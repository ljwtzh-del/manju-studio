# 漫剧工坊：先方案 A，再方案 B（按顺序操作）

这份文件是最短启动清单。详细说明见 `GITHUB_SETUP.md` 和 `tools/workbuddy-bridge/README_ZH.md`。

## A. 私有 GitHub 仓库

1. 下载并解压本工程到一个稳定路径，例如 `D:\Manju-Studio`。
2. 打开 <https://github.com/new>，创建 **Private** 仓库 `manju-studio`；本地工程已有文件时不要再初始化远端 README。
3. 在 PowerShell 切到工程目录，确认敏感文件被忽略：

   ```powershell
   git check-ignore .env data/studio.sqlite3
   git status --short
   ```

4. 若还未初始化 Git：

   ```powershell
   git init
   git branch -M main
   git add .
   git status --short
   ```

   人工检查暂存文件，确认无 `.env`、token、client secret、数据库、个人图片/音视频、模型权重后再提交：

   ```powershell
   git commit -m "chore: initialize Manju Studio workspace"
   git remote add origin YOUR_PRIVATE_REPOSITORY_URL
   git push -u origin main
   ```

   若目录已有 `.git`，先用 `git remote -v` 检查，不能覆盖已有远端。

5. 在 ChatGPT 的 Apps 页面连接 GitHub（若当前 Free 界面提供），只授权 `manju-studio`。测试 ChatGPT 能否读取 `README_ZH.md` 和 `handoff/STATUS.md`。若没有 GitHub App 或仓库读权限，本阶段只完成 GitHub 代码托管，不假装已连接 ChatGPT。

## B. WorkBuddy 本地桥接器

### 注册一次 WorkBuddy OAuth 应用

1. 打开 <https://open.workbuddy.cn/docs/third-party-app> 及开放平台应用管理页，注册第三方应用。
2. 登记回调地址：`http://127.0.0.1:8765/callback`。
3. 申请并等待批准：`user.localassistant.invokable`、`user.localassistant.readable`。
4. 记录 `client_id` 与 `client_secret`。不要发给 ChatGPT、不要放进 Git。
5. 如果使用 GitHub Issue 自动触发，再安装 GitHub CLI：<https://cli.github.com/>，并执行 `gh auth login`。两个授权相互独立。

### 配置本机

1. 在 WorkBuddy 中打开 `D:\Manju-Studio` 对应工程。
2. 双击 `setup_workbuddy_bridge.bat`，按提示输入应用资料并完成浏览器授权。
3. 必须看到 `WorkBuddy 本地助理在线：是`。如果不是，不要发送开发任务。
4. 首先把只读任务写到 `handoff/inbox/000-smoke-test.md`：

   ```markdown
   # 低风险连接测试
   只读取当前项目根目录。报告 README 内容摘要、Git 状态、Python 版本和可以运行的测试命令。不得修改任何文件、不得运行部署或付费 API。
   ```

5. 分发文件任务：

   ```powershell
   .venv\Scripts\python.exe tools\workbuddy-bridge\bridge.py process
   ```

   收到打印出的 bridge task ID 后：

   ```powershell
   .venv\Scripts\python.exe tools\workbuddy-bridge\bridge.py collect --task-id "替换成实际任务 ID"
   ```

### 想只维护一份 GitHub Issue 时（推荐的少搬运模式）

1. 在 GitHub 仓库确保存在标签 `workbuddy-task`、`workbuddy-dispatched`。
2. 在 `setup` 的 GitHub 仓库提示中填 `你的用户名/manju-studio`。
3. 新建 Open Issue，任务内容按“一条 Issue 一个可验收目标”写，并添加 `workbuddy-task` 标签。
4. 运行 `python tools\workbuddy-bridge\bridge.py watch-github --once` 试运行。确认无误后，再持续运行 `python tools\workbuddy-bridge\bridge.py watch-github`。
5. 桥接器仅处理当前 `gh auth login` 账号自己创建的 Issue；发送后会添加 `workbuddy-dispatched` 标签。它不会自动关闭 Issue，也不会自动批准 WorkBuddy 的终端/工具权限。

ChatGPT 内置 GitHub 应用官方说明为只读，不能直接创建 Issue、修改仓库或 push 代码；因此你需要把 ChatGPT 生成的任务摘要粘贴到 GitHub 网页中创建 Issue（一次只交接任务需求，后续代码和日志通过仓库/报告保存）。如果当前 Free 界面没有 GitHub 连接入口，也不妨碍你使用私有仓库和本地 WorkBuddy Issue 轮询。不要把“能读仓库”理解为“能直接控制 WorkBuddy”。

## 状态判断

- A 完成：私有仓库有初始提交、敏感文件未提交、（可选）ChatGPT GitHub 连接只授权该仓库且确实能读取。
- B 完成：本地助理在线；低风险消息成功发送；消息历史能返回；响应记录写到 `handoff/reports/`。
- 真正的任务验收：WorkBuddy 有实际 Git diff、测试命令/输出，且由你确认结果。API 返回 message_id 或 assistant 回复都不是验收通过。
