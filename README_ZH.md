# 漫剧工坊 Studio（MVP 起步项目）

这是一个独立的本地 Web 工作台骨架，围绕“ComfyUI 生图 + Agnes 视频 + FFmpeg 后期”组织生产。它不修改现有 Novel Studio 项目管理层，也不是对 Agnes Pavo 的官方复刻。

## 目前包含

- 项目、镜头分镜、镜头提示词和本地资产库（SQLite）
- 导入 ComfyUI 的 API Format JSON 工作流，通过 `/prompt` 提交任务、查询 history、预览并将生成图片导入资产库
- 可选 Agnes 视频 API 适配器（需要独立 API Key；Pavo 网页会员不等于 API 权限）
- 视频片段归一化、按顺序拼接、边界帧去重、配音/BGM 混音、SRT/ASS 字幕烧录和 MP4 导出
- 任务记录与失败错误显示

## 暂不包含 / 需要后续工程化

- 真实 3D 导演台（可拖拽角色、地面网格、多机位相机操控）——当前先提供分镜板与首尾帧工作流入口，不伪装成完整 3D 场景编辑器
- 角色 LoRA 训练、自动剧本拆分、自动口型同步和自动逐字时间戳
- 内置 TTS 模型。MVP 可上传配音音轨；建议下一阶段接入自托管 CosyVoice/GPT-SoVITS 服务
- 可恢复的持久化作业队列、并发控制、用户登录/权限、对象存储、远程公开图片 URL 服务和成本审计
- Agnes 生成视频的自动下载与 API 字段变化兼容；当前视频 API 的字段版本应和你已开通的模型文档核对

## Windows 本机运行

1. 安装 Python 3.11+、Node 不需要（前端是纯静态页面）、FFmpeg（确保 `ffmpeg` 与 `ffprobe` 在 PATH 里）。
2. 将 `manju-studio-mvp` 文件夹放在合适的开发目录。
3. 复制配置：

   ```powershell
   copy .env.example .env
   ```

4. 编辑 `.env`：
   - `COMFYUI_URL=http://127.0.0.1:8188`
   - 若使用 Agnes API，再填 `AGNES_API_KEY`。不要把密钥提交到 Git。
5. 建立虚拟环境并安装依赖：

   ```powershell
   py -3.11 -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn app.main:app --host 127.0.0.1 --port 8600 --reload
   ```

6. 浏览器访问 `http://127.0.0.1:8600`。

> 只监听 `127.0.0.1`。MVP 没有登录认证，切勿直接将端口暴露到公网。

## ComfyUI 工作流配置

1. 在 ComfyUI 里选好适合漫剧的 checkpoint / LoRA / ControlNet / IP-Adapter 等，测试生图质量。
2. 用 ComfyUI 的 `Save (API Format)` 导出 API 工作流 JSON（不是普通 UI workflow JSON）。
3. 粘贴到“生成引擎 → ComfyUI”里。
4. 按实际导出 JSON 的节点 ID 配置正向提示词、负向提示词、seed、宽高映射，格式是 `节点ID.字段名`，例如 `6.text`。不同工作流节点结构不同，不能盲用示例 ID。
5. 提交后查询任务结果，可将生成图片导入当前项目。如果当前镜头已选中，导入图片会绑定为关键帧。

## Agnes 关键帧视频

MVP 使用可配置的 Agnes API 适配器。默认按 `agnes-video-2.5` 的关键帧模式提交 `mode=keyframe`、`first_frame` / `last_frame`、`seconds`、`size`、`aspect_ratio`。模型接口存在版本差异；如果你使用的是另一版 Agnes 模型，应按该模型的正式请求字段调整 `app/main.py` 的 `agnes_create_video` 和 `agnes_poll`。

首尾帧需要填写 Agnes 服务可访问的图片 URL。`127.0.0.1` 或本机盘符路径通常不是远端服务可访问的 URL。正式版应增加私有对象存储或安全的短时签名 URL 上传流程。

如果当前只有 Pavo 网页端权限，没有 API Key，先把 Pavo 导出的视频上传到“资产库”，照样可以进行自动拼接、混音和字幕烧录。

## 边界帧策略：none / dedupe1 / boundary2

