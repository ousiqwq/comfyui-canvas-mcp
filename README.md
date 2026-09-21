# ComfyUI Canvas MCP

让外部 Agent 直接读取、编辑**浏览器中正在打开的 ComfyUI 画布**，同时保留官方 Comfy MCP 的无头执行工具。

节点位置来自图数据的 `pos/size/bounds`，连接使用节点 ID 和插槽名称/索引，不靠截图猜位置。修改即时反映到目标浏览器。没有内嵌 Claude 终端、第二个聊天 Agent、云中转或 Alpha 会话遥测。

```text
MCP client → comfy-mcp-local (stdio)
                      ├─ official comfy-mcp → comfy-cli / ComfyUI API
                      ├─ canvas tools → ComfyUI same-port bridge → real browser graph
                      └─ local management → existing catalog / Manager / Git / user systemd
```

## 功能

保留固定版本官方全部工具；新增 15 组入口（不是 15 个独立功能）：

| 工具 | 用途 |
|---|---|
| canvas_status / canvas_read | 页面绑定、实际坐标、选区、视口、节点参数、连线、分组、reroute、错误 |
| canvas_apply | 批量增删改节点、动态 widget、连接、分组、复制粘贴、原生 reroute；一个撤销单元 |
| canvas_layout | Panel 拓扑布局、组约束、固定节点、对齐、分布、网格、相对位置、碰撞检查、预览 |
| canvas_subgraph | 创建/进入/退出/解包子图，输入输出暴露、widget 提升、边界 Rail、蓝图 |
| canvas_workflow | 工作流标签、保存/另存/打开/切换、UI/API 导入导出、磁盘检查点及恢复 |
| canvas_control / canvas_screenshot | 视角、撤销重做、当前画布/指定输出运行、中断指定任务；全图/视口/区域截图 |
| canvas_eval | 开放的异步前端 JavaScript，供新增功能和临时适配使用 |
| workflow_tools / workflow_media | 结构 diff、分析、切片、清理、重建/扁平化；媒体元数据恢复 |
| model_catalog | 模型说明文件与目录索引，检查、流式哈希、分类、改名、移动、重复候选、配套清单 |
| node_pack_manage | 单包 Manager 操作、代码检查点与回退，正确运行环境 |
| environment_snapshot | 版本清单、可恢复实体归档、差异与独立恢复程序 |
| runtime_manage | 已有 systemd 用户服务及真实 journal，不另起 ComfyUI |

当前固定依赖版本的工具数量为 **39 个官方 + 15 个新增 = 54 个**。以 `tools/list` 为准。

## Ubuntu 安装

需要已有可运行的 ComfyUI、独立 tools Python，以及 systemd 用户会话。下面两个 Python **不要填反**。项目须保留为源码安装，前端资源和恢复脚本直接从此目录使用。

```bash
git clone https://github.com/ousiqwq/comfyui-canvas-mcp.git
cd comfyui-canvas-mcp

# 替换为自己的绝对路径；工具环境与 ComfyUI 的 torch 环境分开
TOOLS="/path/to/tools-env/bin/python"
RUNTIME="/path/to/comfyui-env/bin/python"
COMFY_ROOT="/path/to/ComfyUI"
"$TOOLS" -m pip install -e .

# 新增扩展链接和本机配置，不修改模型与工作流
"$TOOLS" scripts/install.py \
  --root "$COMFY_ROOT" \
  --runtime-python "$RUNTIME"

# 使用 systemd 用户服务时，确认没有正在执行的任务后重启
systemctl --user restart comfyui.service
```

然后**刷新一次 ComfyUI 网页**，右下角出现绿色 `MCP ●`。点击可查看此页面的 client_id。之后正常使用不需要刷新，也不需要额外常驻 Node 服务。

### 连接 MCP 客户端

将原来官方 `comfy-mcp` 的入口替换为同一工具环境中的 `comfy-mcp-local`；无需再注册第二套官方工具。以下为常见客户端的配置形式，具体顶层字段以客户端要求为准：

```json
{
  "mcpServers": {
    "comfyui": {
      "command": "/path/to/tools-env/bin/comfy-mcp-local",
      "env": {
        "COMFY_BIN": "/path/to/tools-env/bin/comfy",
        "COMFY_LOCAL_URL": "http://127.0.0.1:8188",
        "COMFY_CANVAS_CONFIG": "/path/to/canvas-config.json",
        "CONDA_PREFIX": "/path/to/comfyui-env",
        "VIRTUAL_ENV": ""
      }
    }
  }
}
```

`COMFY_CANVAS_CONFIG` 应指向安装器生成的本机配置，默认位于 `~/.config/comfyui-canvas-mcp/config.json`。其中支持 root、runtime_python、comfy_bin、url、service、state、model_catalog；使用快照功能时，可用 hermes_service 指定额外需要停启的用户服务，不需要则设为 `""`。

