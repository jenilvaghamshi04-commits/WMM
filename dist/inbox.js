let activeInboxKey=null,workspaceResetRequestId=null;
function inboxDate(at){return at?new Date(at).toLocaleString():''}
function inboxAvatar(name){return String(name||'?').split(/\s+/).map(x=>x[0]).slice(0,2).join('').toUpperCase()}
function renderReplyInbox(){
  if(!$('#replyThreads'))return;
  const priorPane=$('#inboxMessages'),priorKey=$('#replyConversation').dataset.threadKey,priorOrder=$('#replyConversation').dataset.order,priorScroll=priorPane?.scrollTop||0,wasAtBottom=priorPane?priorPane.scrollHeight-priorPane.clientHeight-priorScroll<24:true;
  const threads=WMMInboxModel.filter(WMMInboxModel.conversations(leads,deliveries),$('#replySearch').value,$('#replyAccount').value);
  if(!threads.some(t=>t.key===activeInboxKey))activeInboxKey=threads[0]?.key||null;
  $('#replyInboxCount').textContent=threads.length+' conversation'+(threads.length===1?'':'s');
  $('#replyInboxHint').textContent=live?'Chats with received replies · newest activity first. The preview combines saved outgoing messages with up to 20 recent replies per contact.':'Connect your gateway to see received replies and message history.';
  $('#replyThreads').innerHTML=threads.length?threads.map(t=>'<button class="reply-thread '+(t.key===activeInboxKey?'active':'')+'" data-inbox-key="'+esc(t.key)+'"><span class="inbox-avatar">'+esc(inboxAvatar(t.lead.name))+'</span><span class="reply-thread-copy"><span class="reply-thread-title"><b>'+esc(t.lead.name)+'</b><time>'+esc(new Date(t.latest.at).toLocaleDateString())+'</time></span><span class="reply-thread-meta">'+esc(t.lead.username?'@'+t.lead.username:t.lead.group)+' · Account '+esc(t.account_id)+'</span><span class="reply-thread-snippet">'+esc(t.latest.body.slice(0,110))+'</span></span></button>').join(''):'<div class="inbox-empty"><b>'+(!live?'Connect your workspace':'No replies to preview')+'</b><p>'+(!live?'Log in or connect your gateway in Connections.':$('#replySearch').value?'Try another search or account filter.':'Received replies will appear here after your gateway detects them.')+'</p></div>';
  $('#replyThreads').querySelectorAll('[data-inbox-key]').forEach(b=>b.onclick=()=>{activeInboxKey=b.dataset.inboxKey;renderReplyInbox()});
  const thread=threads.find(t=>t.key===activeInboxKey);
  if(!thread){$('#replyConversation').innerHTML='<div class="inbox-empty inbox-empty-chat"><span class="inbox-empty-icon">◌</span><h2>Your conversations, in view</h2><p>Select a chat to preview received replies and the messages you sent.</p></div>';return}
  const route=(thread.lead.folder_routes||[]).find(r=>r.account_id===thread.account_id),stopped=thread.lead.auto_yes?.completed_once;
  const newestFirst=$('#replyMessageOrder').value==='newest',messages=newestFirst?[...thread.messages].reverse():thread.messages;
  $('#replyConversation').innerHTML='<header class="inbox-chat-header"><span class="inbox-avatar">'+esc(inboxAvatar(thread.lead.name))+'</span><div><h2>'+esc(thread.lead.name)+'</h2><p>'+esc(thread.lead.username?'@'+thread.lead.username:'No public username')+' · '+esc(thread.lead.stage)+'</p></div><button id="inboxManageLead">Lead / replies</button></header><div class="inbox-account"><b>Original sender: '+esc(thread.sender_label)+'</b><span>Account '+esc(thread.account_id)+(route?' · '+esc(route.desired):'')+(stopped?' · Automatic response sent once':'')+'</span></div><div class="inbox-messages" id="inboxMessages"><div class="inbox-date-note">Message preview · '+thread.messages.length+' saved messages</div>'+messages.map(m=>'<article class="inbox-bubble '+(m.direction==='sent'?'outgoing':'incoming')+(m.status==='Failed'||m.status==='Uncertain'?' needs-review':'')+'"><div class="inbox-bubble-label">'+(m.direction==='received'?esc(thread.lead.name):m.automation_step?'Automatic reply · message '+m.automation_step:m.followup_of?'Follow-up':'You')+'</div><div class="inbox-bubble-body">'+esc(m.body)+'</div><footer><time>'+esc(inboxDate(m.at))+'</time><span>'+esc(m.status)+(m.status==='Sent'?' ✓':'')+'</span></footer>'+(m.error?'<p class="inbox-bubble-error">'+esc(m.error)+'</p>':'')+'</article>').join('')+'</div><footer class="inbox-readonly">Conversation preview · Replies are received by the original Telegram account.</footer>';
  $('#inboxManageLead').onclick=()=>openLead(thread.lead.key);
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
    people=[];leads=[];deliveries=[];quotaResets=[];logs=[];selected.clear();activeInboxKey=null;savedMessageContact=null;followupDelivery=null;$('#autoSend').checked=false;
    for(const dialog of $$('dialog[open]'))dialog.close();await refresh(false);renderReplyInbox();view('replies');toast('Workspace data reset. Telegram accounts and message templates were kept.');
  });
  renderReplyInbox();
});
