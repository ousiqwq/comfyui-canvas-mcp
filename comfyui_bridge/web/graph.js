import {commands, initialize, workflowIdentity} from './vendor/panel-canvas.js';

let app, api;
const errors=[];
let userActivity=0;
document.addEventListener('pointerdown',()=>userActivity++,true);
document.addEventListener('keydown',()=>userActivity++,true);
export function attach(comfyApp, comfyApi) {
  app = comfyApp; api = comfyApi; initialize(app, api);
  for(const event of ['execution_error','execution_interrupted']) api.addEventListener(event,e=>{
    errors.push({event,...e.detail}); if(errors.length>20)errors.shift();
  });
}
export function capabilities() {
  return Object.fromEntries(Object.entries({...commands,...extraOperations}).map(([name,fn])=>[name,fn.toString().split(/\)\s*\{/)[0]+')']));
}
export function context() { return {app, api, graph: app.canvas.graph, canvas: app.canvas}; }
const clone = x => JSON.parse(JSON.stringify(x));
const pair = x => [Number(x[0]), Number(x[1])];
export function fingerprint() {
  const state=app.graph.serialize();
  if(state.extra){state.extra={...state.extra};delete state.extra.comfyui_mcp;delete state.extra.ds;}
  const text = JSON.stringify([app.extensionManager.workflow.activeWorkflow?.path, app.canvas.graph.id, state]);
  let value = 2166136261;
  for (let i = 0; i < text.length; i++) value = Math.imul(value ^ text.charCodeAt(i), 16777619);
  return (value >>> 0).toString(16);
}
export function info() {
  const workflow = app.extensionManager.workflow.activeWorkflow;
  const paths=[];
  function visit(graph,path,seen){
    if(graph===app.canvas.graph)paths.push(path);
    if(seen.has(graph))return;
    const next=new Set(seen).add(graph);
    for(const node of graph._nodes??[])if(node.subgraph)visit(node.subgraph,[...path,String(node.id)],next);
  }
  visit(app.rootGraph,[],new Set());
  return {workflow: workflow?.path ?? 'unsaved', workflow_id: app.graph.id ?? app.graph._id ?? null,
    graph_id: app.canvas.graph.id ?? app.canvas.graph._id ?? null,
    graph_paths:paths,
    node_count: app.canvas.graph._nodes.length, revision: fingerprint(), visible: !document.hidden};
}
export function nodeInfo(node) {
  node.updateArea?.();
  const bounds = node.getBounding(new Float32Array(4));
  return {id: node.id, type: node.type, title: node.title, pos: pair(node.pos), size: pair(node.size),
    bounds: Array.from(bounds), mode: node.mode, flags: {...node.flags}, color: node.color,
    shape: node.shape, selected: !!app.canvas.selected_nodes?.[node.id], properties: clone(node.properties ?? {}),
    widgets: (node.widgets ?? []).map((w, index) => ({index,name:w.name,type:w.type,value:w.value,
      choices: Array.isArray(w.options?.values) ? w.options.values : undefined})),
    inputs: clone(node.inputs ?? []), outputs: clone(node.outputs ?? [])};
}
export function read({mode='outline', ids, types, title, offset=0, limit=100}={}) {
  const {graph, canvas} = context();
  if (mode === 'full') return {ui: app.graph.serialize(), ...info()};
  if (mode === 'errors') return {events:errors,validation:app.lastNodeErrors??null,...info()};
  const rect = canvas.canvas.getBoundingClientRect();
  const viewport = {x:-canvas.ds.offset[0], y:-canvas.ds.offset[1], width:rect.width/canvas.ds.scale,
    height:rect.height/canvas.ds.scale, zoom:canvas.ds.scale, dpr:devicePixelRatio,
    css_bounds:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},offset:pair(canvas.ds.offset)};
  const selected = new Set([...(canvas.selectedItems ?? []), ...Object.values(canvas.selected_nodes ?? {})]);
  let nodes = graph._nodes.filter(n => (!ids || ids.map(String).includes(String(n.id))) &&
    (!types || types.includes(n.type)) && (!title || String(n.title).toLowerCase().includes(title.toLowerCase())) &&
    (mode !== 'selected' || selected.has(n)));
  if (mode === 'viewport') nodes = nodes.filter(n => {
    const [x,y,w,h] = n.getBounding(new Float32Array(4));
    return x+w>viewport.x && x<viewport.x+viewport.width && y+h>viewport.y && y<viewport.y+viewport.height;
  });
  const links = graph.links instanceof Map ? [...graph.links.values()] : Object.values(graph.links ?? {});
  const groups = graph._groups.map(g => ({id:g.id,title:g.title,color:g.color,font_size:g.font_size,
    bounds:Array.from(g._bounding), node_ids:graph._nodes.filter(n=>{
      const [x,y,w,h]=g._bounding; return n.pos[0]>=x && n.pos[1]>=y && n.pos[0]<x+w && n.pos[1]<y+h;
    }).map(n=>n.id)}));
  return {...info(), viewport, total:nodes.length, offset, truncated:offset+limit<nodes.length,
    nodes:nodes.slice(offset,offset+limit).map(nodeInfo), links:clone(links), groups,
    reroutes:clone(graph.serialize().reroutes??[]),
    rails:Object.fromEntries([['input',graph.inputNode],['output',graph.outputNode]].filter(([,n])=>n).map(([kind,n])=>[kind,{id:n.id,pos:pair(n.pos),size:pair(n.size)}]))};
}

