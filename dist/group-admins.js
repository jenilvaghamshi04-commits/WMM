/* Joined groups, saved admin snapshots, and progressive account setup. */
let groupAdminSnapshots=[],joinedGroupChoices=[],joinedGroupAccount=null,accountSlotCount=1;
function visibleAccounts(){return accounts.filter(a=>a.id<=accountSlotCount||a.authorized||a.api_configured)}
function renderAccountSelectors(){
 const visible=visibleAccounts();
 for(const id of ['loginAccount','tgGroupAccount']){
  const node=document.getElementById(id),previous=node.value;
  node.innerHTML=visible.map(a=>`<option value="${a.id}">Account ${a.id} — ${esc(a.label)}${a.authorized?' ✓':''}</option>`).join('');
  if(visible.some(a=>String(a.id)===previous))node.value=previous;
 }
 const filter=document.getElementById('replyAccount'),previous=filter.value;
 filter.innerHTML='<option value="all">All original accounts</option>'+visible.map(a=>`<option value="${a.id}">Account ${a.id}</option>`).join('');
 if([...filter.options].some(o=>o.value===previous))filter.value=previous;
 document.querySelectorAll('[data-add-account]').forEach(b=>{b.hidden=visible.length>=3;b.disabled=!live;b.onclick=()=>action(b,async()=>{
  if(!serverFeatures.progressive_accounts)throw Error('Deploy the latest gateway on Render to add account slots.');
  const result=await api('/accounts/add',{});await refresh(false);document.getElementById('loginAccount').value=String(result.account_id);clearLogin();renderLogin();view('connections');toast('Account '+result.account_id+' added. Enter its API details and connect it.');
 })});
}
function applyAccountSetup(status){
 accountSlotCount=Math.max(1,Math.min(3,Number(status.account_slots)||Math.max(1,...accounts.filter(a=>a.authorized||a.api_configured).map(a=>a.id))));
 renderAccountSelectors();
}
function legacyGroupAdminSnapshots(){
 const groups=new Map();
 for(const p of people){
  if(p.kind==='group'||!p.scan_account||!p.group_id||p.is_bot)continue;
  const id=p.group_id+':'+p.scan_account;
  if(!groups.has(id)){const chat=people.find(c=>c.kind==='group'&&c.group_id===p.group_id);groups.set(id,{key:'legacy:'+id,group_id:p.group_id,name:p.group,username:p.group_username||chat?.username||'',account_id:p.scan_account,kind:'group',scraped_at:p.scanned_at||'',admins:[],legacy:true})}
  const g=groups.get(id);g.admins.push({name:p.name,username:p.username,user_id:p.user_id,role:p.admin_role||(p.role==='Owner'?'Owner':'Admin'),title:p.title||'',scraped_at:p.scanned_at||''});if((p.scanned_at||'')>g.scraped_at)g.scraped_at=p.scanned_at;
 }
 return [...groups.values()];
}
function renderGroupAdmins(){
 const root=document.getElementById('tgGroupRecords');if(!root)return;
 const q=document.getElementById('tgAdminSearch').value.trim().toLowerCase();
 const source=serverFeatures.group_admin_directory?groupAdminSnapshots:legacyGroupAdminSnapshots();
 const groups=source.slice().sort((a,b)=>(b.scraped_at||'').localeCompare(a.scraped_at||'')).filter(g=>[g.name,g.username,...g.admins.flatMap(a=>[a.name,a.username,a.user_id,a.role,a.title])].join(' ').toLowerCase().includes(q));
 document.getElementById('tgGroupCount').textContent=source.length+' saved '+(source.length===1?'group':'groups');
 document.getElementById('tgGroupGatewayHint').textContent=!live?'Connect your gateway and Telegram account to load joined groups.':!serverFeatures.group_admin_directory?'Deploy the latest gateway on Render to load joined groups. Earlier saved scans are shown below.':'Select one joined group and load its visible admins. Saved results stay available after refresh.';
 root.innerHTML=groups.length?groups.map(g=>`<article class="card tg-group-card"><div class="tg-group-heading"><div><p class="eyebrow">${g.kind==='channel'?'CHANNEL':'GROUP'} · ACCOUNT ${esc(g.account_id)}</p><h2>${esc(g.name)}</h2></div><span class="pill">${g.admins.length} ${g.admins.length===1?'admin':'admins'}</span></div><dl class="tg-group-details"><div><dt>Group / Channel Name</dt><dd>${esc(g.name)}</dd></div><div><dt>Group Username</dt><dd>${g.username?'@'+esc(g.username):'No public username available'}</dd></div></dl><div class="tablewrap"><table><thead><tr><th>Admin Full Name</th><th>Admin @Username</th><th>User ID</th><th>Role</th><th>Tag / Title (CEO etc)</th><th>Scraped At</th></tr></thead><tbody>${g.admins.length?g.admins.map(a=>`<tr><td><b>${esc(a.name)}</b></td><td>${a.username?'@'+esc(a.username):'<span class="hint">Not available</span>'}</td><td class="tg-user-id">${esc(a.user_id)}</td><td><span class="roletag">${esc(a.role)}</span></td><td>${a.title?esc(a.title):'<span class="hint">No title</span>'}</td><td>${a.scraped_at?esc(new Date(a.scraped_at).toLocaleString()):'Not recorded'}</td></tr>`).join(''):'<tr><td colspan="6" class="tg-empty">No non-bot admin records were visible to this account.</td></tr>'}</tbody></table></div><p class="hint tg-group-footer">Saved ${g.scraped_at?esc(new Date(g.scraped_at).toLocaleString()):'previously'}${g.legacy?' · Earlier scan':''}</p></article>`).join(''):'<div class="card tg-empty"><h2>'+ (q?'No matching groups':'No groups saved yet')+'</h2><p class="hint">'+(q?'Try another group, admin name or username.':'Choose an account, load joined groups, then select a group and click Get admins. Existing scans also appear here.')+'</p></div>';
}
function resetJoinedGroupPicker(){joinedGroupChoices=[];joinedGroupAccount=null;document.getElementById('tgJoinedGroup').innerHTML='<option value="">Load joined groups first…</option>';document.getElementById('tgJoinedGroup').disabled=true;document.getElementById('getGroupAdmins').disabled=true;document.getElementById('tgGroupsStatus').textContent=''}
function groupReadReady(){
 if(!live)throw Error('Connect your gateway first.');
 if(!serverFeatures.group_admin_directory)throw Error('Deploy the latest gateway on Render to use joined groups.');
 const id=Number(document.getElementById('tgGroupAccount').value),account=accounts.find(a=>a.id===id);
 if(!account?.authorized)throw Error('Connect Account '+id+' in Connections first.');
 if(account.blocked_until&&new Date(account.blocked_until)>new Date())throw Error('This account is paused until '+new Date(account.blocked_until).toLocaleString()+'. Saved admin records are still available.');
 return id;
}
document.addEventListener('DOMContentLoaded',()=>{
 document.getElementById('tgAdminSearch').oninput=renderGroupAdmins;
 document.getElementById('tgGroupAccount').onchange=resetJoinedGroupPicker;
 document.getElementById('tgJoinedGroup').onchange=()=>{document.getElementById('getGroupAdmins').disabled=!document.getElementById('tgJoinedGroup').value};
 document.getElementById('loadJoinedGroups').onclick=()=>action(document.getElementById('loadJoinedGroups'),async()=>{
  const id=groupReadReady();document.getElementById('tgGroupsStatus').textContent='Loading joined groups for Account '+id+'…';
  try{const result=await api('/groups/joined',{account_id:id});joinedGroupChoices=result.groups;joinedGroupAccount=id;
   const node=document.getElementById('tgJoinedGroup');node.innerHTML='<option value="">Choose a joined group…</option>'+joinedGroupChoices.map(g=>`<option value="${esc(g.group_id)}">${esc(g.name)}${g.username?' · @'+esc(g.username):''}</option>`).join('');node.disabled=!joinedGroupChoices.length;document.getElementById('getGroupAdmins').disabled=true;
   document.getElementById('tgGroupsStatus').textContent=joinedGroupChoices.length+' joined groups / channels available.'+(result.cached?' Using the recent list (cached for 10 minutes).':'')+(result.truncated?' Only the first 1,000 chats were checked; use Find team for another joined group.':'');
  }catch(error){document.getElementById('tgGroupsStatus').textContent=error.message;throw error}
 });
 document.getElementById('getGroupAdmins').onclick=()=>action(document.getElementById('getGroupAdmins'),async()=>{
  const id=groupReadReady(),groupId=document.getElementById('tgJoinedGroup').value;
  if(joinedGroupAccount!==id||!joinedGroupChoices.some(g=>g.group_id===groupId))throw Error('Load joined groups for the selected account first.');
  document.getElementById('tgGroupsStatus').textContent='Reading visible admins…';
  try{const result=await api('/groups/admins',{account_id:id,group_id:groupId});await refresh(false);document.getElementById('tgGroupsStatus').textContent=result.count+' visible admins saved for '+result.group+'.';toast('Admin records saved. No messages were sent.');
  }catch(error){document.getElementById('tgGroupsStatus').textContent=error.message;try{await refresh(false)}catch{}throw error}
 });
 document.getElementById('refreshGroupAdminData').onclick=()=>action(document.getElementById('refreshGroupAdminData'),()=>refresh(false));
 renderAccountSelectors();renderGroupAdmins();
});
