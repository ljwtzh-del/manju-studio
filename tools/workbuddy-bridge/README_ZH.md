# WorkBuddy 本地任务桥接器（Windows）

作用：通过 WorkBuddy 官方 Open API，把 `handoff/inbox/*.md` 任务发送给你电脑上的 WorkBuddy 本地助理，并按任务保存消息 ID、后续回复和交接报告。桥接器仅监听本地文件，不开启 HTTP 服务，不暴露电脑端口。

## 它可以做什么

- 配置 OAuth 应用并在浏览器里进行用户授权。
- 查询 WorkBuddy PC 端本地助理是否在线。
- 将任务 Markdown 文件发送到 WorkBuddy 本地助理。
- 查询后续消息，并把回复写到 `handoff/reports/`。
- 用 `watch` 模式连续串行处理任务文件。
- 将 client secret、access token、refresh token 存入 Windows 系统凭证存储（通过 Python `keyring`）；不把令牌写入项目仓库。

## 真实限制

1. 你必须先拥有 WorkBuddy 开放平台的第三方应用，并拿到 `client_id` 与 `client_secret`。
2. 需要在平台登记回调地址：`http://127.0.0.1:8765/callback`。
3. 申请并获批两项最小权限：`user.localassistant.invokable`、`user.localassistant.readable`。
4. 本地助理执行任务时，WorkBuddy 仍可能在其 UI 中要求你确认工具权限。桥接器不会自动批准权限请求。
5. “API 接收消息成功”或“捕获到助理回复”均不等于代码已完成。必须核对 Git diff、测试日志与真实结果。
6. ChatGPT Free 当前不会因为安装本桥接器就自动获得调用它的工具权限。本方案通过共享仓库和任务文件减少交接，不是对 ChatGPT Free 写操作限制的绕过。

## 安装与使用

请先在 WorkBuddy 打开漫剧工坊目录，然后用 PowerShell 从项目根目录执行：

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r tools\workbuddy-bridge\requirements.txt
python tools\workbuddy-bridge\bridge.py init
python tools\workbuddy-bridge\bridge.py setup
python tools\workbuddy-bridge\bridge.py auth
python tools\workbuddy-bridge\bridge.py status
```

`setup` 会询问应用 ID、回调地址、工程目录与 client secret。secret 输入不回显，并存入 Windows 密钥存储。不要把真实 client secret 发送给 ChatGPT，也不要保存到 `.env` 或 Git。

## 创建任务

1. 将 `handoff/NEXT_TASK.md` 复制为 `handoff/inbox/001-stage1.md`。
2. 填写目标、允许修改范围、禁止修改范围、验收标准和真实测试要求。
3. 确认 WorkBuddy 正在使用正确的工程目录。
4. 执行一次分发：

```powershell
python tools\workbuddy-bridge\bridge.py process
```

5. 桥接器会在发送成功后将任务移到 `handoff/sent/`，并打印 bridge task ID。
6. 捕获回复：

```powershell
python tools\workbuddy-bridge\bridge.py collect --task-id "上一步打印出的任务 ID"
```

也可以持续监听任务箱：

```powershell
python tools\workbuddy-bridge\bridge.py watch
```

`watch` 会串行发送每个任务，等待后续助理回复进入安静窗口后再处理下一个任务。按 Ctrl+C 停止。大任务可能需调大 `--timeout-seconds`；不要同时往同一个 WorkBuddy 会话发送多个互相修改同一文件的任务。

## 手动状态核验

- API 在线状态：`status`
- 已发送但未捕获回复的任务：查看 `handoff/reports/*.json`
- 回复报告：查看 `handoff/reports/*.md`
- 没有捕获到回复时，再执行 `collect`。

桥接器把“安静窗口内未出现新消息”当作停止抓取的技术条件，它不是 WorkBuddy 任务完成信号。最后请在 WorkBuddy UI 中查看操作审批、终端测试与文件修改结果。

## 安全边界

- 任务只允许 Markdown 且最多 50,000 字符；只允许从 `handoff/inbox` 发送。
- 不要将访问令牌、API Key、客户数据、隐私资料或未经授权的声音数据写进任务文件。
- 将高风险动作（删除数据、部署、发布、产生费用、修改其他工程）保留为人工确认。
- 不要把 `handoff/reports` 中的日志直接发布为公开仓库内容；报告可能包含项目结构或内部信息。
- 初次连接请只发送“读取项目并报告 Git 状态”的低风险测试任务。

## 故障排查

- `redirect_uri` 错误：开放平台配置必须与本地配置逐字符一致，包括 IP、端口与路径。
- 无法授权：确认应用处于可用状态、两项权限已批准、client secret 正确。
- `online: false`：打开 WorkBuddy、确认登录同一账号，再检查本地助理是否运行。
- `401`：确认 refresh token 仍有效；必要时重新运行 `auth`。
- 有发送 ID但没有回复：打开 WorkBuddy 检查任务是否卡在权限询问或执行失败，再重新运行 `collect`。
- keyring 报错：确认运行 Windows 原生 Python/Windows Credential Manager 后端，而不是无可用后端的容器或远程 Linux 环境。

官方文档：
- <https://open.workbuddy.cn/docs/third-party-app>
- <https://open.workbuddy.cn/docs/openapi>

## 可选：让私有 GitHub Issue 作为任务入口（进一步减少搬运）

如果你希望只在 GitHub 留一份需求，而不是再把任务拷贝到本地 `handoff/inbox/`，可以启用 GitHub CLI 轮询。这个功能要求本机另行安装 <https://cli.github.com/>，并通过 `gh auth login` 完成 GitHub 登录。WorkBuddy 的 OAuth 和 GitHub CLI 是两套独立授权。

1. 在仓库创建两个标签：`workbuddy-task` 和 `workbuddy-dispatched`。
2. 运行 `gh auth status` 确认登录的是你自己的 GitHub 账号。
3. 在 `setup` 中填写私有仓库 `owner/repo`（如之前留空可再次运行 `setup` 并保留原配置）。
4. 创建一个 Open Issue，勾选 `workbuddy-task` 标签。桥接器只自动分发由当前 `gh` 登录账号创建的 Issue，跳过其他作者的 Issue，避免陌生协作者触发本地执行。
5. 在 PowerShell 运行一次：

```powershell
python tools\workbuddy-bridge\bridge.py watch-github --once
```

若验证无误，再持续运行：

```powershell
python tools\workbuddy-bridge\bridge.py watch-github
```

桥接器会将 Issue 标题、正文和 URL 转成任务发送给 WorkBuddy；成功后给 Issue 添加 `workbuddy-dispatched` 标签并留言记录 bridge task ID。它不会自动关闭 Issue，也不会自动把任务标记为已完成。检查 WorkBuddy 实际修改和测试后，由你决定是否关闭 Issue。

重要：ChatGPT 内置 GitHub 应用的官方说明是只读——可检索已授权仓库内容，但不能直接创建 Issue、推送代码或修改仓库。你需要在 GitHub 网页中创建带 `workbuddy-task` 标签的 Issue；这仍然只需交接一条任务描述，不需要反复搬运代码和日志。ChatGPT 连接器可用于之后读取仓库/Issue 内容（前提是当前 Free 界面提供此连接）。
