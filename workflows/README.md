# ComfyUI 工作流目录

把 ComfyUI `Save (API Format)` 导出的工作流 JSON 放在本目录作为版本化模板。不同 checkpoint、LoRA、IP-Adapter、ControlNet 或自定义节点会造成 workflow JSON 与输入映射不同，所以不要使用未在自己的 ComfyUI 安装中验证过的 JSON。

建议为工作流维护一个伴随清单：
- `name` / `version`
- `comfyui_version`
- 所需节点与模型文件
- 正向提示词节点 ID / 字段
- 负向提示词节点 ID / 字段
- seed 节点 ID / 字段
- 宽高节点 ID / 字段
- 保存图片节点
- 验收样例与推荐显存
