import * as graph from './graph.js';

// LAN HTTP lacks randomUUID even though getRandomValues is available.
if (!crypto.randomUUID) crypto.randomUUID=()=>{
  const bytes=crypto.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&15)|64; bytes[8]=(bytes[8]&63)|128;
  const hex=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
};
const uuid = () => [...crypto.getRandomValues(new Uint8Array(16))].map(b=>b.toString(16).padStart(2,'0')).join('');
const clientId = uuid();
let socket, app, api, badge;
let chain=Promise.resolve();
const completed=new Map();
const actions={capabilities:graph.capabilities,read:graph.read,apply:graph.apply,layout:graph.layout,subgraph:graph.subgraph,
  control:graph.control,screenshot:graph.screenshot,eval:graph.evaluate,workflow:graph.workflow};
async function execute(message) {
  if (completed.has(message.id)) return completed.get(message.id);
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
  if(badge)badge.title=`Client: ${clientId}\n${graph.info().workflow}\nLast: ${message.action} ${result.ok?'OK':result.error}`;
  if (completed.size>128) completed.delete(completed.keys().next().value);
  return result;
}
function connect() {
  const url=new URL(api.apiURL('/canvas-mcp/ws'),location.href);
  url.protocol=location.protocol==='https:'?'wss:':'ws:';
  socket=new WebSocket(url);
  socket.onopen=()=>{socket.send(JSON.stringify({type:'hello',client_id:clientId,info:graph.info()}));badge.textContent='MCP ●';badge.style.color='#8fce9b';console.info('[canvas-mcp] connected',clientId);};
  socket.onmessage=event=>{
    const command=JSON.parse(event.data);
    chain=chain.then(async()=>{
      const result=await execute(command);
      if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify(result));
    }).catch(error=>console.error('[canvas-mcp]',error));
  };
  socket.onclose=()=>{badge.textContent='MCP ○';badge.style.color='#e0b574';setTimeout(connect,2000);};
}
async function start() {
  app=window.comfyAPI?.app?.app ?? window.comfyAPI?.app;
  api=window.comfyAPI?.api?.api ?? window.comfyAPI?.api;
  if(!app?.canvas?.graph || !app?.extensionManager?.workflow?.activeWorkflow || !api?.apiURL) { setTimeout(start,250);return; }
  graph.attach(app,api);
  window.comfyCanvasMCP={clientId,read:graph.read,execute};
  badge=document.createElement('button');badge.textContent='MCP ○';badge.title=`Client: ${clientId}`;
  badge.style.cssText='position:fixed;bottom:8px;right:12px;z-index:1000;background:#20242acc;border:1px solid #5c6570;border-radius:5px;padding:4px 8px;font:12px monospace;cursor:pointer';
  badge.onclick=()=>window.prompt('Use this client_id to target this browser tab:',clientId);
  document.body.append(badge);
  connect();
  setInterval(()=>{if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'heartbeat',info:graph.info()}));},15000);
}
start();
