#!/usr/bin/env python3
"""Conservative Markdown HTTPS link checker; standard library only."""
import argparse
import http.client
import ipaddress
import re
import socket
import ssl
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

# ponytail: handles simple inline links only; use a Markdown parser for full syntax.
LINK = re.compile(r'(?<!!)\[[^\]\n]*\]\(https://[^\s()<>]+\)')


def parts(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username is not None or
            p.password is not None or p.query or p.port not in (None, 443) or
            any(ord(c) < 33 or ord(c) == 127 for c in url)):
        raise ValueError('unsupported URL')
    return p


def fetch(url):
    p = parts(url)
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('non-public address')
    # Connect to the already-validated numeric address, preventing DNS rebinding.
    addr = addresses[0][4]
    sock = socket.create_connection((addr[0], addr[1]), timeout=10)
    try:
        tls = ssl.create_default_context().wrap_socket(sock, server_hostname=p.hostname)
    except Exception:
        sock.close()
        raise
    conn = http.client.HTTPSConnection(p.hostname, timeout=10)
    conn.sock = tls
    try:
        conn.request('GET', urlunsplit(('', '', p.path or '/', '', '')), headers={'User-Agent': 'LinkBot/1.0', 'Accept': '*/*'})
        response = conn.getresponse()
        return response.status, response.getheader('Location')
    finally:
        conn.close()


def resolve(url):
    """Return (replacement, missing); only all-permanent chains ending in 200 qualify."""
    try:
        original = parts(url)
        current = urlunsplit((original.scheme, original.netloc, original.path, '', ''))
        seen = set()
        redirected = False
        for _ in range(6):
            if current in seen:
                return None, False
            seen.add(current)
            status, location = fetch(current)
            if status == 404:
                return None, True
            if status == 200:
                return (current + ('#' + original.fragment if original.fragment else '') if redirected else None), False
            if status not in (301, 308) or not location:
                return None, False
            target = urljoin(current, location)
            p = parts(target)
            if p.hostname.lower() != original.hostname.lower() or p.fragment:
                return None, False
            current = target
            redirected = True
    except (ValueError, OSError, http.client.HTTPException, UnicodeError):
        pass
    return None, False


def scan(root, fix=True, strict=False):
    root = Path(root)
    if strict and not root.exists():
        raise FileNotFoundError(root)
    paths = [root] if root.is_file() else sorted(root.rglob('*.md'))
    base = root.parent if root.is_file() else root
    changes, missing = [], []
    for path in paths:
        if path.is_symlink() or '.git' in path.parts or path.suffix.lower() != '.md':
            continue
        try:
            text = path.read_bytes().decode('utf-8')
        except (OSError, UnicodeError):
            if strict:
                raise
            continue
        def replace(match):
            token = match.group(0)
            start = token.index('](https://') + 2
            url = token[start:-1]
            replacement, is_missing = resolve(url)
            name = path.relative_to(base).as_posix()
            if is_missing:
                missing.append(f'{name}: {url}')
            if replacement and replacement != url:
                changes.append(name)
                return token[:start] + replacement + ')'
            return match.group(0)
        # ponytail: skip all backtick lines; a Markdown parser can recover inline links later.
        lines, fence = [], None
        for line in text.splitlines(keepends=True):
            marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
            if fence:
                if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                    fence = None
                lines.append(line)
            elif marker:
                fence = marker.group(1)
                lines.append(line)
            elif '`' in line:
                lines.append(line)
            else:
                lines.append(LINK.sub(replace, line))
        updated = ''.join(lines)
        if updated != text and fix:
            path.write_bytes(updated.encode('utf-8'))
    return changes, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check Markdown HTTPS links; use --fix to update permanent redirects.')
    parser.add_argument('--fix', action='store_true', help='write eligible redirect replacements')
    parser.add_argument('paths', nargs='*', default=['.'], help='Markdown files or directories (default: current directory)')
    args = parser.parse_args(argv)
    changes, missing = [], []
    try:
        for path in args.paths:
            found, broken = scan(Path(path), fix=args.fix, strict=True)
            changes.extend(found)
            missing.extend(broken)
    except (OSError, UnicodeError) as exc:
        import sys
        print(f'linkbot: {exc!s}', file=sys.stderr)
        return 2
    print(f'{"Updated" if args.fix else "Would update"} {len(changes)} links.')
    for item in changes:
        print(f'  {item!r}')
    print('404 links:')
    for item in missing:
        print(repr(item))
    return 1 if missing or (changes and not args.fix) else 0


if __name__ == '__main__':
    raise SystemExit(main())