- `none`：不裁剪，适合独立镜头或模型已保证衔接的片段。
- `dedupe1`：从第 2 段及后续段落开头移除 1 帧，适合下一段首帧被复用为上一段末帧的情况。
- `boundary2`：对非最后一段尾部移除 2 帧，并从后续段落开头移除桥接首帧。它对应的桥接约定是：下一段首帧使用上一段实际输出视频的倒数第 3 帧（帧编号从 0 开始，即 `N-3`）。

不要无条件把所有视频都裁掉两帧。建议先用 3 个镜头逐帧验收，确认模型是否真有尾帧重复/异常，再决定项目默认策略。代码会记录每条视频裁剪前的帧数和当前策略。

## 配音、BGM、字幕

- 配音：MVP 先将 TTS 输出音频作为 `voice` 或 `audio` 上传。下一阶段建议将自托管 CosyVoice 或 GPT-SoVITS 包成一个本地 API provider，让角色音色、语速、停顿参数进入项目数据。代码/模型权重/训练数据的许可证需分别审核；使用真人声音克隆时需取得相应授权。
- BGM：上传 WAV/MP3 等资产，并在后期页选择；可单独调整 BGM 分贝。商用发布要使用自有或明确授权的音乐。
- 字幕：上传与成片时间轴对应的 SRT/ASS。SRT 可先由台词表生成；需要逐字效果时下一阶段增加语音识别/强制对齐。字幕通过 FFmpeg 的 `subtitles`（libass）滤镜烧录。
- 若配音超过视频时长，MVP 的 `-shortest` 会以视频长度为准；正式系统应先做音视频时长校验与时间线重排。

## 推荐开发顺序

1. ComfyUI 工作流稳定化：角色资产、场景资产、角色 LoRA/IP-Adapter、输出图审阅和版本选择。
2. 镜头连续性：每段保存实际首末帧，建立 `bridge_frame_asset_id`、帧号、fps 和裁剪规则，自动给下一镜头填首帧参考。
3. Agnes 视频适配器：模型字段确认、任务轮询、视频自动拉取到资产库、失败重试和成本记录。
4. 音频工位：角色配音服务、角色音色库、台词分段、BGM ducking/淡入淡出、音频时间线。
5. 字幕与交付：SRT 自动生成、人工校对、字幕模板、多规格导出。
6. 工程化：后台任务队列（Redis/Celery 或等价方案）、可恢复任务、对象存储、权限、并发配额、审计日志。

## GitHub 与 WorkBuddy 低搬运工作流

- 先看 `GITHUB_SETUP.md`：建立私有 GitHub 仓库、检查忽略规则、连接 ChatGPT GitHub 应用（若当前账号界面提供）。GitHub 连接用于读取获授权仓库，不等同于控制 WorkBuddy。
- 再看 `tools/workbuddy-bridge/README_ZH.md`：桥接器通过 WorkBuddy 官方 Open API 发送 Markdown 任务并捕获后续回复。需要自己注册 WorkBuddy 开放平台应用、获批 OAuth 权限并授权账号；这是本地起步工程，不代表真实 API 已连通。
- 任务投递目录是 `handoff/inbox/`。工作任务应一次只包含一个可验收目标。凭证通过 Windows 密钥存储保存，不得把 secret/token 放到仓库。
- ChatGPT Free 不会因为仓接入器安装就自动获得当前会话的本地写操作能力；请勿把桥接器理解为绕过套餐限制的方案。

## 重要参考

- ComfyUI：<https://docs.comfy.org/>；常规 API 工作流由 `/prompt` 提交，并通过 history/queue API 查询。
- FFmpeg Filters：<https://ffmpeg.org/ffmpeg-filters.html>；字幕烧录取决于 FFmpeg build 是否包含 subtitles/libass。
- StoryBored（MIT，参考项目流程）：<https://github.com/storybored-app/storybored>
- OpenVideoStudio（Apache-2.0，参考本地优先、分阶段生产与合成流程）：<https://github.com/mne03005-png/OpenVideoStudio>

本项目是可以在本机运行和继续开发的 MVP 骨架，不代表已连接你的实际 ComfyUI/Agnes API，也不声称已完成完整 Pavo 等级的 3D 导演台。
