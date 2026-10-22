(function(root){
  const time=value=>{const n=Date.parse(value);return Number.isFinite(n)?n:0};
  const key=(principal,target)=>JSON.stringify([String(principal),String(target)]);
  function conversations(leads,deliveries){
    const threads=new Map();
    for(const lead of leads){
      if(lead.kind!=='dm')continue;
      for(const reply of lead.replies||[]){
        if(reply.principal==null||lead.target==null)continue;
        const id=key(reply.principal,lead.target);
        if(!threads.has(id))threads.set(id,{key:id,principal:String(reply.principal),target:String(lead.target),lead,messages:[],seen:new Set()});
        const thread=threads.get(id),rid='reply:'+String(reply.message_id??reply.at);
        if(thread.seen.has(rid))continue;thread.seen.add(rid);
        thread.messages.push({key:rid,direction:'received',body:reply.body||'[Media message]',at:reply.at,account_id:reply.account_id,status:'Received'});
      }
    }
    for(const delivery of deliveries){
      if((delivery.kind||'dm')!=='dm')continue;
      const thread=threads.get(key(delivery.principal,delivery.target));if(!thread)continue;
      const did='send:'+delivery.delivery_id;if(thread.seen.has(did))continue;thread.seen.add(did);
      thread.messages.push({key:did,direction:'sent',body:delivery.message||'Message text is unavailable for this older record.',at:delivery.at,account_id:delivery.account_id,sender_label:delivery.sender_label,status:delivery.status,error:delivery.error,automation_step:delivery.automation_step,followup_of:delivery.followup_of});
    }
    return [...threads.values()].map(thread=>{
      thread.messages.sort((a,b)=>time(a.at)-time(b.at)||a.key.localeCompare(b.key));
      thread.latest=thread.messages.at(-1);thread.latestReply=[...thread.messages].reverse().find(m=>m.direction==='received');
      thread.original=thread.messages.find(m=>m.direction==='sent'&&!m.followup_of)||thread.messages.find(m=>m.direction==='sent');
      thread.account_id=thread.original?.account_id??thread.latestReply?.account_id;thread.sender_label=thread.original?.sender_label||'Account '+thread.account_id;
      delete thread.seen;return thread;
    }).sort((a,b)=>time(b.latest?.at)-time(a.latest?.at)||a.key.localeCompare(b.key));
  }
  function filter(threads,search='',account='all'){
    const q=String(search).trim().toLocaleLowerCase();return threads.filter(t=>(account==='all'||String(t.account_id)===String(account))&&(!q||[t.lead.name,t.lead.username,t.lead.group,t.sender_label,...t.messages.map(m=>m.body)].join(' ').toLocaleLowerCase().includes(q)));
  }
  root.WMMInboxModel={conversations,filter};
})(typeof window==='undefined'?globalThis:window);
