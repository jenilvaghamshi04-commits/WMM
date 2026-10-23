let activeInboxKey=null,workspaceResetRequestId=null;const inboxReplyDrafts=new Map(),inboxReplyRequests=new Map();
function inboxDate(at){return at?new Date(at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:true,timeZoneName:'short'}):''}
function inboxAvatar(name){return String(name||'?').split(/\s+/).map(x=>x[0]).slice(0,2).join('').toUpperCase()}
function renderReplyInbox(){
  if(!$('#replyThreads'))return;
  const priorPane=$('#inboxMessages'),priorKey=$('#replyConversation').dataset.threadKey,priorOrder=$('#replyConversation').dataset.order,priorScroll=priorPane?.scrollTop||0,wasAtBottom=priorPane?priorPane.scrollHeight-priorPane.clientHeight-priorScroll<24:true;
  if(priorKey&&$('#inboxReplyText'))inboxReplyDrafts.set(priorKey,$('#inboxReplyText').value);
  const threads=WMMInboxModel.filter(WMMInboxModel.conversations(leads,deliveries),$('#replySearch').value,$('#replyAccount').value);
  if(!threads.some(t=>t.key===activeInboxKey))activeInboxKey=threads[0]?.key||null;
  $('#replyInboxCount').textContent=threads.length+' conversation'+(threads.length===1?'':'s');
  $('#replyInboxHint').textContent=live?'Chats with received replies · newest activity first. The preview combines saved outgoing messages with up to 20 recent replies per contact.':'Connect your gateway to see received replies and message history.';
  $('#replyThreads').innerHTML=threads.length?threads.map(t=>'<button class="reply-thread '+(t.key===activeInboxKey?'active':'')+'" data-inbox-key="'+esc(t.key)+'"><span class="inbox-avatar">'+esc(inboxAvatar(t.lead.name))+'</span><span class="reply-thread-copy"><span class="reply-thread-title"><b>'+esc(t.lead.name)+'</b><time>'+esc(new Date(t.latest.at).toLocaleDateString('en-IN',{timeZone:'Asia/Kolkata'}))+'</time></span><span class="reply-thread-meta">'+esc(t.lead.username?'@'+t.lead.username:t.lead.group)+' · Account '+esc(t.account_id)+' · '+esc(t.lead.location?.country_name||'Country unknown')+'</span><span class="reply-thread-snippet">'+esc(t.latest.body.slice(0,110))+'</span></span></button>').join(''):'<div class="inbox-empty"><b>'+(!live?'Connect your workspace':'No replies to preview')+'</b><p>'+(!live?'Log in or connect your gateway in Connections.':$('#replySearch').value?'Try another search or account filter.':'Received replies will appear here after your gateway detects them.')+'</p></div>';
  $('#replyThreads').querySelectorAll('[data-inbox-key]').forEach(b=>b.onclick=()=>{activeInboxKey=b.dataset.inboxKey;renderReplyInbox()});
  const thread=threads.find(t=>t.key===activeInboxKey);
  if(!thread){$('#replyConversation').innerHTML='<div class="inbox-empty inbox-empty-chat"><span class="inbox-empty-icon">◌</span><h2>Your conversations, in view</h2><p>Select a chat to preview received replies and the messages you sent.</p></div>';return}
  const route=(thread.lead.folder_routes||[]).find(r=>r.account_id===thread.account_id),stopped=thread.lead.auto_yes?.completed_once;
  const newestFirst=$('#replyMessageOrder').value==='newest',messages=newestFirst?[...thread.messages].reverse():thread.messages;
  $('#replyConversation').innerHTML='<header class="inbox-chat-header"><span class="inbox-avatar">'+esc(inboxAvatar(thread.lead.name))+'</span><div><h2>'+esc(thread.lead.name)+'</h2><p>'+esc(thread.lead.username?'@'+thread.lead.username:'No public username')+' · '+esc(thread.lead.stage)+'</p>'+countryBadge(thread.lead.location)+locationButton(thread.lead)+'</div><button id="inboxManageLead">Lead / replies</button></header><div class="inbox-account"><b>Original sender: '+esc(thread.sender_label)+'</b><span>Account '+esc(thread.account_id)+(route?' · '+esc(route.desired):'')+(stopped?' · Automatic response sent once':'')+'</span></div><div class="inbox-messages" id="inboxMessages"><div class="inbox-date-note">Message preview · '+thread.messages.length+' saved messages</div>'+messages.map(m=>'<article class="inbox-bubble '+(m.direction==='sent'?'outgoing':'incoming')+(m.status==='Failed'||m.status==='Uncertain'?' needs-review':'')+'"><div class="inbox-bubble-label">'+(m.direction==='received'?esc(thread.lead.name):m.conversation_reply?'You · reply':m.automation_step?'Automatic reply · message '+m.automation_step:m.followup_of?'Follow-up':'You')+'</div><div class="inbox-bubble-body">'+esc(m.body)+'</div><footer><time>'+esc(inboxDate(m.at))+'</time><span>'+esc(m.status)+(m.status==='Sent'?' ✓':'')+'</span></footer>'+(m.error?'<p class="inbox-bubble-error">'+esc(m.error)+'</p>':'')+'</article>').join('')+'</div><div class="inbox-composer"><label for="inboxReplyText">Reply message</label><textarea id="inboxReplyText" maxlength="4096" placeholder="Write a reply to this conversation…"></textarea><details><summary>Message preview</summary><div id="inboxReplyPreview" class="messagecopy"></div></details><div class="crm-buttons"><span id="inboxReplyHint" class="hint"></span><button type="button" id="inboxSendReply" class="primary">Send reply</button></div></div>';
  const editor=$('#inboxReplyText'),sendButton=$('#inboxSendReply');editor.value=inboxReplyDrafts.get(thread.key)||'';
  const queued=queuedSends.some(q=>String(q.target)===thread.target&&['Queued','Sending'].includes(q.status));
  $('#inboxReplyHint').textContent=queued?'A message is pending for this contact. Check Pending sends.':'Uses '+thread.sender_label+' · Account '+thread.account_id+'. A delayed reply is saved on the server.';
  sendButton.disabled=!serverFeatures.manual_replies||!thread.original?.delivery_id||queued;
  if(!serverFeatures.manual_replies)$('#inboxReplyHint').textContent='Deploy the latest WMM backend on Render to send replies here.';
  function updateReplyPreview(){inboxReplyDrafts.set(thread.key,editor.value);$('#inboxReplyPreview').textContent=WMMMessageModel.personalize(editor.value,thread.lead,thread.original?.token_symbol||'',thread.original?.exchange||'')}
  editor.oninput=updateReplyPreview;updateReplyPreview();
  sendButton.onclick=()=>action(sendButton,async()=>{
    const text=editor.value.trim();if(!text)throw Error('Write a reply first.');
    let request=inboxReplyRequests.get(thread.key);if(!request||request.text!==text){request={text,id:uniqueRequest()};inboxReplyRequests.set(thread.key,request)}
    const result=await api('/conversation/reply',{delivery_id:thread.original.delivery_id,message:text,request_id:request.id});
    inboxReplyDrafts.delete(thread.key);inboxReplyRequests.delete(thread.key);editor.value='';await refresh(false);
    toast(result.status==='Queued'?'Reply queued on your server. You can close this tab.':'Reply sent from the original Telegram account.');
  });
  $('#inboxManageLead').onclick=()=>openLead(thread.lead.key);bindLocationActions($('#replyConversation'));
  const pane=$('#inboxMessages'),order=$('#replyMessageOrder').value;$('#replyConversation').dataset.threadKey=thread.key;$('#replyConversation').dataset.order=order;pane.scrollTop=priorKey===thread.key&&priorOrder===order?(newestFirst||!wasAtBottom?priorScroll:pane.scrollHeight):(newestFirst?0:pane.scrollHeight);
}
async function openWorkspaceReset(){
  if(!live)throw Error('Connect your gateway to reset workspace data.');
  if(!serverFeatures.workspace_reset)throw Error('Deploy the latest GitHub commit on Render to enable workspace reset.');
  const data=await api('/workspace/reset-preview');workspaceResetRequestId=uniqueRequest();
  $('#workspaceResetCounts').innerHTML=Object.entries(data.counts).map(([label,count])=>'<div><b>'+esc(count)+'</b><span>'+esc(label)+'</span></div>').join('');
  $('#workspaceResetConfirmation').value='';$('#workspaceResetStatus').textContent='';$('#confirmWorkspaceReset').disabled=true;$('#workspaceResetDialog').showModal();
}
document.addEventListener('DOMContentLoaded',()=>{
  $('#replyMessageOrder').onchange=renderReplyInbox;$('#replySearch').oninput=renderReplyInbox;$('#replyAccount').onchange=renderReplyInbox;
  $('#refreshReplyInbox').onclick=()=>action($('#refreshReplyInbox'),()=>refresh(false));
  $('#openWorkspaceReset').onclick=()=>action($('#openWorkspaceReset'),openWorkspaceReset);
  $('#workspaceResetConfirmation').oninput=()=>{$('#confirmWorkspaceReset').disabled=$('#workspaceResetConfirmation').value!=='RESET DATA'};
  $('#cancelWorkspaceReset').onclick=()=>{if(!busy)$('#workspaceResetDialog').close()};$('#workspaceResetDialog').addEventListener('cancel',e=>{if(busy)e.preventDefault()});
  $('#confirmWorkspaceReset').onclick=()=>action($('#confirmWorkspaceReset'),async()=>{
    if($('#workspaceResetConfirmation').value!=='RESET DATA')throw Error('Type RESET DATA to reset the workspace.');
    $('#workspaceResetStatus').textContent='Waiting for active operations, then clearing workspace records…';
    await api('/workspace/reset',{confirmation:'RESET DATA',request_id:workspaceResetRequestId});
    people=[];leads=[];deliveries=[];quotaResets=[];logs=[];queuedSends=[];inboxReplyDrafts.clear();inboxReplyRequests.clear();selected.clear();activeInboxKey=null;savedMessageContact=null;followupDelivery=null;$('#autoSend').checked=false;
    for(const dialog of $$('dialog[open]'))dialog.close();await refresh(false);renderReplyInbox();view('saved');toast('Workspace data reset. Telegram accounts and message templates were kept.');
  });
  renderReplyInbox();
});