const operations = {
  add:'graph_add_node', remove:'graph_remove_node', clear:'graph_clear', edit:'graph_edit_node',
  move:'graph_move_node', resize:'graph_resize_node', set_widget:'graph_set_widget',
  remove_widget:'graph_remove_widget', set_property:'graph_set_node_property', set_mode:'graph_set_node_mode',
  connect:'graph_connect', disconnect:'graph_disconnect', copy:'graph_copy_nodes', paste:'graph_paste_nodes',
  create_group:'graph_create_group', move_group:'graph_move_group', edit_group:'graph_edit_group', remove_group:'graph_remove_group',
};
const extraOperations={
  reroute_add({link_id,pos}){
    const graph=context().graph, link=graph.links instanceof Map?graph.links.get(link_id):graph.links[link_id];
    if(!link)throw new Error('link_id not found');
    const reroute=graph.createReroute(pos,link);
    if(!reroute)throw new Error('Native reroute creation unsupported by this frontend');
    return {id:reroute.id,pos:pair(reroute.pos)};
  },
  reroute_move({reroute_id,pos}){
    const reroute=context().graph.getReroute(reroute_id);
    if(!reroute)throw new Error('reroute_id not found');
    reroute.pos[0]=pos[0];reroute.pos[1]=pos[1];
    return {id:reroute.id,pos:pair(reroute.pos)};
  },
  reroute_remove({reroute_id}){context().graph.removeReroute(reroute_id);return {removed:reroute_id};},
  widget_to_input({node_id,widget}){
    const node=context().graph.getNodeById(node_id),w=node.widgets.find(w=>w.name===widget);
    if(!w)throw new Error('Widget not found');
    let slot=node.inputs?.findIndex(i=>i.name===widget);
    if(slot>=0)return {coexists:true,input_index:slot,widget};
    node.convertWidgetToInput(w);
    slot=node.inputs?.findIndex(i=>i.name===widget);
    if(!(slot>=0))throw new Error('Frontend did not expose widget input');
    return {input_index:slot,widget};
  },
  input_to_widget({node_id,widget}){
    const node=context().graph.getNodeById(node_id),slot=node.inputs?.findIndex(i=>i.name===widget);
    if(!node.widgets?.some(w=>w.name===widget))throw new Error('No backing widget; cannot invent one');
    if(slot>=0)node.disconnectInput(slot);
    return {widget,coexists:true,note:'Modern frontend keeps widget and input together; disconnected the input.'};
  },
};
export async function transaction(work) {
  const {graph} = context();
  const workflow=app.extensionManager.workflow.activeWorkflow;
  const activity=userActivity;
  const tracker=workflow.changeTracker;
  tracker.captureCanvasState();
  const before = clone(app.graph.serialize());
  // Panel commands already call beforeChange/afterChange. Collapse those into one pair.
  const beforeChange = graph.beforeChange;
  const afterChange = graph.afterChange;
  tracker.beforeChange();
  graph.beforeChange = () => {};
  graph.afterChange = () => {};
  try { return await work(); }
  catch (error) {
    if(userActivity!==activity||app.extensionManager.workflow.activeWorkflow!==workflow)throw new Error(`Partial batch; user/target changed, no whole-graph rollback applied: ${error.message}`);
    await app.loadGraphData(before,false,false,workflow);
    throw new Error(`Batch failed; restored graph snapshot: ${error.message}`);
  } finally {
    graph.beforeChange = beforeChange;
    graph.afterChange = afterChange;
    if(app.extensionManager.workflow.activeWorkflow===workflow){tracker.activeState=before;tracker.afterChange();}
    else tracker.changeCount=Math.max(0,tracker.changeCount-1);
    app.canvas.setDirty(true,true);
  }
}
export async function apply({operations: batch}) {
  const aliases = {};
  const resolve = value => typeof value === 'string' && value.startsWith('$') ? aliases[value.slice(1)] :
    Array.isArray(value) ? value.map(resolve) : value && typeof value === 'object' ?
      Object.fromEntries(Object.entries(value).map(([k,v])=>[k,resolve(v)])) : value;
  return transaction(async()=>{
    const results=[];
    for (const operation of batch) {
      const {op,as,...args} = resolve(operation);
      const name=operations[op];
      const fn=extraOperations[op]??commands[name];
      if (!fn) throw new Error(`Unknown operation ${op}; supported: ${Object.keys(operations).join(', ')}`);
      const result=await fn({...args,workflow_uuid:workflowIdentity()});
      if(result?.error || (result?.applied===false&&!result?.unchanged)) throw new Error(JSON.stringify(result));
      // Panel validates graph/workflow correspondence on each command. Keep its
      // live baseline current while the outer tracker owns the single undo entry.
      app.extensionManager.workflow.activeWorkflow.changeTracker.activeState=clone(app.graph.serialize());
      if (as) aliases[as]=result.added?.id ?? result.pasted?.[0]?.id;
      results.push(result);
    }
    return {results, aliases, revision:fingerprint()};
  });
}
export async function layout(params) {
  const {action='auto',node_ids,grid=20,...args}=params;
  const nodes=context().graph._nodes.filter(n=>!n.flags?.pinned && (!node_ids || node_ids.map(String).includes(String(n.id))));
  if(action==='collisions'){
    const overlaps=[];
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i].getBounding(), b=nodes[j].getBounding();
      if(a[0]<b[0]+b[2]&&a[0]+a[2]>b[0]&&a[1]<b[1]+b[3]&&a[1]+a[3]>b[1])overlaps.push([nodes[i].id,nodes[j].id]);
    }
    return {overlaps};
  }
  if (action==='auto') {
    const fixed=context().graph._nodes.filter(n=>n.flags?.pinned).map(n=>({n,pos:pair(n.pos)}));
    const result=await commands.graph_auto_layout({node_ids,...args});
    if(!params.dry_run)for(const {n,pos} of fixed)n.pos=pos;
    return result;
  }
  if(action==='relative'){
    const anchor=context().graph.getNodeById(args.anchor_id);
    if(!anchor)throw new Error('anchor_id not found');
    const moves=nodes.filter(n=>n!==anchor).map(n=>({op:'move',node_id:n.id,pos:[anchor.pos[0]+(args.offset?.[0]??350),anchor.pos[1]+(args.offset?.[1]??0)]}));
    return params.dry_run?{applied:false,moves}:apply({operations:moves});
  }
  if (!nodes.length) return {moved:[]};
  const axis=action.endsWith('_y') ? 1 : 0;
  const sorted=[...nodes].sort((a,b)=>a.pos[axis]-b.pos[axis]);
  const start=sorted[0].pos[axis], end=sorted.at(-1).pos[axis];
  const moves=sorted.map((n,index)=>{
    const pos=pair(n.pos);
    if (action==='snap') { pos[0]=Math.round(pos[0]/grid)*grid; pos[1]=Math.round(pos[1]/grid)*grid; }
    else if (action.startsWith('align')) pos[axis]=start;
    else if (action.startsWith('distribute')) pos[axis]=start+(end-start)*index/Math.max(1,sorted.length-1);
    else throw new Error('action: auto, snap, align_x, align_y, distribute_x, distribute_y');
    return {op:'move',node_id:n.id,pos};
  });
  return params.dry_run ? {applied:false,moves} : apply({operations:moves});
}
const subgraphCommands={create:'graph_create_subgraph',from_group:'graph_subgraph_group',inspect:'graph_get_subgraph',
  enter:'graph_enter_subgraph',exit:'graph_exit_subgraph',unpack:'graph_unpack_subgraph',
  expose_input:'graph_expose_subgraph_input',expose_output:'graph_expose_subgraph_output',
  unexpose_input:'graph_unexpose_subgraph_input',unexpose_output:'graph_unexpose_subgraph_output',
  move_rail:'graph_move_rail',promote_widget:'graph_promote_widget',save:'graph_save_subgraph',list:'graph_list_subgraphs',add:'graph_add_subgraph'};
