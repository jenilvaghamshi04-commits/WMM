let queuedSends=[],queuedSendsTimer=null;
function renderQueuedSends(){
  const visible=queuedSends.filter(q=>['Queued','Sending','Needs attention'].includes(q.status));
  document.querySelectorAll('[data-queued-panel]').forEach(host=>{
    host.innerHTML=visible.length?'<div class="card" style="margin-bottom:18px"><div class="cardhead"><h2>Pending sends</h2><button data-cancel-all-queued>Stop pending sends</button></div><div class="inner"><p class="hint">Saved on your server. You can close the dialog or browser tab. The gateway must be running; if it sleeps, sending resumes after it wakes. Delays and daily limits stay in place.</p>'+visible.map(q=>'<div class="historyentry"><b>'+esc(q.name)+'</b> · Account '+q.account_id+' · <b>'+esc(q.status)+'</b><p class="hint">'+(q.status==='Queued'?'Not before '+esc(new Date(q.next_attempt_at).toLocaleString())+' · original sender retained':esc(q.error||'Sending now'))+'</p><details><summary>Message preview</summary><div class="messagecopy">'+esc(q.message)+'</div></details>'+(q.status==='Queued'?'<button data-cancel-queued="'+esc(q.queue_id)+'">Cancel this send</button>':'')+'</div>').join('')+'</div></div>':'';
    host.querySelectorAll('[data-cancel-queued]').forEach(button=>button.onclick=()=>action(button,async()=>{await rawApi('/send-queue/cancel',{id:button.dataset.cancelQueued});await refresh(false)}));
    const stop=host.querySelector('[data-cancel-all-queued]');if(stop)stop.onclick=()=>action(stop,async()=>{await rawApi('/send-queue/cancel',{});await refresh(false);toast('Pending sends cancelled. A message already in flight may finish.');});
  });
}
async function refreshQueuedSends(){const data=await rawApi('/status');queuedSends=data.queued_sends||[];renderQueuedSends()}
document.addEventListener('DOMContentLoaded',()=>{
  queuedSendsTimer=setInterval(async()=>{if(!live||!key||!serverFeatures.background_sends||busy||document.activeElement?.matches('textarea,input,select'))return;try{await refresh(false)}catch{}},5000);
});

function queuedContactBadge(contact){const q=queuedSends.find(q=>q.contact_id===(contact.id||contact.contact_id)&&["Queued","Sending"].includes(q.status));return q?'<p class="hint"><b>'+esc(q.status)+'</b> · Account '+q.account_id+' · saved on server</p>':''}
