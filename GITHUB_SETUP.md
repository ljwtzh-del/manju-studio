# 方案 A：私有 GitHub 仓库（先完成）

目标：让 ChatGPT 在连接器支持且仓库授权完成时可以按需读取工程代码；让 WorkBuddy 通过本地 Git 管理代码与开发阶段。GitHub 仓库是共享工程记录，不等于 ChatGPT 获得 WorkBuddy 终端控制权。

## 1. 创建私有仓库

1. 打开 <https://github.com/new>。
2. Repository name：`manju-studio`。
3. 选择 **Private**，不要选择 Public。
4. 由于本地已有文件，初始化 README 可不勾选，避免第一次 push 冲突。
5. 创建后复制仓库的 HTTPS 或 SSH URL。

官方指南：<https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository>

## 2. 首次安全检查

在 PowerShell 切到工程根目录：

```powershell
git status --short
git check-ignore .env data/studio.sqlite3
```

必须确认 `.env`、数据库运行文件、桥接器本地配置和凭证没有进入 Git。`git status --short` 里不应出现真实密钥文件。

## 3. 初始化 Git 并绑定远端

如果当前目录还没有 Git 仓库：

```powershell
git init
git branch -M main
git add .
git status --short
```

先人工检查 `git status`，确认没有密钥、用户素材、生成视频、模型权重、数据库和大型临时文件，再提交：

```powershell
git commit -m "chore: initialize Manju Studio workspace"
git remote add origin YOUR_PRIVATE_REPOSITORY_URL
git push -u origin main
```

如果目录已经是 Git 仓库，先运行 `git remote -v` 与 `git status`，不要再次 `git init` 或覆盖已有 remote；确认后再绑定远端。

## 4. 连接 ChatGPT

1. 在 ChatGPT 的 Settings → Apps（或 Connectors，界面名称可能变化）中查找 GitHub。
2. 按页面流程授权 GitHub，并在 GitHub App 的 repository access 设置中，只选择 `manju-studio`。
3. 回到 ChatGPT 对话，测试请求：“请读取私有仓库 `manju-studio` 的 README_ZH.md、GITHUB_SETUP.md、handoff/STATUS.md，并总结当前架构。”
4. 如果仓库不显示，检查 GitHub App 安装是否针对正确账户/组织，并确认该仓库已被勾选。新建私有仓库可能不会立即出现。

OpenAI 官方说明：<https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt>

## 5. 当前 Free 账号的边界

- GitHub 连接的可用性和读取范围以当前 ChatGPT Apps 页面实际显示为准。
- GitHub 连接用于检索授权仓库内容；不要假定它能直接改文件、提交代码或启动 WorkBuddy。
- 若 Free 工作区没有 GitHub App，仍可以使用私有 GitHub 存档，但 ChatGPT 读取代码会需要文件附件或摘要作为替代渠道。
- 不要把 `.env`、token、client secret、数据库、用户私人素材、付费模型凭证或未经授权的音视频推送到仓库。

## 6. 后续日常节奏

- WorkBuddy 每完成一个开发阶段：运行测试、检查 `git diff`、提交代码、更新 `handoff/STATUS.md` 和 `handoff/REPORT.md`。
- 每个任务一个小提交；保持可回滚，禁止将所有阶段一次性混成一个大提交。
- 以 Git commit 和测试日志为事实来源，不以智能体自述的“全部完成”为验收依据。
