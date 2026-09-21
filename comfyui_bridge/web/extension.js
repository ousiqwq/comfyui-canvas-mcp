import * as graph from './graph.js';
import {createStatusUI} from './status-ui.js';

// LAN HTTP lacks randomUUID even though getRandomValues is available.
if (!crypto.randomUUID) crypto.randomUUID=()=>{
  const bytes=crypto.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64; bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
};
const uuid = () => [...crypto.getRandomValues(new Uint8Array(16))].map(b=>b.toString(16).padStart(2,'0')).join('');
const clientId = uuid();
let socket, app, api, ui;
const connection = {state:'connecting', connectedAt:null, queued:0, active:null, recent:[],
  stats:{completed:0, failed:0, cached:0, disconnects:0, lastRequestAt:null}};
let chain=Promise.resolve();
const completed=new Map();
const actions={capabilities:graph.capabilities,read:graph.read,apply:graph.apply,layout:graph.layout,subgraph:graph.subgraph,
  control:graph.control,screenshot:graph.screenshot,eval:graph.evaluate,workflow:graph.workflow};
async function execute(message) {
  if (completed.has(message.id)) {
    connection.stats.cached++;
    ui?.update();
    return completed.get(message.id);
  }
  const started = performance.now();
  connection.active = message.params?.action ? `${message.action}.${message.params.action}` : message.action;
  ui?.update();
  let result;
  try {
    const before=graph.fingerprint();
    if (message.revision && message.revision!==before) throw new Error('STALE_REVISION: re-read the current graph');
    if (!actions[message.action]) throw new Error(`Unknown action ${message.action}`);
    const data=await actions[message.action](message.params);
    result={type:'result',id:message.id,ok:true,result:data,revision:graph.fingerprint(),...graph.info()};
  } catch(error) {
    console.error('[canvas-mcp]',error);
    result={type:'result',id:message.id,ok:false,error:error.message,revision:graph.fingerprint()};
  }
  completed.set(message.id,result);
  connection.stats.completed++;
  if (!result.ok) connection.stats.failed++;
  connection.stats.lastRequestAt = Date.now();
  connection.recent.push({at:Date.now(), action:connection.active, ok:result.ok,
    duration:Math.round(performance.now()-started), error:result.error?.slice(0,300)});
  if (connection.recent.length>20) connection.recent.shift();
  connection.active = null;
  ui?.update();
  if (completed.size>128) completed.delete(completed.keys().next().value);
  return result;
}
function connect() {
  const url=new URL(api.apiURL('/canvas-mcp/ws'),location.href);
  url.protocol=location.protocol==='https:'?'wss:':'ws:';
  socket=new WebSocket(url);
  socket.onopen=()=>{
    socket.send(JSON.stringify({type:'hello',client_id:clientId,info:graph.info()}));
    connection.state='connected'; connection.connectedAt=Date.now(); ui.update();
    console.info('[canvas-mcp] connected',clientId);
  };
  socket.onmessage=event=>{
    const command=JSON.parse(event.data);
    connection.queued++;
    chain=chain.then(async()=>{
      connection.queued--;
      const result=await execute(command);
      if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify(result));
    }).catch(error=>console.error('[canvas-mcp]',error));
  };
  socket.onclose=()=>{
    connection.state='disconnected'; connection.connectedAt=null; connection.stats.disconnects++;
    ui.update(); setTimeout(connect,2000);
  };
}
async function start() {
  app=window.comfyAPI?.app?.app ?? window.comfyAPI?.app;
  api=window.comfyAPI?.api?.api ?? window.comfyAPI?.api;
  if(!app?.canvas?.graph || !app?.extensionManager?.workflow?.activeWorkflow || !api?.apiURL) { setTimeout(start,250);return; }
  graph.attach(app,api);
  window.comfyCanvasMCP={clientId,read:graph.read,execute};
  ui=createStatusUI({app,api,clientId,snapshot:(includeCanvas=true)=>{
    if (!includeCanvas) return connection;
    const current=app.canvas.graph;
    return {...connection,canvas:{...graph.info(),
      link_count:current.links instanceof Map ? current.links.size : Object.keys(current.links??{}).length,
      group_count:current._groups?.length??0, selected_count:Object.keys(app.canvas.selected_nodes??{}).length,
      zoom:app.canvas.ds.scale}};
  }});
  connect();
  setInterval(()=>{if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'heartbeat',info:graph.info()}));},15000);
}
start();
