# 实时画布操作指南

这是现有 `comfyui` MCP 的扩展，不是第二个 Agent。官方无头工具仍在同一入口。

## 选哪条路径

- 用户说“我正在看的画布”：先 `canvas_status`，明确浏览器 client_id，再 `canvas_read`。一个页面自动选择；多个页面选择后 bind_client，后续不会追随焦点乱跳。
- 浏览器必须打开且刷新过扩展。没有页面时仍能用官方文件执行工具，但不要说修改了用户当前画布。
- 日常读取用 outline、selected 或 viewport；查具体节点用 ids。真实 pos/size/bounds、插槽、分组和图 ID 是操作依据，截图仅辅助看效果。
- 改参数/节点/连线用 canvas_apply，复杂修改可以先 canvas_workflow checkpoint。用读取返回的 revision 检查是否已被用户改动。
- 原生子图、自动布局、蓝图的具体参数可从 canvas_status(capabilities=true) 查看；无需记近百个工具名。
- 结构化工具暂未覆盖的动作可用 canvas_eval，成功后可提炼为正式工具或技能经验。不需要因为工具名不存在就宣称前端无法做到。

## 一个批次的示例

```json
{"operations":[
  {"op":"add","class_type":"EmptyImage","pos":[80,120],"as":"image"},
  {"op":"add","class_type":"SaveImage","pos":[480,120],"as":"save"},
  {"op":"set_widget","node_id":"$image","widget":"width","value":512},
  {"op":"connect","from_node_id":"$image","from_output":"IMAGE","to_node_id":"$save","to_input":"images"}
]}
```

操作后读回；批次可原生 undo/redo。普通节点修改、布局无需反复询问用户；工作流整体替换、共享依赖调整、打断别人的任务、删除模型、收费调用等影响不明时核实关键范围。必要时用独立子 Agent 判断，而非把所有工作卡在审核上。

## 保存、运行、恢复

- canvas_workflow save_as 的 path 例如 `my-project/demo.json`，实际使用 ComfyUI 用户工作流存储 API。
- canvas_control run 提交当前未保存的画布，返回真实 prompt ID。用官方 job/fetch_outputs 确认完成与输出。只收到 queued 不等于完成。
- run 的 to_node_id 限已存在的根图输出节点；复杂子图执行 ID 需要先检查实际 prompt，不猜。
- 超时是结果未知，不是操作没发生。同一个 request_id 可取已有结果；不要新建 ID 盲目重复排队。
- workflow_tools 负责分析/diff/切片/转换；转换开新标签，API 转 UI 会重建布局，不是原布局无损恢复。
- workflow_media 只提取确实存在的媒体元数据。被清理元数据的图不能还原原工作流。
- canvas_workflow checkpoint 保存图；environment_snapshot manifest 只保存版本清单，restorable 才归档实体环境。恢复命令/任务结果保存在快照目录。

## 模型、节点与运行环境

- 下载使用官方 `download_model`；本插件的 `model_catalog` 负责本地模型检查与分类，不包含独立的网盘接入服务。模型说明与目录索引保持同一套记录，避免互相矛盾。
- 保留 models 现有大类，在类下按家族/作者细分；未知模型必须联网找原作者、模型卡、配套工作流等证据。`ae.safetensors` 不能只凭名字决定给谁用。
- 已有模型改名会影响工作流引用；工具保留 previous_path，不擅自批量替换所有工作流。
- node_pack_manage 操作单个包，代码检查点包含未提交文件；回退代码不等于回退共享 Python 依赖。
- systemd 管理的 ComfyUI 使用 runtime_manage；不要用官方 launch_comfyui 再起一个占用相同端口的实例。
- 扩展、技能与经验可以持续改进；记录已验证的方法和适用条件，不把一次临时故障变成永久禁令。

本扩展无 Alpha 遥测、内嵌 Claude 终端或额外聊天服务。使用云端模型的客户端仍可能发送工具结果和截图，这不是完全离线方案。
