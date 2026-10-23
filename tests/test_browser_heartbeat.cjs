const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('dist/keep-alive.js','utf8');
const listeners={},windowListeners={},nodes=new Map(),requests=[],intervals=new Map();let now=1000000,nextTimer=1;
function node(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',disabled:false});return nodes.get(id)}
class TestDate extends Date{constructor(...args){super(...(args.length?args:[now]))}static now(){return now}}
const document={visibilityState:'visible',querySelector:node,getElementById:id=>node('#'+id),addEventListener:(name,fn)=>listeners[name]=fn};
const context=vm.createContext({document,window:{location:{hostname:'dashboard.chatgpt.site',origin:'https://dashboard.chatgpt.site'},addEventListener:(name,fn)=>windowListeners[name]=fn},gateway:'https://wmm-test.onrender.com',AbortController,Date:TestDate,fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({ok:true,service:'teamradar'})}},setInterval:(fn,ms)=>{const id=nextTimer++;intervals.set(id,{fn,ms});return id},clearInterval:id=>intervals.delete(id),setTimeout:()=>nextTimer++,clearTimeout(){},action(){},navigator:{clipboard:{}},Error});
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve()};
(async()=>{
 vm.runInContext(code,context);listeners.DOMContentLoaded();await flush();assert.equal(requests.length,1);assert.equal(requests[0].url,'https://wmm-test.onrender.com/api/health');assert.equal(requests[0].options.cache,'no-store');assert.equal(requests[0].options.credentials,'omit');assert.equal(requests[0].options.headers,undefined);assert.match(node('#activeHeartbeatStatus').textContent,/active/);
 const interval=[...intervals.values()][0];assert.equal(interval.ms,600000);vm.runInContext('renderKeepAliveSetup()',context);await flush();assert.equal(requests.length,1);
 now+=600000;await interval.fn();await flush();assert.equal(requests.length,2);
 document.visibilityState='hidden';now+=600000;listeners.visibilitychange();await interval.fn();await flush();assert.equal(requests.length,2);assert.match(node('#activeHeartbeatStatus').textContent,/paused/);
 document.visibilityState='visible';listeners.visibilitychange();await flush();assert.equal(requests.length,3);
 windowListeners.pagehide();assert.equal(intervals.size,0);windowListeners.pageshow();await flush();assert.equal(intervals.size,1);
 context.gateway='';context.window.location={hostname:'dashboard.chatgpt.site',origin:'https://dashboard.chatgpt.site'};now+=600000;await [...intervals.values()][0].fn();await flush();assert.equal(requests.length,4);
 context.window.location={hostname:'wmm-test.onrender.com',origin:'https://wmm-test.onrender.com'};await [...intervals.values()][0].fn();await flush();assert.equal(requests.length,5);
 context.fetch=async(url,options)=>{requests.push({url,options});return {status:url.endsWith('/api/health')?404:200,ok:!url.endsWith('/api/health'),json:async()=>({ok:true,service:'teamradar'})}};await vm.runInContext('pingWhileVisible(true)',context);assert.equal(requests.at(-1).url,'https://wmm-test.onrender.com/health');assert.equal(requests.at(-1).options.credentials,'omit');
 console.log('9 browser heartbeat checks passed: immediate, ten-minute cadence, visibility, return, page lifecycle, origin selection and credential-free requests.');
})().catch(e=>{console.error(e);process.exitCode=1});
