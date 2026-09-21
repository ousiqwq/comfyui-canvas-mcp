// Extract the reachable canvas code from a pinned MIT Panel checkout.
// No extension registration, chat UI, orchestrator or top-level side effects.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {parse} from 'acorn';
import {full} from 'acorn-walk';
import {build} from 'esbuild';

const root = path.resolve(process.argv[2] ?? '../references/comfyui-mcp-panel');
const pinned='8a4b885d82a007592247bfd40e14cd8849932190';
if(execFileSync('git',['-C',root,'rev-parse','HEAD'],{encoding:'utf8'}).trim()!==pinned)throw new Error('Panel checkout does not match pinned commit');
const sourceFile = path.join(root, 'web/js/comfyui-mcp-panel.js');
const source = fs.readFileSync(sourceFile, 'utf8');
const ast = parse(source, {ecmaVersion: 'latest', sourceType: 'module'});
const wanted = new Set([
  'graph_add_node','graph_remove_node','graph_clear','graph_connect','graph_disconnect',
  'graph_set_widget','graph_remove_widget','graph_set_node_property','graph_edit_node',
  'graph_move_node','graph_resize_node','graph_auto_layout','graph_canvas',
  'graph_create_group','graph_move_group','graph_edit_group','graph_remove_group',
  'graph_set_node_mode','graph_get_subgraph','graph_create_subgraph','graph_subgraph_group',
  'graph_expose_subgraph_output','graph_expose_subgraph_input',
  'graph_unexpose_subgraph_output','graph_unexpose_subgraph_input','graph_unpack_subgraph',
  'graph_copy_nodes','graph_paste_nodes','graph_save_subgraph','graph_list_subgraphs',
  'graph_add_subgraph','graph_enter_subgraph','graph_exit_subgraph','graph_move_rail',
  'graph_promote_widget','graph_screenshot','graph_load', 'refresh_nodes',
]);
const declarations = new Map();
const parts = [];
const names = node => {
  if (!node) return [];
  if (node.type === 'Identifier') return [node.name];
  if (node.type === 'ObjectPattern') return node.properties.flatMap(p => names(p.value ?? p.argument));
  if (node.type === 'ArrayPattern') return node.elements.flatMap(names);
  if (node.type === 'RestElement') return names(node.argument);
  if (node.type === 'AssignmentPattern') return names(node.left);
  return [];
};
function add(code, binds, node) {
  const item = {code, node, binds};
  parts.push(item);
  for (const name of binds) declarations.set(name, item);
}
for (const statement of ast.body) {
  if (statement.type === 'ImportDeclaration') {
    for (const spec of statement.specifiers) {
      const name = spec.local.name;
      const location = statement.source.value.startsWith('.') ? path.resolve(path.dirname(sourceFile), statement.source.value).replaceAll('\\','/') : statement.source.value;
      const what = spec.type === 'ImportDefaultSpecifier' ? name : spec.type === 'ImportNamespaceSpecifier' ? `* as ${name}` : `{${spec.imported.name} as ${name}}`;
      add(`import ${what} from ${JSON.stringify(location)};`, [name], null);
    }
  } else if (statement.type === 'VariableDeclaration') {
    for (const decl of statement.declarations) {
      if (decl.id.name === 'GRAPH_TOOL_EXECUTORS') {
        const kept = decl.init.properties.filter(p => wanted.has(p.key.name ?? p.key.value));
        const code = `const GRAPH_TOOL_EXECUTORS = {${kept.map(p => source.slice(p.start,p.end)).join(',\n')}};`;
        add(code, ['GRAPH_TOOL_EXECUTORS'], parse(code,{ecmaVersion:'latest',sourceType:'module'}));
      } else add(`${statement.kind} ${source.slice(decl.start,decl.end)};`, names(decl.id), decl);
    }
  } else if (statement.type === 'FunctionDeclaration' || statement.type === 'ClassDeclaration') {
    if(statement.id.name==='assertGraphBoundToActiveWorkflow'){
      // Panel's retired orchestrator owns a separate workflow UUID/seal. This
      // bridge binds client + native workflow/graph revision instead. Keep the
      // actual canvas identity check, not the unavailable orchestrator's seal.
      const code=`function assertGraphBoundToActiveWorkflow(graph,rootGraph) {
        if(rootGraph!==app.rootGraph || graph!==app.canvas.graph || !app.extensionManager.workflow.activeWorkflow)
          throw new Error('Canvas target changed; read and bind the current graph again');
      }`;
      add(code,[statement.id.name],parse(code,{ecmaVersion:'latest',sourceType:'module'}));
    }else add(source.slice(statement.start,statement.end), [statement.id.name], statement);
  }
}
const included = new Set();
function visit(name) {
  const item = declarations.get(name);
  if (!item || included.has(item)) return;
  included.add(item);
  if (item.node) full(item.node, n => { if (n.type === 'Identifier') visit(n.name); });
}
visit('GRAPH_TOOL_EXECUTORS');
visit('app'); visit('api');
visit('workflowStableUuid');
const entry = parts.filter(x => included.has(x)).map(x=>x.code).join('\n') + `
export function initialize(comfyApp, comfyApi) { app = comfyApp; api = comfyApi; }
export const commands = GRAPH_TOOL_EXECUTORS;
export const workflowIdentity = workflowStableUuid;
`;
fs.mkdirSync('.build',{recursive:true});
fs.writeFileSync('.build/panel-entry.js', entry);
fs.mkdirSync('comfyui_bridge/web/vendor',{recursive:true});
await build({stdin:{contents:entry,resolveDir:root,sourcefile:'panel-canvas-extract.js'},bundle:true,format:'esm',target:'es2022',outfile:'comfyui_bridge/web/vendor/panel-canvas.js',legalComments:'eof',minify:false,treeShaking:true,banner:{js:'// Derived from artokun/comfyui-mcp-panel @ 8a4b885d82a007592247bfd40e14cd8849932190 (MIT).\n// Generated by scripts/vendor-panel.mjs; see THIRD_PARTY.md.'}});
fs.copyFileSync(path.join(root,'LICENSE'),'comfyui_bridge/web/vendor/PANEL-LICENSE.txt');
console.log(`Extracted ${wanted.size} canvas handlers; ${included.size} reachable declarations.`);
