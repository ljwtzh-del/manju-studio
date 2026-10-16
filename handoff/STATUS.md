# 漫剧工坊开发状态

## 当前状态
- 阶段：工程准备 / 连接 GitHub 与 WorkBuddy
- 事实来源：当前 Git commit、真实测试输出、WorkBuddy 执行记录
- 最后更新时间：待首次真实开发后填写

## 已有工程骨架
- [x] FastAPI 本地 Web MVP 骨架（具体运行状态需在目标 Windows 机器验证）
- [x] ComfyUI API 工作流接入骨架
- [x] 视频拼接 / 音轨 / 字幕烧录流程骨架
- [x] WorkBuddy 本地桥接器起步实现（须通过真实 OAuth / API 连通性测试）
- [ ] 私有 GitHub 仓库连接
- [ ] WorkBuddy OAuth 应用权限获批
- [ ] 真实 API 冒烟测试
- [ ] 自动化单元测试与代码审查

## 约束
- 不修改已有 Novel Studio 项目管理功能。
- 不提交 `.env`、凭证、运行数据库、模型权重、生成媒体或私人用户资产。
- 未实测的功能不得标记为 PASS。

## 下一步
1. 按 `GITHUB_SETUP.md` 建立私有仓库并完成首次安全 push。
2. 按 `tools/workbuddy-bridge/README_ZH.md` 配置 WorkBuddy 官方 API。
3. 先发出低风险只读任务，确认消息往返成功。
4. 再从 `handoff/inbox/` 分发漫剧工坊 Stage 1 开发任务。
