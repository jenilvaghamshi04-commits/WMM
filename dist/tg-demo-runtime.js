/* Fictional, browser-only TG Groups admins sandbox. No Telegram or gateway calls. */
window.WMMGroupsDemo={start:async function(){
 const storageKey='wmm.groups.demo.v1';
 const now=()=>Date.now()+(state.offset||0),iso=()=>new Date(now()).toISOString(),istDay=t=>new Date(new Date(t).getTime()+19800000).toISOString().slice(0,10);
 function seed(){
  const names=['Orion Labs','Harbor Network','Cedar Protocol','Nova Community'];
  const groups=names.map((name,i)=>({key:'demo-group-'+i,group_id:'demo-group-'+i,name:name+' · Demo',username:'demo_'+name.toLowerCase().replaceAll(' ','_'),kind:'group',account_id:i%2+1,collection_source:'automatic_join',scraped_at:new Date(Date.now()-i*3600000).toISOString(),archive:{status:'Archived'},admins:['Owner','Admin','Admin','Admin'].map((role,j)=>({user_id:'demo-user-'+i+'-'+j,name:['Alex Morgan','Sam Chen','Taylor Reed','Jordan Lee'][j],username:'demo_'+i+'_'+j,role,title:['CEO','CTO','Moderator','BD'][j],scraped_at:new Date().toISOString()}))}));
  const variants={template:['Hey @username! I came across $TOKEN on {{exchange}}. Could we discuss liquidity?','Hi @username, Mark from WMM here. Who handles $TOKEN liquidity on {{exchange}}?','Hello @username! Could WMM share a liquidity proposal for $TOKEN on {{exchange}}?','Hey @username, would your team like a market-making demo for $TOKEN on {{exchange}}?','Hi @username! Are you the right contact for $TOKEN market making on {{exchange}}?'],followup_template:[WMMMessageModel.followup],yes_pitch_template:[WMMMessageModel.yesPitch],yes_demo_template:[WMMMessageModel.yesDemo]};
  return {version:1,slots:2,groups:groups.slice(0,2),available:groups.slice(2),queue:[],deliveries:[],receipts:{},rotation:{},offset:0,cfg:{template:variants.template[0],followup_template:variants.followup_template[0],yes_pitch_template:variants.yes_pitch_template[0],yes_demo_template:variants.yes_demo_template[0],template_variants:variants,send_delay_seconds:120,sender_account:1,token_symbol:'DEMO',sheet_url:'',auto_yes_enabled:false,auto_followup_enabled:false}};
 }
 let state;try{state=JSON.parse(localStorage.getItem(storageKey));if(state?.version!==1)state=null}catch{}if(!state)state=seed();
 function save(){try{localStorage.setItem(storageKey,JSON.stringify(state))}catch{}}
 function tick(){let changed=false;for(const q of state.queue)if(q.status==='Queued'&&Date.parse(q.next_attempt_at)<=now()){
  q.status='Sent';state.deliveries.unshift({delivery_id:q.queue_id,id:q.contact_id,contact_id:q.contact_id,target:q.target,kind:'dm',account_id:q.account_id,status:'Sent',at:iso(),message:q.message,name:q.name,recipient_name:q.name,simulated:true});changed=true;
 }if(changed)save();return changed}
 function contacts(){return state.groups.flatMap(g=>g.admins.map(a=>({...a,id:a.user_id,kind:'dm',scan_account:g.account_id,group_id:g.group_id,group:g.name,is_bot:false,scanned_at:g.scraped_at})));}
 function status(){tick();return {version:'demo',accounts:[1,2,3].map(id=>{const day=t=>new Date(new Date(t).getTime()+19800000).toISOString().slice(0,10),used=state.deliveries.filter(d=>d.account_id===id&&day(d.at)===day(now())).length;return {id,label:'Demo sender '+id,authorized:id<=state.slots,api_configured:id<=state.slots,usage:{dm:{used,limit:15,remaining:15-used},group:{used:0,limit:30,remaining:30}},daily_progress:{dm:{used,sent:used,limit:15,queued:state.queue.filter(q=>q.account_id===id&&q.status==='Queued').length,remaining:Math.max(0,15-used-state.queue.filter(q=>q.account_id===id&&q.status==='Queued').length)},group:{used:0,sent:0,limit:30,queued:0,remaining:30}},sent_today:used,daily_goal:10,pacing:{delay_seconds:state.cfg.send_delay_seconds},group_watch:{ready:true,started_at:state.groups[0]?.scraped_at,saved:state.groups.filter(g=>g.account_id===id).length,pending:0},health:{state:'Demo',connected:true}}}),account_slots:state.slots,group_admins:state.groups,contacts:contacts(),queued_sends:state.queue,deliveries:state.deliveries,leads:[],quota_resets:[],settings:{...state.cfg,template_rotation:state.rotation},features:{token_personalization:true,message_templates:true,new_recipient_dm_quota:true,original_sender_lock:true,group_admin_directory:true,progressive_accounts:true,new_group_watch:true,new_group_picker_archive:true,admin_bulk_sends:true,send_pacing:true,background_sends:true,template_variants:true,nonrepeating_templates:true,affirmative_only:true}}}
 function error(message){return Object.assign(Error(message),{status:409})}
 rawApi=async function(path,body){
  if(path==='/status')return status();
  if(path==='/templates'&&!body)return {...state.cfg,template_rotation:state.rotation};
  if(path==='/templates'){state.cfg={...state.cfg,...body};for(const [k,v] of Object.entries(body.template_variants||{}))state.cfg[k]=v.find(t=>t.trim())||'';save();return {ok:true}}
  if(path==='/sending-pace'){if(![120,300,600].includes(body.delay_seconds))throw error('Choose 2, 5 or 10 minutes.');state.cfg.send_delay_seconds=body.delay_seconds;save();return {ok:true}}
  if(path==='/accounts/add'){if(state.slots>=3)throw error('All three demo accounts are already available.');state.slots++;save();return {account_id:state.slots}}
  if(path==='/groups/new')return {groups:state.available.filter(g=>g.account_id===body.account_id),account_id:body.account_id,watch_principal:'demo-account-'+body.account_id};
  if(path==='/groups/new/admins'){const g=state.available.find(g=>g.group_id===body.group_id&&g.account_id===body.account_id);if(!g||body.watch_principal!=='demo-account-'+body.account_id)throw error('Reload new demo groups for this account.');state.available=state.available.filter(x=>x!==g);g.scraped_at=iso();state.groups.unshift(g);save();return {count:g.admins.length,group:g.name,archive:{status:'Archived'}}}
  if(path==='/send-queue/cancel'){for(const q of state.queue)if(q.status==='Queued'&&(!body.id||q.queue_id===body.id))q.status='Cancelled';save();return {ok:true}}
  if(path==='/groups/admins/send-batch'){
   if(state.receipts[body.request_id])return state.receipts[body.request_id];
   const recipients=contacts(),used=state.deliveries.filter(d=>d.account_id===body.account_id&&istDay(d.at)===istDay(now())).length,pending=state.queue.filter(q=>q.account_id===body.account_id&&q.status==='Queued').length;
   if(used+pending+body.messages.length>15)throw error('Demo account daily limit reached. Reset demo to start again.');
   if(!body.messages.length||body.account_id>state.slots)throw error('Choose recipients and an available demo account.');
   const rotation=JSON.parse(JSON.stringify(state.rotation));const prepared=[];
   for(const item of body.messages){const p=recipients.find(p=>p.id===item.id);if(!p||prepared.some(q=>q.target===p.user_id)||state.queue.some(q=>q.target===p.user_id&&['Queued','Sent'].includes(q.status)))throw error('This demo admin is already queued or sent.');
    const text=item.template_choices?.template,pool=[...new Set(state.cfg.template_variants.template.map(t=>t.trim()).filter(Boolean))];let seen=(rotation.template?.used||[]).filter(t=>pool.includes(t));if(pool.every(t=>seen.includes(t)))seen=[];
    if(!pool.includes(text)||seen.includes(text))throw error('This saved option changed. Reopen the preview.');rotation.template={used:[...seen,text],last:text};
    prepared.push({queue_id:'demo-send-'+uniqueRequest(),contact_id:p.id,target:p.user_id,kind:'dm',status:'Queued',created_at:iso(),name:p.name,account_id:body.account_id,message:WMMMessageModel.personalize(item.message,p,body.token_symbol,body.exchange)});
   }
   const gap=Math.max(body.delay_seconds,state.cfg.send_delay_seconds)*1000,last=state.queue.filter(q=>q.account_id===body.account_id&&q.status==='Queued').map(q=>Date.parse(q.next_attempt_at)),first=Math.max(now(),...last.map(t=>t+gap));
   prepared.forEach((q,i)=>q.next_attempt_at=new Date(first+i*gap).toISOString());state.queue.push(...prepared);state.rotation=rotation;
   const result={status:'Queued',count:prepared.length,account_id:body.account_id,delay_seconds:gap/1000};state.receipts[body.request_id]=result;save();return result;
  }
  throw Error('This is the isolated TG Groups admins demo. This operation cannot access live services.');
 };
 // Never read or write the live dashboard session from this page.
 Object.assign(workspaceSession,{read:()=>null,save:()=>false,clear(){},page(){},filter(){}});gateway='';key='';
 const liveView=view;view=function(page){liveView(['groups','templates'].includes(page)?page:'groups')};
 const normalRefresh=refresh;refresh=async function(...args){await normalRefresh(...args);$('#connectionBadge').textContent='DEMO · simulated accounts';$('#connectionNotice').textContent='Demo workspace — fictional contacts and simulated messages.';document.querySelectorAll('[data-add-account]').forEach(b=>b.onclick=()=>action(b,async()=>{await rawApi('/accounts/add',{});await refresh(false);toast('Demo account added and ready to use.')}));document.querySelectorAll('[data-queued-panel] .inner > .hint').forEach(p=>p.textContent='Simulated queue stored in this browser. Use Advance 10 minutes to test delays instantly. No Telegram messages are sent.');};
 $('#loginScreen').hidden=true;$('#appShell').hidden=false;
 document.querySelectorAll('nav button[data-view]').forEach(b=>{if(!['groups','templates'].includes(b.dataset.view))b.hidden=true});
 $('#dashboardLogout').textContent='Exit demo';$('#dashboardLogout').onclick=()=>location.assign('/');
 document.querySelectorAll('a[href="gateway.zip"]').forEach(a=>a.hidden=true);
 const banner=document.createElement('div');banner.className='demo-banner';banner.innerHTML='<div><b>Interactive demo</b><p>Fictional groups · simulated sends · IST · live data stays separate</p></div><button id="demoAdvance">Advance 10 minutes</button><button id="demoReset">Reset demo</button><a href="/">Back to live workspace</a>';
 document.querySelector('main').prepend(banner);
 $('#demoAdvance').onclick=async()=>{state.offset+=600000;tick();save();await refresh(false);toast('Demo clock advanced 10 minutes. Due messages are simulated as sent.');};
 $('#demoReset').onclick=async()=>{state=seed();save();tgAdminSelected.clear();tgAdminBatchPlan=null;groupAdminOpenKey=undefined;groupPageDelayDirty=false;resetJoinedGroupPicker();closeTgAdminComposer();await refresh();view('groups');toast('Fictional demo records restored.');};
 await refresh();view('groups');save();setInterval(async()=>{if(!busy&&tick())await refresh(false)},1000);
}};
