/* Pure browser-local demo model. No gateway access or live workspace keys. */
(function(root){
 'use strict';
 const defaultTemplates=[
  'Hey @username, I recently came across $TOKEN on {EXCHANGE}. Are you the right person to discuss liquidity support?',
  'Hi @username! I’m Mark from WallStreet Market Maker. Who handles $TOKEN liquidity on {EXCHANGE}?',
  'Hello @username, would you be open to a quick conversation about market making for $TOKEN on {EXCHANGE}?',
  'Hey @username, we work with token teams on CEX liquidity. Is $TOKEN on {EXCHANGE} something you manage?',
  'Hi @username, nice to meet you. I’d like to introduce our liquidity support for $TOKEN on {EXCHANGE}. Are you the best contact?'
 ];
 const names=['Alex Morgan','Priya Shah','Daniel Lee','Maya Chen','Sam Patel','Jordan Kim'];
 const titles=['CEO','CTO','Business Development','Moderator','Community Lead',''];
 function group(key,name,account,index){const at=new Date(Date.now()-index*3600000).toISOString();return {key,name,username:'demo_'+key,account,kind:'group',scraped_at:at,archived:true,admins:names.map((n,i)=>({id:key+'-'+i,user_id:String(900000000+index*100+i),name:n,username:i===5?'':'sample_'+key+'_'+(i+1),role:i===0?'Owner':'Admin',title:titles[i],scraped_at:at}))}}
 function initial(){return {version:1,accounts:2,delay:120,speed:60,clock:Date.now(),paused:false,groups:[group('aurora','Aurora Labs · Demo',1,1),group('orbit','Orbit Network · Demo',2,2),group('vertex','Vertex Protocol · Demo',1,3)],available:[group('nova','Nova Community · Demo',1,4),group('atlas','Atlas DAO · Demo',2,5),group('prism','Prism Network · Demo',3,6)],templates:defaultTemplates.slice(),used:[],last:null,queue:[],nextId:1};}
 function eligible(state,uid){return !state.queue.some(q=>q.user_id===uid&&q.status!=='Cancelled');}
 function findAdmin(state,id){for(const g of state.groups){const a=g.admins.find(a=>a.id===id);if(a)return {...a,group:g.name,groupAccount:g.account};}return null;}
 function personalize(text,admin,token,exchange){return text.replaceAll('@username',admin.username?'@'+admin.username:admin.name).replaceAll('$TOKEN','$'+token.replace(/^\$/,'').toUpperCase()).replaceAll('{EXCHANGE}',exchange);}
 function preview(state,ids,sender,token,exchange,first='random',random=Math.random){
  token=token.trim().replace(/^\$/,'').toUpperCase();if(!/^[A-Z0-9][A-Z0-9._-]{0,31}$/.test(token)||!exchange)throw Error('Enter a token symbol and choose an exchange.');
  if(!Number.isInteger(sender)||sender<1||sender>state.accounts)throw Error('Choose an available demo account.');
  if(!ids.length||ids.length>15||new Set(ids).size!==ids.length)throw Error('Select between 1 and 15 different admins.');
  const pool=[...new Set(state.templates.map(t=>t.trim()).filter(Boolean))];if(pool.length!==5)throw Error('Save five different, nonempty demo options first.');
  const used=state.used.filter(t=>pool.includes(t));let rotation=used.slice(),last=state.last;
  const messages=ids.map((id,index)=>{const a=findAdmin(state,id);if(!a||!eligible(state,a.user_id))throw Error('A selected admin is already queued or sent. Clear the selection and try again.');
   let available=pool.filter(t=>!rotation.includes(t));if(!available.length){rotation=[];available=pool.slice();}
   if(!rotation.length&&available.length>1)available=available.filter(t=>t!==last);
   const chosen=index===0&&first!=='random'?state.templates[Number(first)]:null;
   if(chosen&&!available.includes(chosen))throw Error('That option has already been used in this cycle. Choose another option or random.');
   const template=chosen||available[Math.floor(random()*available.length)];rotation.push(template);last=template;
   return {admin_id:id,user_id:a.user_id,name:a.name,username:a.username,template,message:personalize(template,a,token,exchange)};
  });
  const day=new Date(state.clock+19800000).toISOString().slice(0,10);
  const usedQuota=state.queue.filter(q=>q.account===sender&&q.day===day&&q.status!=='Cancelled').length;
  if(usedQuota+messages.length>15)throw Error('Demo Account '+sender+' has '+(15-usedQuota)+' DMs left today. Reduce the selection or choose another demo account.');
  return {messages,sender,delay:state.delay,token,exchange,used:rotation,last,day};
 }
 function enqueue(state,plan){
  if(plan.delay!==state.delay)throw Error('Delay changed. Preview the messages again.');
  // Revalidate recipients and quota at confirmation; the reviewed text stays fixed.
  preview(state,plan.messages.map(m=>m.admin_id),plan.sender,plan.token,plan.exchange);
  const pending=state.queue.filter(q=>q.account===plan.sender&&q.status==='Queued');
  const sent=state.queue.filter(q=>q.account===plan.sender&&q.status==='Simulated sent');
  let at=Math.max(state.clock,...pending.map(q=>q.at+Math.max(q.delay,plan.delay)*1000),...sent.map(q=>q.sent_at+plan.delay*1000));
  for(const m of plan.messages){state.queue.push({...m,id:state.nextId++,account:plan.sender,delay:plan.delay,day:plan.day,at,status:'Queued'});at+=plan.delay*1000;}
  state.used=plan.used.slice();state.last=plan.last;
  return plan.messages.length;
 }
 function tick(state,elapsed){if(state.paused)return false;state.clock+=Math.max(0,elapsed)*state.speed;let changed=false;for(const q of state.queue){if(q.status==='Queued'&&q.at<=state.clock){q.status='Simulated sent';q.sent_at=q.at;changed=true;}}return changed;}
 function collect(state,key,account){const g=state.available.find(g=>g.key===key&&g.account===account);if(!g)throw Error('Choose a new demo group for the selected account.');state.available=state.available.filter(x=>x.key!==key);g.scraped_at=new Date(state.clock).toISOString();g.admins.forEach(a=>a.scraped_at=g.scraped_at);g.archived=true;state.groups.unshift(g);return g;}
 const api={initial,preview,enqueue,tick,collect,eligible,findAdmin,personalize};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.WMMGroupsDemo=api;
})(typeof globalThis==='undefined'?this:globalThis);
