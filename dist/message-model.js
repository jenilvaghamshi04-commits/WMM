(function(root){
  function type(contact){return contact.kind||'dm'}
  function conversation(contact,history){
    const k=type(contact),target=String(k==='group'?contact.group_id:contact.user_id);
    const rows=history.filter(d=>(d.kind||'dm')===k&&(d.id===contact.id||(target!=='undefined'&&String(d.target)===target))).slice().sort((a,b)=>new Date(b.at)-new Date(a.at));
    const sent=rows.filter(d=>d.status==='Sent'),pending=rows.some(d=>d.status==='Sending'||d.status==='Uncertain');
    return {rows,sent,latest:rows[0]||null,lastSent:sent[0]||null,followups:sent.filter(d=>!!d.followup_of).length,canSend:sent.length===0&&!pending,canFollowup:sent.length>0&&!pending,pending};
  }
  function personalize(text,contact){return String(text||'').replaceAll('{{name}}',contact.name||'').replaceAll('{{role}}',contact.role||'').replaceAll('{{group}}',contact.group||'')}
  function status(summary){
    const d=summary.latest;
    if(!d)return 'Not sent';
    if(d.status==='Sending')return 'Sending';
    if(d.status==='Uncertain')return 'Delivery needs review';
    if(d.followup_of)return d.status==='Sent'?'Follow-up sent':'Follow-up '+d.status.toLowerCase();
    return d.status==='Sent'?'Message sent':d.status;
  }
  root.WMMMessageModel={type,conversation,personalize,status};
})(typeof window==='undefined'?globalThis:window);
