# 验收记录

2026-09-21，Ubuntu / Python 3.13 / ComfyUI frontend 1.53.6 / comfy-cli 1.20.0 / comfy-mcp 0.10.0 / MCP SDK 2.2.0。

已实际执行：

- 局域网 HTTP 浏览器连接，直接读 pos/size/bounds 和插槽。
- MCP stdio 握手，客户端发现 54 个不重复工具；官方 server_info 回归。
- 新标签批量添加 EmptyImage、SaveImage，修改四个 widget、按插槽名连接。
- 一次 undo 返回空图、redo 恢复整个批次。
- 自动布局 dry-run 不改变 revision；实际布局与分组可操作。
- UI JSON 保存后从 ComfyUI 用户 API 读取，确认两个节点、一条连线（不是仅检查 HTTP 200）。
- 无模型 64×64 任务完成，官方 job 返回 completed，fetch_outputs 下载实际 PNG。
- 从该 PNG 提取 prompt/workflow 元数据。
- 画布截图通过 MCP 返回；子图创建、进入/退出 settled=true、解包、蓝图保存。
- 版本清单通过独立 systemd worker 生成并返回 success。
- 隔离临时目录中验证归档 SHA-256、恢复代码、保留 excluded models、保留反向备份。

没有为了测试而更新/卸载用户节点、改动真实模型分类、下载大模型，或替换生产 Conda 环境。完整环境恢复只做了隔离文件夹机制验证，没有在生产环境执行破坏性恢复。视频元数据、不同自定义节点、所有前端版本和所有子图组合未做穷举兼容测试。

因此此记录证明已验证的链路可用，不等于承诺任意第三方节点或将来版本完全兼容。遇到新组合可用开放 eval 验证，再把稳定方法纳入结构化工具和 skill。

## 0.1.1 状态面板

- 浏览器实测左下角统计区上方的入口，字号为 10px，未遮挡右下角画布工具栏。
- 点击打开详情、关闭按钮与 Esc 关闭、重新打开、手动与自动刷新均通过。
- 连接页数、Client ID、画布信息、前后端版本与实际桥接返回一致；不把桥接连接冒充为 Agent 在线。
- 复制 Client ID 后核对剪贴板内容；提供不支持剪贴板 API 时的可选中文本。
- 只读请求与过期 revision 拒绝均出现在最近操作中；检查前后画布 revision 未改变。
- 面板内容可滚动，窄窗口无横向溢出。没有为验收修改、保存或运行工作流。
