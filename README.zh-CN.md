# LinkBot

[English](README.md) | [Українська](README.uk.md) | 简体中文

检查 Markdown HTTPS 链接的永久重定向和 404。CLI、pre-commit 和 action 默认不修改文件；只有明确使用 `--fix` 才会修改本地文件。工具发送 HTTPS GET 请求，不进行网络写入。

## CLI

需要 Python 3.9+ 和 pip；核心代码无第三方运行时依赖：

```sh
python3 -m pip install .
linkbot
linkbot docs README.md
linkbot --fix docs
```

请审查 diff。退出码：0 表示无发现（或已修复且无 404），1 表示检查时发现重定向或发现 404，2 表示参数或文件读写错误。网络错误和不支持的链接会被跳过，因此成功不代表所有链接正常。输出包含链接数量、文件名和 404；后续文件出错时先前修改可能保留。

## pre-commit

先安装 [pre-commit](https://pre-commit.com/)，然后添加 `.pre-commit-config.yaml`，此示例固定到已发布的版本标签：

```yaml
repos:
  - repo: https://github.com/ruslanlap/linkbot
    rev: v0.1.0
    hooks:
      - id: linkbot
```

运行 `pre-commit install` 和 `pre-commit run --all-files`。hook 检查传入的 Markdown 文件，不修改文件或 Git 索引，包括部分暂存文件。使用 `linkbot --fix` 单独修复、审查并手动暂存。网络检查可能较慢，离线结果不完整。

## GitHub Action

需要 checkout、Python 3 和 bash；此示例固定到已发布的版本标签：

```yaml
jobs:
  links:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - id: links
        uses: ruslanlap/linkbot@v0.1.0
        with:
          path: docs
```

`path` 为单个文件或目录，默认 `.`。输出 `exit-code` 为 0、1 或 2；1 和 2 会使步骤失败。通过 `${{ steps.links.outputs.exit-code }}` 读取；失败后使用 `if: always()` 或 `continue-on-error`。action 不需要令牌或写权限，`contents: read` 用于 checkout。action 不修复文件或创建 PR。本仓库另有定时/手动 `.github/workflows/linkbot.yml`，执行 `--fix` 并可能创建 PR，需要 contents 和 pull-requests 写权限及 GitHub 设置允许创建 PR；尚未在真实 GitHub 验证。只有 404 不会创建 PR，请查看运行摘要。

## 限制

仅支持简单的内联 HTTPS 链接；图片、带查询参数的 URL、代码块、含反引号的行和其他 Markdown 形式会被跳过。只修复同主机、最终返回 200 的 301/308。锚点保留但不验证；私有地址会被拒绝。部分 HTTP/网络错误和不可访问的目录可能被忽略。请审查所有修改，不要在 URL 中放入密钥。

实验性的托管 GitHub App 代码仍保留在 `ghapp/`，但不受支持。

完整测试需安装 `requirements.txt`、`pytest`、`pytest-subtests` 和 `pyyaml`，然后运行 `python3 -m pytest -q`。
