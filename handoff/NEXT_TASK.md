# WorkBuddy 开发任务模板

将此文件复制到 `handoff/inbox/001-stage1-smoke-test.md`，把占位内容改为本次任务，再执行桥接器。

## 目标
先确认工程可重复运行，不做业务大改。

## 范围
- 允许修改：测试、README、启动脚本中的必要内容。
- 禁止修改：既有 Novel Studio 工程；未经审查的大规模架构重写；删除用户数据；任何密钥文件。

## 执行步骤
1. 检查 `git status`、Python 版本、依赖文件和项目结构。
2. 创建/运行目前能够运行的测试；若缺少测试，补充最小冒烟测试。
3. 运行 `python -m compileall app tools/workbuddy-bridge`。
4. 检查桥接器 CLI 的帮助与 init 功能，不调用真实 WorkBuddy API，除非用户已完成 OAuth 配置并明确要求。
5. 检查 `.gitignore` 是否排除 `.env`、数据库、OAuth 配置和凭证文件。
6. 修复发现的低风险问题并重跑测试。

## 验收标准
- 实际列出执行的命令和退出码。
- 不得声称没有运行的测试通过。
- 不得输出 secret/token 的内容。
- 清楚报告当前还未真实验证的 ComfyUI / Agnes API / TTS / FFmpeg 部分。

## 交付格式
更新 `handoff/STATUS.md` 与 `handoff/REPORT.md`，列出修改文件、测试输出摘要、未完成问题、下一阶段建议。除非用户另行要求，先不要自动 push。
