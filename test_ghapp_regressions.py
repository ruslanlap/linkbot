import io
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ghapp import github_api, scanner


def archive(data=b'hello', mode=0o755):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        info = tarfile.TarInfo('repo/file.md')
        info.mode, info.size = mode, len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def response(data):
    result = MagicMock()
    result.__enter__.return_value = result
    result.iter_content.return_value = [data]
    return result


def test_snapshot_pinned_and_count_unique(tmp_path):
    (tmp_path / 'file.md').write_text('new')
    (tmp_path / 'file.md').chmod(0o755)
    with patch.object(github_api, 'get_default_branch', return_value='main'), \
         patch.object(github_api, 'get_branch_sha', return_value='snapshot'), \
         patch.object(github_api, 'branch_exists', return_value=False), \
         patch.object(github_api, 'download_repo', return_value=tmp_path) as download, \
         patch('linkbot.scan', return_value=(['file.md', 'file.md'], [])), \
         patch.object(github_api, 'create_commit_from_files') as commit, \
         patch.object(github_api, 'create_pr', return_value=1) as pr:
        result = scanner.scan_repo(1, 'o', 'r')
    assert result['changes'] == ['file.md']
    assert download.call_args.args[-1] == 'snapshot'
    assert commit.call_args.args[3] == 'snapshot'
    assert commit.call_args.args[5]['file.md'] == ('new', '100755')
    assert '**1 file(s) updated.**' in pr.call_args.args[-1]


def test_existing_branch_is_never_updated():
    with patch.object(github_api, 'branch_exists', return_value=True), \
         patch.object(github_api, 'download_repo') as download, \
         patch.object(github_api, 'create_commit_from_files') as commit:
        result = scanner.scan_repo(1, 'o', 'r')
    assert result['pr'] is None
    download.assert_not_called()
    commit.assert_not_called()


def test_branch_creation_never_patches():
    with patch.object(github_api, '_headers', return_value={}), \
         patch('requests.post') as post, patch('requests.patch') as update:
        github_api.create_or_update_branch(1, 'o', 'r', 'b', 'sha')
    update.assert_not_called()
    post.assert_called_once()


def test_archive_limits_and_cleanup(tmp_path):
    with patch.object(github_api, '_headers', return_value={}), \
         patch.object(github_api.tempfile, 'mkdtemp', side_effect=lambda **kw: str(tmp_path / 'extracted')), \
         patch('requests.get', return_value=response(archive(b'x' * 100))), \
         patch.object(github_api, 'MAX_UNCOMPRESSED_BYTES', 10):
        (tmp_path / 'extracted').mkdir()
        with pytest.raises(ValueError):
            github_api.download_repo(1, 'o', 'r')
    assert not (tmp_path / 'extracted').exists()
    with patch.object(github_api, '_headers', return_value={}), \
         patch('requests.get', return_value=response(b'x' * 11)), \
         patch.object(github_api, 'MAX_COMPRESSED_BYTES', 10):
        with pytest.raises(ValueError):
            github_api.download_repo(1, 'o', 'r')


def test_webhook_body_limit():
    from ghapp.app import app
    with app.test_client() as client:
        assert client.post('/webhook', data=b'x' * (1024 * 1024 + 1)).status_code == 413


def test_archive_preserves_executable_and_skips_links(tmp_path):
    import shutil
    with patch.object(github_api, '_headers', return_value={}), \
         patch('requests.get', return_value=response(archive())):
        root = github_api.download_repo(1, 'o', 'r', 'snapshot')
    try:
        assert (root / 'file.md').stat().st_mode & 0o111
    finally:
        shutil.rmtree(root)


def test_commit_uses_snapshot_and_executable_mode_and_never_forces():
    replies = []
    for sha in ('blob', 'tree', 'commit'):
        reply = MagicMock()
        reply.json.return_value = {'sha': sha}
        replies.append(reply)
    branch_reply = MagicMock()
    branch_reply.raise_for_status.side_effect = RuntimeError('branch already exists')
    replies.append(branch_reply)
    commit_response = MagicMock()
    commit_response.json.return_value = {'tree': {'sha': 'snapshot-tree'}}
    with patch.object(github_api, '_headers', return_value={}), \
         patch('requests.get', return_value=commit_response), \
         patch('requests.post', side_effect=replies) as post, \
         patch('requests.patch') as update:
        with pytest.raises(RuntimeError, match='branch already exists'):
            github_api.create_commit_from_files(1, 'o', 'r', 'snapshot', 'b',
                                                {'file.md': ('new', '100755')}, 'msg')
    assert post.call_args_list[1].kwargs['json']['tree'][0]['mode'] == '100755'
    assert post.call_args_list[1].kwargs['json']['base_tree'] == 'snapshot-tree'
    assert post.call_args_list[2].kwargs['json']['parents'] == ['snapshot']
    update.assert_not_called()
