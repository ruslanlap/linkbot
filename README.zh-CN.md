# LinkBot

[English](README.md) | [Українська](README.uk.md) | 简体中文

LinkBot 查找 Markdown 中的永久重定向链接，并通过 pull request 提出修改。

> **实验性原型。** 公共 GitHub App 尚未注册或部署，也没有安装按钮。尚未使用真实 GitHub API 验证 PR 创建；请勿用于生产环境。

## 使用流程

1. 如需试用，请自行注册 GitHub App、部署服务器，并授予所选仓库的访问权限。配置步骤见 [English README](README.md)。
2. 安装 webhook 会触发扫描。若要每周扫描，需要单独启动调度器并手动配置 `LINKBOT_INSTALLATION_IDS`。
3. 找到重定向后，请在合并前审查 PR。如果 `linkbot/permanent-redirects` 分支已存在，仓库会被跳过；机器人不会更新该分支。

**仅有 404 时不会创建通知或 PR。** 没有 PR 不代表所有链接都正常。

## 替代方案：GitHub Actions

将 `linkbot.py` 和 `.github/workflows/linkbot.yml` 复制到仓库，并在 GitHub Actions 设置中允许创建 PR。通过 **Actions → LinkBot → Run workflow** 手动运行。这不是安装 GitHub App；工作流尚未在真实 GitHub 上验证。

## 限制

仅检查 Markdown 中简单的 HTTPS 链接以及指向同一主机的 301/308 重定向。图片、URL 查询字符串、代码块及部分 Markdown 语法会被跳过。锚点会保留，但不会验证。重定向不能保证页面内容等价，请手动审查 diff。

## 本地运行

`python3 linkbot.py .` 会检查并**修改**当前目录下的 Markdown 文件；提交前请审查更改。服务器依赖：`pip install -r requirements.txt`。测试还需安装 pytest 和 pytest-subtests，然后运行 `python3 -m pytest -q`。
