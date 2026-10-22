function followupAction(summary,lead){if(!summary.canFollowup||WMMMessageModel.hasReplied(lead))return '';return lead?.followup_due?'<button class="primary" data-due="'+esc(lead.key)+'">Review due follow-up</button>':'<button class="primary" data-followup="'+esc(summary.lastSent.delivery_id)+'">Send follow-up ↗</button>'}
function crmKey(contact){const kind=contact.kind||'dm';return kind+':'+String(contact.target??(kind==='group'?contact.group_id:contact.user_id))}
function crmLead(contact){return leads.find(lead=>lead.key===crmKey(contact))}
function crmDate(value){return value?new Date(value).toLocaleString():'Not checked'}
function leadBadges(lead){
  if(!lead)return '<div class="sentmeta">Lead tracking: deploy the latest gateway.</div>';
  return '<div class="crm-badges"><span class="crm-badge '+(lead.reply_status==='Replied'?'replied':'')+'">'+esc(lead.reply_status)+'</span><span class="crm-badge">Stage: '+esc(lead.stage)+'</span>'+(lead.needs_attention?'<span class="crm-badge attention">Reply needs attention</span>':'')+(lead.followup_due&&!WMMMessageModel.hasReplied(lead)?'<span class="crm-badge attention">Follow-up due</span>':'')+'</div>'+(lead.due_at&&!WMMMessageModel.hasReplied(lead)?'<div class="sentmeta">Follow-up '+(lead.followup_due&&!WMMMessageModel.hasReplied(lead)?'due ':'scheduled ')+esc(crmDate(lead.due_at))+'</div>':'')+(lead.latest_reply?'<div class="crm-snippet">'+esc(lead.latest_reply.body.slice(0,130))+'</div>':'')+(lead.sync_error?'<div class="deliverydetail">'+esc(lead.sync_error)+'</div>':'')+folderBadges(lead)+autoReplyBadges(lead)+autoFollowupBadges(lead);
}
function folderBadges(lead){return (lead.folder_routes||[]).map(route=>'<div class="crm-folder-route '+(route.desired==='🔵'?'blue':'yellow')+'"><span>'+(route.status==='Synced'?'Telegram folder: ':route.status==='Pending'?'Moving to folder: ':'Folder needs attention: ')+esc(route.desired)+' · Account '+esc(route.account_id)+'</span>'+(route.error?'<div class="deliverydetail">'+esc(route.error)+'</div>':'')+'</div>').join('')}
function autoReplyBadges(lead){const a=lead.auto_yes;if(!a)return '';return '<div class="crm-snippet"><b>Automatic replies: '+esc(a.completed_once?'Sent once · automation stopped':a.status)+'</b><div class="sentmeta">'+esc(a.exchange_name)+' · $'+esc(a.token_symbol)+(a.branch?' · '+esc(a.branch==='yes'?'Yes reply':'No reply')+' · '+a.sent_parts+'/'+a.total_parts+' messages sent':'')+'</div>'+(a.error?'<div class="deliverydetail">'+esc(a.error)+'</div>':'')+'</div>'}
function autoFollowupBadges(lead){const a=lead.auto_followup;if(!a)return '';return '<div class="crm-snippet"><b>3-day follow-up: '+esc(a.status)+'</b><div class="sentmeta">Original sender · Account '+esc(a.account_id)+' · Due '+esc(crmDate(a.due_at))+'</div>'+(a.error?'<div class="deliverydetail">'+esc(a.error)+'</div>':'')+'</div>'}
function bindLeadActions(container){
  container.querySelectorAll('[data-lead]').forEach(b=>b.onclick=()=>openLead(b.dataset.lead));
  container.querySelectorAll('[data-due]').forEach(b=>b.onclick=()=>action(b,()=>reviewDueFollowup(b.dataset.due)));
}
function renderPipeline(){
  const summary=$('#leadSummary');if(!summary)return;
  const direct=leads.filter(l=>l.kind==='dm'),attention=direct.filter(l=>l.needs_attention).length,due=direct.filter(l=>l.followup_due&&!WMMMessageModel.hasReplied(l)).length;
  summary.innerHTML=[['Total DM leads',direct.length],['Awaiting reply',direct.filter(l=>l.reply_status==='Awaiting reply').length],['Replies needing attention',attention],['Follow-ups due',due]].map(([label,count])=>'<div class="crm-stat"><span>'+label+'</span><b>'+count+'</b></div>').join('');
  $('#replyTrackingHint').textContent=!live?'Connect your gateway to load replies and reminders.':!serverFeatures.lead_management?'Deploy the latest WMM commit on Render to enable reply detection, reminders and lead stages.':'Replies are detected while your gateway is online. History checks run in the background; Check replies starts a small batch now. Dashboard data refreshes every 30 seconds. Confirmed DMs go to 🔵; replies move the chat to 🟡 on the same Telegram account. A clear yes keeps it in 🟡 after the pitch and call invitation are sent. The three-day automatic follow-up checks for replies and uses the first sender; unavailable senders wait without switching accounts.';
  if(live&&serverFeatures.lead_management&&!serverFeatures.telegram_folder_routing)$('#replyTrackingHint').textContent+=' Deploy the latest gateway to enable Telegram folder routing.';
  const query=$('#leadSearch').value.toLowerCase(),filter=$('#leadFilter').value,type=$('#leadType').value;
  const visible=leads.filter(l=>l.kind===type&&[l.name,l.username,l.group].join(' ').toLowerCase().includes(query)&&(filter==='all'||filter==='attention'&&l.needs_attention||filter==='due'&&l.followup_due&&!WMMMessageModel.hasReplied(l)||filter==='awaiting'&&l.reply_status==='Awaiting reply'||filter==='replied'&&l.reply_status==='Replied'));
  $('#pipelineBoard').innerHTML=['New','Contacted','Replied','Meeting','Proposal','Client'].map(stage=>{const list=visible.filter(l=>l.stage===stage);return '<section class="pipeline-column"><header><h2>'+stage+'</h2><span class="count">'+list.length+'</span></header><div class="pipeline-cards">'+(list.length?list.map(l=>'<article class="pipeline-lead"><button class="lead-name" data-lead="'+esc(l.key)+'">'+esc(l.name)+'</button><div class="sentmeta">'+esc(l.username?'@'+l.username:l.group||'No public username')+'</div>'+leadBadges(l)+'<div class="crm-buttons"><button data-lead="'+esc(l.key)+'">Manage lead</button>'+(l.followup_due&&!WMMMessageModel.hasReplied(l)?'<button class="primary" data-due="'+esc(l.key)+'">Review follow-up</button>':'')+'</div><div class="sentmeta">Updated '+(l.last_activity_at?esc(crmDate(l.last_activity_at)):'—')+'</div></article>').join(''):'<p class="pipeline-empty">No leads in this stage.</p>')+'</div></section>'}).join('');
  bindLeadActions($('#pipelineBoard'));
}
let activeLeadKey=null;
function populateLead(lead){
  $('#leadDialogName').textContent=lead.name;$('#leadDialogIdentity').textContent=(lead.username?'@'+lead.username+' · ':'')+(lead.group||'Telegram direct message');$('#leadDialogStatus').innerHTML=leadBadges(lead);
  $('#leadStage').value=lead.stage;$('#leadReminderDays').value=String(lead.reminder_days);$('#leadRemindersEnabled').checked=lead.reminders_enabled;$('#leadRemindersEnabled').disabled=lead.kind!=='dm';$('#leadReminderDays').disabled=lead.kind!=='dm';
  $('#leadReminderHint').textContent=lead.due_at?'Next follow-up: '+crmDate(lead.due_at)+' · '+lead.reminder_days+' days after the last confirmed send.':lead.reminder_reason+'.';
  $('#checkLeadReplies').hidden=lead.kind!=='dm'||!lead.last_sent_at;$('#acknowledgeLead').hidden=!lead.needs_attention;$('#reviewLeadFollowup').hidden=!lead.followup_due||WMMMessageModel.hasReplied(lead);
  $('#leadReplies').innerHTML=lead.replies.length?lead.replies.map(reply=>'<article class="reply-entry"><div class="sentmeta">Received · Account '+esc(reply.account_id)+' · '+esc(crmDate(reply.at))+'</div><div class="crm-reply-body">'+esc(reply.body)+'</div></article>').join(''):'<p class="hint" style="padding:16px 0">'+(lead.kind==='group'?'Group messages are not used for individual reply detection.':'No reply has been detected after the first confirmed message.')+'</p>';
  if(lead.kind==='dm'&&lead.last_sent_at)$('#leadReplies').insertAdjacentHTML('beforeend','<p class="hint">History checked: '+esc(crmDate(lead.sync_checked_at))+(lead.sync_complete?' · Up to date at that check':' · '+(lead.sync_error||'More history may need checking'))+'</p>');
  $('#syncLeadFolders').hidden=lead.kind!=='dm'||!lead.last_sent_at||!serverFeatures.telegram_folder_routing;
  const auto=lead.auto_yes;$('#toggleAutoReplies').hidden=!auto||['Complete','Cancelled','Needs attention'].includes(auto.status);$('#toggleAutoReplies').textContent=auto?.enabled?'Pause automatic replies':'Resume automatic replies';$('#leadSaveState').textContent='';
}
function openLead(key){
  if(!live||!serverFeatures.lead_management){toast('Deploy the latest gateway commit on Render to enable lead management.');return}
  const lead=leads.find(l=>l.key===key);if(!lead){toast('Refresh data to load this lead.');return}activeLeadKey=key;populateLead(lead);$('#leadDialog').showModal();
}
async function checkReplyBatch(key=null){
  if(!live||!serverFeatures.lead_management)throw Error('Deploy the latest gateway commit on Render to check replies.');
  const result=await api('/replies/sync',key?{key}:{});await refresh(false);
  if(activeLeadKey&&$('#leadDialog').open){const lead=leads.find(l=>l.key===activeLeadKey);if(lead)populateLead(lead)}
  const failure=result.results?.find(r=>!r.ok);toast(failure?failure.error:result.checked?'Checked '+result.checked+' conversation(s).'+(result.remaining?' Background checks will continue with the rest.':''):'Recently checked or waiting for the next permitted check.');return result;
}
async function reviewDueFollowup(key){
  await checkReplyBatch(key);const lead=leads.find(l=>l.key===key);
  if(!lead||WMMMessageModel.hasReplied(lead)){toast('A reply was received. Follow-up reminders have stopped.');return}
  if(!lead.followup_due){toast('This follow-up is no longer due.');return}
  if(!lead.sync_complete||lead.sync_error||!lead.sync_checked_at||Date.now()-Date.parse(lead.sync_checked_at)>5*60*1000)throw Error(lead.sync_error||'Reply history is still being checked. Check replies again before reviewing this reminder.');
  if($('#leadDialog').open)$('#leadDialog').close();openFollowup(lead.followup_delivery_id);
}
document.addEventListener('DOMContentLoaded',()=>{
  for(const selector of ['#leadSearch','#leadFilter','#leadType'])$(selector).addEventListener(selector==='#leadSearch'?'input':'change',renderPipeline);
  $('#syncLeadFolders').onclick=()=>action($('#syncLeadFolders'),async()=>{const result=await api('/folders/sync',{key:activeLeadKey});await refresh(false);const lead=leads.find(l=>l.key===activeLeadKey);if(lead)populateLead(lead);const failed=result.results?.find(r=>!r.ok);toast(failed?failed.error:result.checked?'Telegram folders synced.':'Folders are up to date or waiting for Telegram to allow the next update.');});
  $('#toggleAutoReplies').onclick=()=>action($('#toggleAutoReplies'),async()=>{const lead=leads.find(l=>l.key===activeLeadKey);await api('/auto-yes/update',{key:activeLeadKey,enabled:!lead.auto_yes.enabled});await refresh(false);populateLead(leads.find(l=>l.key===activeLeadKey));toast('Automatic reply setting updated.');});
  $('#refreshPipeline').onclick=()=>action($('#refreshPipeline'),()=>refresh(false));
  $$('[data-check-replies]').forEach(b=>b.onclick=()=>action(b,()=>checkReplyBatch()));
  $('#closeLeadDialog').onclick=()=>{if(!busy)$('#leadDialog').close()};$('#leadDialog').addEventListener('cancel',e=>{if(busy)e.preventDefault()});
  $('#saveLead').onclick=()=>action($('#saveLead'),async()=>{if(!activeLeadKey)return;await api('/leads/update',{key:activeLeadKey,stage:$('#leadStage').value,reminder_days:Number($('#leadReminderDays').value),reminders_enabled:$('#leadRemindersEnabled').checked});await refresh(false);const lead=leads.find(l=>l.key===activeLeadKey);if(lead)populateLead(lead);$('#leadSaveState').textContent='Lead settings saved.';toast('Lead stage and reminder settings saved.');});
  $('#acknowledgeLead').onclick=()=>action($('#acknowledgeLead'),async()=>{await api('/leads/update',{key:activeLeadKey,acknowledge:true});await refresh(false);const lead=leads.find(l=>l.key===activeLeadKey);if(lead)populateLead(lead);toast('Reply marked as reviewed.');});
  $('#checkLeadReplies').onclick=()=>action($('#checkLeadReplies'),()=>checkReplyBatch(activeLeadKey));$('#reviewLeadFollowup').onclick=()=>action($('#reviewLeadFollowup'),()=>reviewDueFollowup(activeLeadKey));
  renderPipeline();
  setInterval(async()=>{if(!live||busy||document.hidden||document.querySelector('dialog[open]'))return;try{await refresh(false)}catch{}},30000);
});
