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

`path` 为单个文件或目录，默认 `.`。新输入 `fix` 仅接受 `'true'` 或 `'false'`（默认）；`'true'` 应用符合条件的修复。输出 `exit-code` 为 0、1 或 2；1 和 2 会使步骤失败。通过 `${{ steps.links.outputs.exit-code }}` 读取；失败后使用 `if: always()` 或 `continue-on-error`。action 不需要令牌或写权限，也不创建 PR。

### 定时修复 PR

将 [`.github/workflows/linkbot.yml`](.github/workflows/linkbot.yml) 复制到自己仓库的相同路径。它每周或手动运行，使用 `fix: 'true'` 调用已发布的 action，并通过 `peter-evans/create-pull-request` 将更改合并到一个 PR。退出码 1 允许在存在未修复 404 时提交修复；退出码 2 或缺少状态会阻止 PR。只有 404 时不会创建 PR；请查看 action 日志。合并前请审查所有修复。工作流仅授予 contents 和 pull-requests 写权限；仓库设置还必须允许 Actions 创建 PR。

工作流引用 `@main`，因此必须先合并并发布这些更改。发布后请固定到包含 `fix` 的不可变提交或版本；上面的 `v0.1.0` 示例仅用于检查。尚未使用真实 PR 验证。

## 限制

支持简单内联 Markdown HTTPS 链接、嵌套图片徽章链接，以及单行、带引号 href 的 HTML 锚点；跳过图片源、含查询参数的 URL、代码块及包含反引号或反斜杠的行。修复同主机、最终返回 200 的 301/308。对于确认 404 的 GitHub `releases/latest/download` 资源，通过无需令牌的公开 API 查询最新稳定版本，仅当资源名只有版本不同且匹配唯一时才修复；草稿、预发布、缺失或不明确的结果不会修复，API 限流可能阻止修复。锚点保留但不验证；私有地址会被拒绝。部分 HTTP/网络错误和不可访问的目录可能被忽略。请审查所有修改，不要在 URL 中放入密钥。

实验性的托管 GitHub App 代码仍保留在 `ghapp/`，但不受支持。

完整测试需安装 `requirements.txt`、`pytest`、`pytest-subtests` 和 `pyyaml`，然后运行 `python3 -m pytest -q`。
