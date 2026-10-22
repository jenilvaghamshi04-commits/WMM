(function(root){
  const introduction="Hey @username! Hope you're doing well.\n\nI'm Mark from Wallstreet Market Maker (WMM).\n\nI recently came across $TOKEN and thought it would be worth connecting.\n\nWe work with crypto projects to improve trading liquidity, maintain healthier order books, and manage liquidity across exchanges.\n\nI believe there could be a good opportunity for us to work together.\n\nAre you the right person to discuss this with?";
  function type(contact){return contact.kind||'dm'}
  function summarize(rows){
    rows=rows.slice().sort((a,b)=>new Date(b.at)-new Date(a.at));
    const sent=rows.filter(d=>d.status==='Sent'),pending=rows.some(d=>d.status==='Sending'||d.status==='Uncertain');
    return {rows,sent,latest:rows[0]||null,lastSent:sent[0]||null,firstMessage:sent.filter(d=>!d.followup_of).at(-1)||rows.at(-1)||null,lastFollowup:sent.find(d=>d.followup_of)||null,followups:sent.filter(d=>!!d.followup_of).length,canSend:sent.length===0&&!pending,canFollowup:sent.length>0&&!pending,pending};
  }
  function conversation(contact,history){
    const k=type(contact),target=String(k==='group'?contact.group_id:contact.user_id);
    return summarize(history.filter(d=>(d.kind||'dm')===k&&(d.id===contact.id||(target!=='undefined'&&String(d.target)===target))));
  }
  function conversations(history){
    const grouped=new Map();
    for(const d of history){const key=(d.kind||'dm')+':'+(d.target??d.id);if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(d)}
    return [...grouped.values()].map(summarize).sort((a,b)=>new Date(b.latest.at)-new Date(a.latest.at));
  }
  function normalizeToken(value){return String(value||'').trim().replace(/^\$+/,'')}
  function requiresToken(text){return /\$TOKEN\b|\{\{token\}\}/.test(text||'')}
  function personalize(text,contact,tokenSymbol=''){
    const symbol=normalizeToken(tokenSymbol),handle=contact.username?'@'+String(contact.username).replace(/^@+/,''):(contact.name||'there');
    return String(text||'').replaceAll('@{{username}}',handle).replaceAll('{{username}}',handle).replaceAll('@username',handle).replaceAll('{{name}}',contact.name||'').replaceAll('{{role}}',contact.role||'').replaceAll('{{group}}',contact.group||'').replaceAll('{{token}}',symbol?'$'+symbol:'$TOKEN').replace(/\$TOKEN\b/g,symbol?'$'+symbol:'$TOKEN');
  }
  function status(summary){const d=summary.latest;if(!d)return 'Not sent';if(d.status==='Sending')return 'Sending';if(d.status==='Uncertain')return 'Delivery needs review';if(d.followup_of)return d.status==='Sent'?'Follow-up sent':'Follow-up '+d.status.toLowerCase();return d.status==='Sent'?'Message sent':d.status}
  root.WMMMessageModel={type,conversation,conversations,personalize,status,introduction,normalizeToken,requiresToken};
})(typeof window==='undefined'?globalThis:window);