可选的 Hermes 集成：安装时添加 `--hermes`，只合并 `mcp_servers.comfyui`。然后重启该客户端，用 `hermes mcp test comfyui` 检查连接。其他客户端按其 MCP 设置界面配置即可。

依赖/源码版本说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。预生成前端已提交，普通安装不需要 Node/npm；只有重提取 Panel 时才需要 `npm ci`。

## 怎么让 Agent 使用

将 [操作指南](docs/agent-guide.md) 作为 MCP 客户端或 Agent 的参考资料。指南只描述本插件与官方 MCP 的配合，不要求额外的下载技能或私人服务。

可以直接说：

> 看我当前打开的 ComfyUI 画布，读取实际节点和参数，把节点整理为从左到右，再告诉我哪些模型缺失。先不要运行。

> 在新工作流标签中构建工作流，改完读回校验，保存，然后运行并取回结果。

多个浏览器页面同时打开时，先 `canvas_status` 选择目标，一次绑定；不会向所有页面广播修改。刷新页面后 client_id 更新，需要重新绑定。

## 备份与恢复

- 普通画布批次用原生撤销；大改前用 `canvas_workflow(action="checkpoint")` 保存 UI JSON。
- `environment_snapshot(mode="manifest")` **只是版本清单**，不是完整环境备份。
- `mode="restorable"` 才归档选中的 `code/runtime/tools/bridge` 实体文件。大环境可能占用几十 GB，先确认空间和空闲窗口。捕获期间临时停启配置的用户服务；独立 transient user service 执行，不依赖 MCP 客户端进程存活。
- 不包含模型权重、input/output 媒体或独立存放的客户端对话数据库；这不是整机备份工具。
- 恢复仅承诺**同机、同架构、原绝对路径**。先校验 SHA-256、解包，再切换目录，旧目录保留为 `.before-restore-*`。可选的 Hermes 集成只合并 comfyui MCP 项，不覆盖其他客户端设置。
- 快照、任务日志与模型来源记录属于本机运行数据，可能含绝对路径、服务参数或凭据；不要提交到公开仓库。

```bash
/usr/bin/python3 /path/to/snapshot/restore.py /path/to/snapshot
# 确认目标和校验结果后
/usr/bin/python3 /path/to/snapshot/restore.py /path/to/snapshot --apply
```

也可用 `environment_snapshot restore_plan/restore`。恢复日志和结果文件不依赖 MCP 连接；重连后检查 `restore-result.json`、服务日志和实际工作流。通过验证前不要删除反向备份。

## 验证与开发

不是大型测试框架。`scripts/smoke.py` 做 MCP 握手/官方状态回归；加 `--edit` 会在**新标签**创建无模型的 64×64 测试工作流，验证编辑、连线、一次撤销、布局预览、保存和提交。它不会下载或加载大模型。运行前只保留或绑定测试页面，勿误选用户其他页面。

```bash
"/path/to/tools-env/bin/python" scripts/smoke.py --edit
```

代码按 canvas / workflows / media / models / nodepacks / snapshots / runtime 分模块；ComfyUI 版本相关的接口集中于 `comfyui_bridge/web/graph.js`。新增画布动作在那里实现，再注册简洁 MCP schema；不需要修改官方 MCP。

## 真实边界

- 这是可信内网工具。开放 eval 和本地管理能力，不应把桥接端口直接暴露到公网。
- 页面关闭或冻结时无法同屏编辑；官方无头工具仍能工作。
- 返回超时不代表没执行。不要盲目重发生成任务；request_id 只在当前服务的短期缓存内去重。
- 画布撤销不撤销已提交任务、下载、安装或任意 JS 的外部副作用。
- API JSON 不含原布局；转换和扁平化会重建排版，子图/自定义节点以实际前端能导出的 prompt 为限。
- 没有工作流元数据的图片/视频不能恢复原工作流。视频检查需要系统 `ffprobe`。
- 单包代码回退不等于共享 Python 环境回退。
- 本扩展不增加遥测；使用云端模型的 MCP 客户端仍可能发送工具结果和截图。官方依赖自身设置由使用者管理。

## 回退部署

把 MCP 客户端的 command 改回工具环境中的 `bin/comfy-mcp`，重新连接客户端。桥接链接可在确认指向本项目后取消链接；不删除 ComfyUI、模型或工作流。重启 ComfyUI 并刷新浏览器后回到原有行为。使用可选 Hermes 安装时，安装前的配置副本留在 `.hermes/config.yaml.before-canvas-*`，只恢复需要的 MCP 项。

AGPL-3.0-or-later；Panel 衍生文件保留 MIT 声明。详见 [LICENSE](LICENSE)。
