# Upstream sources

## Canvas engine

- Source: https://github.com/artokun/comfyui-mcp-panel
- Commit: `8a4b885d82a007592247bfd40e14cd8849932190`
- License: MIT, retained verbatim in `comfyui_bridge/web/vendor/PANEL-LICENSE.txt`.
- Primary source: `web/js/comfyui-mcp-panel.js`, `GRAPH_TOOL_EXECUTORS` and reachable helpers/modules.
- Generated output: `comfyui_bridge/web/vendor/panel-canvas.js`.
- Reproduction: `npm ci && npm run vendor -- /path/to/pinned/panel-checkout`.

The extractor selects 38 node/link/widget/group/layout/subgraph/screenshot/import
handlers. It excludes Panel's extension registration and all entrypoint top-level
statements; no Panel chat, terminal, agent/orchestrator or account service starts.
Reachable dependencies retain upstream compatibility code. Source provenance
comments in the generated file refer to the original modules.

Local adaptations are centralized in the extractor and `web/graph.js`:

- `initialize()` injects ComfyUI app/api; `workflowIdentity` supplies the widget
  command stamp used by Panel.
- Panel's orchestrator-specific workflow seal assertion is replaced with the
  actual current native canvas/root/workflow identity check. This bridge supplies
  client targeting, graph revision and request deduplication itself.
- Local batch transactions integrate ComfyUI's native ChangeTracker.
- Local HTTP-compatible UUID support; own tab persistence, queue submission,
  region/viewport capture, reroutes and frontend escape hatch.

Do not edit the generated vendor file directly. Change the extractor/adapter and
regenerate against the pinned checkout; review and smoke-test before a pin bump.

## Official MCP

- Source: https://github.com/Comfy-Org/comfy-mcp
- Python dependency: `comfy-mcp==0.10.0` (installed package, not vendored).
- License: upstream AGPL-3.0-or-later / commercial dual license.
- Reference reviewed: `e5f768d31de21ea32829381cebdda5336492a8ac`.
- One integration module: `src/comfy_canvas/upstream.py` imports the official
  singleton and registers our additions on it. Original tool functions stay intact.

This combined project is distributed under AGPL-3.0-or-later. Panel-derived files
retain their MIT notice; do not relicense the official dependency as MIT.

## Design reference only

https://github.com/ConstantineB6/comfy-pilot at
`772f639a7fed8513b145fb082102c7ac7837a766` was reviewed for interaction design. It is
not installed or required, and no second canvas controller is started.
