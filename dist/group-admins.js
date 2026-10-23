/* Joined groups, saved admin snapshots, and progressive account setup. */
let groupAdminSnapshots=[],joinedGroupChoices=[],joinedGroupAccount=null,joinedGroupPrincipal=null,accountSlotCount=1;
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
function groupAdminCards(groups,demo=false){return groups.map(g=>`<article class="card tg-group-card"${demo?' data-demo="true"':''}><div class="tg-group-heading"><div><p class="eyebrow">${demo?'DEMO · '+(g.kind==='channel'?'CHANNEL':'GROUP'):(g.kind==='channel'?'CHANNEL':'GROUP')+' · ACCOUNT '+esc(g.account_id)}</p><h2>${esc(g.name)}</h2></div><span class="pill">${demo?'Demo · ':''}${g.admins.length} ${g.admins.length===1?'admin':'admins'}</span></div><dl class="tg-group-details"><div><dt>Group / Channel Name</dt><dd>${esc(g.name)}</dd></div><div><dt>Group Username</dt><dd>${g.username?'@'+esc(g.username):'No public username available'}</dd></div></dl><div class="tablewrap"><table><thead><tr><th>Admin Full Name</th><th>Admin @Username</th><th>User ID</th><th>Role</th><th>Tag / Title (CEO etc)</th><th>Scraped At</th></tr></thead><tbody>${g.admins.length?g.admins.map(a=>`<tr><td>${adminBatchCheckbox(a,g,demo)}</td><td>${a.username?'@'+esc(a.username):'<span class="hint">Not available</span>'}</td><td class="tg-user-id">${esc(a.user_id)}</td><td><span class="roletag">${esc(a.role)}</span></td><td>${a.title?esc(a.title):'<span class="hint">No title</span>'}</td><td>${a.scraped_at?esc(new Date(a.scraped_at).toLocaleString()):'Not recorded'}</td></tr>`).join(''):'<tr><td colspan="6" class="tg-empty">No non-bot admin records were visible to this account.</td></tr>'}</tbody></table></div><p class="hint tg-group-footer">${demo?'Sample timestamp':'Saved'} ${g.scraped_at?esc(new Date(g.scraped_at).toLocaleString()):'previously'}${g.legacy?' · Earlier scan':''}${g.archive?' · '+esc(groupArchiveLabel(g.archive)):''}</p></article>`).join('')}
function newGroupAdminSnapshots(){return groupAdminSnapshots.filter(g=>g.collection_source==='automatic_join')}
function renderGroupWatch(){
 const root=document.getElementById('tgWatchAccounts');if(!root)return;
 root.innerHTML=visibleAccounts().map(a=>{const w=a.group_watch||{},paused=a.blocked_until&&new Date(a.blocked_until)>new Date();
 const state=!a.authorized?'Connect this account':paused?'Paused by Telegram':!serverFeatures.new_group_watch?'Gateway update required':w.error||(!w.ready?'Recording existing groups…':'Watching for new groups');
 return `<div class="tg-watch-account"><b>Account ${a.id} · ${esc(a.label)}</b><span class="hint">${esc(state)}</span>${w.ready?`<small class="hint">Started ${esc(new Date(w.started_at).toLocaleString())} · ${Number(w.saved)||0} collected · ${Number(w.pending)||0} pending${w.unavailable?' · '+Number(w.unavailable)+' unavailable':''}</small>`:''}</div>`}).join('');
}
function renderGroupAdmins(){
 const root=document.getElementById('tgGroupRecords');if(!root)return;renderAdminBatchBar();renderGroupWatch();
 const q=document.getElementById('tgAdminSearch').value.trim().toLowerCase();
 const source=newGroupAdminSnapshots();
 const groups=source.slice().sort((a,b)=>(b.scraped_at||'').localeCompare(a.scraped_at||'')).filter(g=>[g.name,g.username,...g.admins.flatMap(a=>[a.name,a.username,a.user_id,a.role,a.title])].join(' ').toLowerCase().includes(q));
 document.getElementById('tgGroupCount').textContent=source.length+' saved '+(source.length===1?'group':'groups');
 document.getElementById('tgGroupGatewayHint').textContent=!live?'Connect your gateway and Telegram account to start watching new groups.':!serverFeatures.new_group_watch?'Deploy gateway v3.14 on Render to enable automatic collection.':'Checks run every 5 minutes while the gateway is running. New groups are read one at a time, at least 2 minutes apart. Refresh saved data to see the latest results.';
 root.innerHTML=groups.length?groupAdminCards(groups):'<div class="card tg-empty"><h2>'+ (q?'No matching new groups':'Waiting for your next group')+'</h2><p class="hint">'+(q?'Try another group, admin name or username.':'After monitoring starts, join a new group in Telegram. Its visible admins and titles will appear here automatically. Earlier groups are excluded.')+'</p></div>';
}
function resetJoinedGroupPicker(){joinedGroupChoices=[];joinedGroupAccount=null;joinedGroupPrincipal=null;document.getElementById('tgJoinedGroup').innerHTML='<option value="">Load new groups first…</option>';document.getElementById('tgJoinedGroup').disabled=true;document.getElementById('getGroupAdmins').disabled=true;document.getElementById('tgGroupsStatus').textContent=''}
function groupReadReady(){
 if(!live)throw Error('Connect your gateway first.');
 if(!serverFeatures.group_admin_directory)throw Error('Deploy the latest gateway on Render to use joined groups.');
 const id=Number(document.getElementById('tgGroupAccount').value),account=accounts.find(a=>a.id===id);
 if(!account?.authorized)throw Error('Connect Account '+id+' in Connections first.');
 if(account.blocked_until&&new Date(account.blocked_until)>new Date())throw Error('This account is paused until '+new Date(account.blocked_until).toLocaleString()+'. Saved admin records are still available.');
 return id;
}
document.addEventListener('DOMContentLoaded',()=>{
 initializeAdminBatch();
 document.getElementById('tgAdminSearch').oninput=renderGroupAdmins;
 document.getElementById('tgGroupAccount').onchange=()=>{resetJoinedGroupPicker();document.getElementById('tgGroupsStatus').textContent='Click Refresh new groups for the selected account.'};
 document.getElementById('addNewGroupData').onclick=()=>action(document.getElementById('addNewGroupData'),async()=>{document.getElementById('tgNewGroupPicker').hidden=false;await loadNewJoinedGroups()});
 document.getElementById('tgJoinedGroup').onchange=()=>{document.getElementById('getGroupAdmins').disabled=!document.getElementById('tgJoinedGroup').value};
 document.getElementById('loadJoinedGroups').onclick=()=>action(document.getElementById('loadJoinedGroups'),loadNewJoinedGroups);
 document.getElementById('getGroupAdmins').onclick=()=>action(document.getElementById('getGroupAdmins'),async()=>{
  const id=groupReadReady(),groupId=document.getElementById('tgJoinedGroup').value;
  if(joinedGroupAccount!==id||!joinedGroupChoices.some(g=>g.group_id===groupId))throw Error('Load joined groups for the selected account first.');
  if(!serverFeatures.new_group_picker_archive)throw Error('Deploy gateway v3.15 on Render to collect and archive new groups.');
  document.getElementById('tgGroupsStatus').textContent='Saving visible admins, then archiving this group…';
  try{const result=await api('/groups/new/admins',{account_id:id,group_id:groupId,watch_principal:joinedGroupPrincipal});await refresh(false);resetJoinedGroupPicker();document.getElementById('tgGroupsStatus').textContent=result.count+' visible admins saved for '+result.group+'. '+groupArchiveLabel(result.archive);toast('Admin data saved. '+groupArchiveLabel(result.archive));
  }catch(error){document.getElementById('tgGroupsStatus').textContent=error.message;try{await refresh(false)}catch{}throw error}
 });
 document.getElementById('refreshGroupAdminData').onclick=()=>action(document.getElementById('refreshGroupAdminData'),()=>refresh(false));
 renderAccountSelectors();renderGroupAdmins();
});
async function loadNewJoinedGroups(){
 const id=groupReadReady();resetJoinedGroupPicker();
 if(!serverFeatures.new_group_picker_archive)throw Error('Deploy gateway v3.15 on Render to use Add new group data.');
 document.getElementById('tgGroupsStatus').textContent='Checking new joined groups for Account '+id+'…';
 try{const result=await api('/groups/new',{account_id:id});joinedGroupChoices=result.groups;joinedGroupAccount=id;joinedGroupPrincipal=result.watch_principal;
  const node=document.getElementById('tgJoinedGroup');node.innerHTML='<option value="">Choose a new joined group…</option>'+joinedGroupChoices.map(g=>`<option value="${esc(g.group_id)}">${esc(g.name)}${g.username?' · @'+esc(g.username):''}${g.status==='Unavailable'?' · previous read unavailable':''}</option>`).join('');node.disabled=!joinedGroupChoices.length;
  document.getElementById('tgGroupsStatus').textContent=joinedGroupChoices.length?joinedGroupChoices.length+' new joined groups available. Choose one, then Get admins & archive.':'No new unsaved groups found. Earlier groups are excluded; already collected groups appear below.';
 }catch(error){document.getElementById('tgGroupsStatus').textContent=error.message;throw error}
}
function groupArchiveLabel(archive){return !archive?'':archive.status==='Archived'?'Archived in Telegram.':archive.status==='Pending'?'Archive pending · admin data is saved.':archive.error||'Archive: '+archive.status}
