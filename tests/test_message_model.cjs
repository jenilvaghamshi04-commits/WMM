const assert=require('node:assert/strict');
const m=require('../dist/message-model.js').WMMMessageModel || globalThis.WMMMessageModel;
const person={id:'groupA:7',user_id:'7',name:'Jenil',role:'Admin',group:'WallStreetMM'};
const first={id:'groupA:7',target:'7',kind:'dm',delivery_id:'first',status:'Sent',account_id:1,at:'2026-10-22T08:00:00Z'};
let checks=0;function check(name,fn){fn();checks++;console.log('PASS:',name)}
check('unsent contact can open initial messaging',()=>{const s=m.conversation(person,[]);assert.equal(s.canSend,true);assert.equal(s.canFollowup,false);assert.equal(m.status(s),'Not sent')});
check('initial sent contact switches to follow-up',()=>{const s=m.conversation(person,[first]);assert.equal(s.canSend,false);assert.equal(s.canFollowup,true);assert.equal(m.status(s),'Message sent')});
check('contact history follows identity across scanned groups',()=>{const alias={...person,id:'groupB:7'};assert.equal(m.conversation(alias,[first]).sent.length,1)});
check('follow-up count and latest status update on saved row',()=>{const a={...first,delivery_id:'f1',followup_of:'first',at:'2026-10-22T08:30:00Z'},b={...a,delivery_id:'f2',at:'2026-10-22T09:00:00Z'};const s=m.conversation(person,[first,a,b]);assert.equal(s.followups,2);assert.equal(s.lastSent.delivery_id,'f2');assert.equal(m.status(s),'Follow-up sent')});
check('failed follow-up keeps original sent state and allows a new follow-up',()=>{const failed={...first,delivery_id:'f1',followup_of:'first',status:'Failed',at:'2026-10-22T09:00:00Z'};const s=m.conversation(person,[first,failed]);assert.equal(s.sent.length,1);assert.equal(s.followups,0);assert.equal(s.canFollowup,true);assert.equal(m.status(s),'Follow-up failed')});
check('uncertain follow-up blocks additional sends',()=>{const unknown={...first,delivery_id:'u',followup_of:'first',status:'Uncertain',at:'2026-10-22T09:00:00Z'};const s=m.conversation(person,[first,unknown]);assert.equal(s.canSend,false);assert.equal(s.canFollowup,false);assert.equal(m.status(s),'Delivery needs review')});
check('group and DM histories remain separate',()=>{const group={...person,id:'group:7',group_id:'7',kind:'group'};assert.equal(m.conversation(group,[first]).rows.length,0)});
check('preview text substitutes all supported placeholders',()=>{assert.equal(m.personalize('Hi {{name}}, {{role}} at {{group}}. {{name}}!',person),'Hi Jenil, Admin at WallStreetMM. Jenil!')});
console.log(checks+' message model checks passed');