export async function subgraph({action,...args}) {
  const fn=commands[subgraphCommands[action]];
  if (!fn) throw new Error(`Unknown subgraph action; choose ${Object.keys(subgraphCommands)}`);
  return fn(args);
}
export async function control({action,...args}) {
  if (action==='run') {
    const prompt=await app.graphToPrompt();
    const target=args.to_node_id==null?null:String(args.to_node_id);
    if(target&&!prompt.output[target])throw new Error('Target must be a root output node in the executable prompt');
    if(target){
      const definitions=await api.getNodeDefs();
      if(!definitions[prompt.output[target].class_type]?.output_node)throw new Error('Partial run target must be an output node');
    }
    const results=[];
    for(let i=0;i<(args.batch_count??1);i++)results.push(await api.queuePrompt(0,prompt,target?{partialExecutionTargets:[target]}:undefined));
    return {queued:true,prompts:results,partial_execution_targets:target?[target]:null};
  }
  if(action==='interrupt'){
    if(!args.prompt_id)throw new Error('prompt_id required');
    const queue=await api.getQueue();
    const running=queue.Running??queue.queue_running??[];
    if(!running.some(item=>String(item.prompt?.[1]??item[1])===String(args.prompt_id)))throw new Error('Requested prompt is not running; refusing to interrupt another job');
    await api.interrupt();return {interrupted:args.prompt_id};
  }
  if (action==='refresh_nodes') return commands.refresh_nodes();
  if (action==='select') {
    const nodes=context().graph._nodes.filter(n=>args.node_ids.map(String).includes(String(n.id)));
    app.canvas.selectItems(nodes); return {selected:nodes.map(n=>n.id)};
  }
  if (action==='undo' || action==='redo') {
    const tracker=app.extensionManager.workflow.activeWorkflow.changeTracker;
    await tracker[action](); return read();
  }
  if (action==='clear') return apply({operations:[{op:'clear'}]});
  return commands.graph_canvas({action,...args});
}
export async function screenshot({mode='full',bounds,node_ids,padding=60}={}) {
  if(mode==='full')return commands.graph_screenshot({padding});
  const {canvas,graph}=context(), cv=canvas.canvas, ds=canvas.ds;
  if(mode==='nodes'){
    const boxes=graph._nodes.filter(n=>node_ids.map(String).includes(String(n.id))).map(n=>Array.from(n.getBounding()));
    if(!boxes.length)throw new Error('No nodes matched');
    const x=Math.min(...boxes.map(b=>b[0])),y=Math.min(...boxes.map(b=>b[1]));
    bounds=[x,y,Math.max(...boxes.map(b=>b[0]+b[2]))-x,Math.max(...boxes.map(b=>b[1]+b[3]))-y];
  }
  const saved={scale:ds.scale,offset:pair(ds.offset)},LG=window.LiteGraph??window.comfyAPI?.litegraph?.LiteGraph;
  const vue=LG?.vueNodesMode;
  try{
    if(LG&&typeof vue==='boolean')LG.vueNodesMode=false;
    if(mode!=='viewport'){
      if(!bounds||bounds.length!==4)throw new Error('bounds:[x,y,width,height] required');
      const rect=cv.getBoundingClientRect();
      ds.scale=Math.min((rect.width-2*padding)/Math.max(1,bounds[2]),(rect.height-2*padding)/Math.max(1,bounds[3]));
      ds.offset[0]=-bounds[0]+padding/ds.scale;ds.offset[1]=-bounds[1]+padding/ds.scale;
    }
    canvas.setDirty(true,true);canvas.draw(true,true);
    return {data_url:cv.toDataURL('image/png'),bounds:bounds??read().viewport,width:cv.width,height:cv.height,mode};
  }finally{
    if(LG&&typeof vue==='boolean')LG.vueNodesMode=vue;
    ds.scale=saved.scale;ds.offset[0]=saved.offset[0];ds.offset[1]=saved.offset[1];canvas.setDirty(true,true);
  }
}
export async function evaluate({code}) {
  const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
  const result=await new AsyncFunction('app','api','LiteGraph','commands',code)(app,api,window.LiteGraph,commands);
  app.canvas.setDirty(true,true);
  return result ?? null;
}
export async function workflow({action,path,name,graph,force=false}) {
  const store=app.extensionManager.workflow;
  if (action==='list') return {active:store.activeWorkflow?.path,open:store.openWorkflows.map(w=>({path:w.path,isModified:w.isModified})),files:await api.listUserDataFullInfo('workflows')};
  if (action==='new') { await app.extensionManager.command.execute('Comfy.NewBlankWorkflow'); return info(); }
  if (action==='load') { const loaded=await commands.graph_load({graph}); return {...loaded,...info()}; }
  if (action==='export') return {ui:app.graph.serialize(),prompt:await app.graphToPrompt()};
  if (action==='save' || action==='save_as') {
    const file=path ?? name ?? store.activeWorkflow?.path;
    if (!file || file.includes('Unsaved')) throw new Error('Provide path for the first save');
    const destination=file.startsWith('workflows/')?file:`workflows/${file.endsWith('.json')?file:file+'.json'}`;
    const snapshot=clone(app.graph.serialize());
    const response=await api.storeUserData(destination,snapshot,{overwrite:action==='save'||force,stringify:true,throwOnError:true,full_info:true});
    if (!response.ok) throw new Error(await response.text());
    await store.loadWorkflows();
    const saved=store.getWorkflowByPath(destination);
    if(saved){await saved.load({force:true});await app.loadGraphData(snapshot,true,false,saved);}
    return {saved:true,path:destination,revision:fingerprint()};
  }
  if (action==='open' || action==='switch') {
    const open=store.openWorkflows.find(w=>w.path===path);
    if (open) {
      await store.openWorkflow(open);
      await app.loadGraphData(open.activeState,false,false,open);
    } else {
      const response=await api.getUserData(path.startsWith('workflows/')?path:`workflows/${path}`);
      if (!response.ok) throw new Error(await response.text());
      await store.loadWorkflows();
      const destination=path.startsWith('workflows/')?path:`workflows/${path}`;
      const saved=store.getWorkflowByPath(destination);
      if(saved)await saved.load();
      await app.loadGraphData(await response.json(),true,false,saved??path.replace(/^workflows\//,''));
    }
    return info();
  }
  const target=store.openWorkflows.find(w=>w.path===path) ?? store.activeWorkflow;
  if (action==='close') {
    if (target.isModified && !force) throw new Error('Unsaved workflow; save first or pass force:true');
    await store.closeWorkflow(target); return info();
  }
  if (action==='rename') {
    if(!name)throw new Error('name required');
    const destination=name.startsWith('workflows/')?name:`workflows/${name.endsWith('.json')?name:name+'.json'}`;
    await store.renameWorkflow(target,destination); return info();
  }
  throw new Error('Unknown workflow action');
}
