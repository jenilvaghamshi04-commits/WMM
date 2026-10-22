const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const script=fs.readFileSync('dist/import-pacing.js','utf8');
function setup({active=true,stop=false,response}={}){
 let ticks=0,calls=[],now=0,ctx;const progress={textContent:''},button={hidden:true};
 ctx=vm.createContext({document:{addEventListener(){},querySelectorAll(s){return s==='[data-send-progress]'?[progress]:[button]}},Date:{now:()=>now},Math,Number,String,Promise,Error,serverFeatures:{send_pacing:active},deliveries:[],sender:()=>2,
  setTimeout(fn,ms){ticks++;now+=ms;if(stop)vm.runInContext('pendingSendStopped=true',ctx);fn()},
  rawApi:async(path,body)=>{calls.push({path,body});return response?response(calls.length,path,body):{ok:true}}});
 vm.runInContext(script,ctx);return {ctx,calls,progress,button,get ticks(){return ticks}};
}
(async()=>{
 const original={id:'lead',account_id:1,message:'Reviewed text'},s=setup({response:n=>{if(n===1)throw Object.assign(Error('Wait'),{code:'send_cooldown',retryAfter:120});return {status:'Sent'}}});
 s.ctx.body=original;assert.equal((await vm.runInContext("api('/send',body)",s.ctx)).status,'Sent');assert.equal(s.calls.length,2);assert.equal(s.ticks,120);assert.equal(s.calls[1].body,original);assert.equal(s.calls[1].body.account_id,1);
 const stopped=setup({stop:true,response:()=>{throw Object.assign(Error('Wait'),{code:'send_cooldown',retryAfter:120})}});stopped.ctx.body=original;
 await assert.rejects(vm.runInContext("api('/send',body)",stopped.ctx),/stopped/);assert.equal(stopped.calls.length,1);
 for(const error of [Error('Telegram wait'),Object.assign(Error('Network uncertain'),{name:'AbortError'}),Object.assign(Error('Daily cap'),{code:'daily_limit'})]){
  const s=setup({response:()=>{throw error}});s.ctx.body=original;await assert.rejects(vm.runInContext("api('/send',body)",s.ctx));assert.equal(s.calls.length,1);assert.equal(s.ticks,0);
 }
 const old=setup({active:false});old.ctx.body=original;await assert.rejects(vm.runInContext("api('/send',body)",old.ctx),/latest WMM backend/);assert.equal(old.calls.length,0);
 const follow=setup({response:n=>{if(n===1)throw Object.assign(Error('Wait'),{code:'send_cooldown',retryAfter:5});return {status:'Sent'}}});follow.ctx.body={delivery_id:'first',request_id:'stable-request',message:'Follow up'};
 await vm.runInContext("api('/follow-up',body)",follow.ctx);assert.equal(follow.calls[0].body,follow.calls[1].body);assert.equal(follow.ticks,5);
 console.log('7 pacing UI scenarios passed: wait, sender retention, stop, no retry after errors, upgrade gate, follow-up identity.');
})().catch(e=>{console.error(e);process.exitCode=1});
