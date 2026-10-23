const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function setup(){
 const nodes=new Map(),calls=[],toasts=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',open:false,checked:false});return nodes.get(id)};
 const fields=[['initial','template','introduction'],['followup','followup_template','followup'],['yesPitch','yes_pitch_template','yesPitch'],['yesDemo','yes_demo_template','yesDemo']];
 const cfg={template_variants:{template:['New one','New two','New three','New four','New five'],followup_template:['Follow'],yes_pitch_template:['Pitch'],yes_demo_template:['Invite']},template_rotation:{template:{used:['New one'],last:'New one'}}};
 const stale=()=>Object.assign(Error('This saved option changed. Reopen the preview.'),{status:409});
 const ctx=vm.createContext({document:{addEventListener(){},getElementById:node},templateFields:fields,WMMMessageModel:{introduction:'Built-in default',followup:'Follow',yesPitch:'Pitch',yesDemo:'Invite'},live:true,serverFeatures:{send_pacing:true,background_sends:true},savedTemplate:'Old option',savedFollowupTemplate:'Follow',savedYesPitch:'Pitch',savedYesDemo:'Invite',toast:t=>toasts.push(t),updateContactPreview(){},updateFollowupPreview(){},refresh:async()=>{},refreshQueuedSends:async()=>{},uniqueRequest:()=> 'test-preview-request',Math,Error,
 rawApi:async(path,body)=>{calls.push({path,body});if(path==='/templates')return cfg;throw stale()}});
 vm.runInContext(fs.readFileSync('dist/template-variants.js','utf8'),ctx);vm.runInContext(fs.readFileSync('dist/import-pacing.js','utf8'),ctx);
 vm.runInContext("savedTemplateVariants.template=['Old option'];templateRotationUsed={};templateRotationLast={}",ctx);
 return {ctx,node,calls,toasts,cfg,stale};
}
test('opening a preview refreshes actual saved options and current rotation',async()=>{
 const a=setup();await vm.runInContext('refreshTemplateCatalog();',a.ctx);vm.runInContext('chooseContactInitial()',a.ctx);
 assert.ok(a.cfg.template_variants.template.includes(a.node('contactMessageText').value));assert.notEqual(a.node('contactMessageText').value,'New one');assert.notEqual(a.node('contactMessageText').value,'Old option');assert.deepEqual(a.calls.map(c=>c.path),['/templates']);
});
test('stale direct-send option rebuilds its preview and never retries the send',async()=>{
 const a=setup();a.node('contactMessageDialog').open=true;a.node('contactMessageFormat').value='saved';
 await assert.rejects(vm.runInContext("api('/send',{id:'contact',message:'Old option'})",a.ctx),/Review the new preview/);
 assert.deepEqual(a.calls.map(c=>c.path),['/send','/templates']);assert.ok(a.cfg.template_variants.template.includes(a.node('contactMessageText').value));assert.equal(vm.runInContext('templateRotationUsed.template.length',a.ctx),1);
});
test('stale queued-send option also rebuilds the preview without duplicate enqueue attempts',async()=>{
 const a=setup();a.node('contactMessageDialog').open=true;a.node('contactMessageFormat').value='saved';
 const raw=a.ctx.rawApi;a.ctx.rawApi=async(path,body)=>{if(path==='/send'){a.calls.push({path,body});throw Object.assign(Error('cooldown'),{code:'send_cooldown'})}return raw(path,body)};
 await assert.rejects(vm.runInContext("api('/send',{id:'contact',message:'Old option'})",a.ctx),/Review the new preview/);
 assert.deepEqual(a.calls.map(c=>c.path),['/send','/send-queue','/templates']);
});
test('blank saved pools cannot masquerade as a random built-in option',()=>{
 const a=setup();vm.runInContext("savedTemplateVariants.template=['','','','','']",a.ctx);assert.throws(()=>vm.runInContext("pickSavedTemplate('template')",a.ctx),/Add and save/);assert.equal(a.calls.length,0);
});
test('changing rotation invalidates a previously cached compose plan',()=>{
 const a=setup();vm.runInContext("savedTemplateVariants.template=['One','Two','Three'];getInitialBatchPlan(['lead'])",a.ctx);const before=vm.runInContext('initialBatchPlan',a.ctx);
 vm.runInContext("templateRotationUsed.template=[initialBatchPlan.messages.get('lead').text];getInitialBatchPlan(['lead'])",a.ctx);assert.notEqual(vm.runInContext('initialBatchPlan',a.ctx),before);assert.notEqual(vm.runInContext("initialBatchPlan.messages.get('lead').text",a.ctx),before.messages.get('lead').text);
});
