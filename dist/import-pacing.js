// Shared pacing for reviewed sends. Only an explicit server cooldown is retried.
let pendingSendStopped=false;
function beginPacedAction(){pendingSendStopped=false}
function finishPacedAction(){document.querySelectorAll('[data-send-progress]').forEach(e=>e.textContent='');document.querySelectorAll('[data-stop-pending]').forEach(e=>e.hidden=true)}
function showSendWait(text){document.querySelectorAll('[data-send-progress]').forEach(e=>e.textContent=text);document.querySelectorAll('[data-stop-pending]').forEach(e=>e.hidden=false)}
async function api(path,body){
  const sends=['/send','/follow-up','/sheet-send','/conversation/reply'].includes(path);
  if(sends&&!serverFeatures.send_pacing)throw Error('Deploy the latest WMM backend on Render before sending. This version requires server-enforced message delays.');
  if(sends&&pendingSendStopped)throw Error('Pending sends stopped.');
  const choices=sends&&path!=='/sheet-send'?messageTemplateChoices(path,body):{};
  const request=sends?{...body,template_choices:choices}:body;
  try{const result=await rawApi(path,request);if(sends)recordTemplateChoices(choices);return result}
  catch(error){
    if(sends&&await recoverTemplatePreview(error))throw Error('Saved options updated. Review the new preview, then send again.');
    if(!sends||error.code!=='send_cooldown')throw error;
    if(!serverFeatures.background_sends)throw Error('Deploy the latest WMM backend on Render for background sending. This message was not queued; reopen its preview after deployment.');
    if(path==='/sheet-send')throw error;
    let result;
    try{result=await rawApi('/send-queue',{request_id:uniqueRequest(),action:path==='/conversation/reply'?'reply':path==='/follow-up'?'follow-up':'send',payload:request})}
    catch(queueError){if(await recoverTemplatePreview(queueError))throw Error('Saved options updated. Review the new preview, then send again.');throw queueError}
    recordTemplateChoices(choices);await refreshQueuedSends();return result;
  }
}
function renderPacingSetup(settings){
  const select=document.getElementById('sendDelay');if(!select)return;
  select.value=String(settings?.send_delay_seconds||120);
  document.getElementById('pacingState').textContent=serverFeatures.send_pacing?'Server delay active for manual messages, follow-ups and automatic replies.':'Deploy the latest WMM backend on Render to enable sending delays and imports.';
}
let importSheetData=null,importBatchId=null;
function clearImportPreview(){importBatchId=null;document.getElementById('confirmImport').disabled=true;document.getElementById('importPreviewBody').replaceChildren();document.getElementById('importSummary').textContent='Preview the rows before adding them.'}
function importColumnOptions(headers,selected){return '<option value="">Not used</option>'+headers.map((h,i)=>'<option value="'+i+'" '+(i===selected?'selected':'')+'>'+esc(String.fromCharCode(65+i)+' · '+(h||'Column '+(i+1)))+'</option>').join('')}
async function readImportSheet(){
  if(!live||!serverFeatures.contact_import)throw Error('Connect the gateway running the latest WMM backend to import a sheet.');
  const file=document.getElementById('importFile').files[0],url=document.getElementById('importSheetUrl').value.trim();
  if(!!file===!!url)throw Error('Choose one file or paste one Google Sheets URL.');
  let body;
  if(file){
    if(file.size>5*1024*1024)throw Error('Choose a file up to 5 MB.');
    const encoded=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(Error('Could not read the file.'));r.readAsDataURL(file)});
    body={filename:file.name,content_base64:encoded};
  }else body={sheet_url:url,worksheet:document.getElementById('importWorksheet').value.trim()};
  clearImportPreview();importSheetData=null;document.getElementById('importMapping').hidden=true;
  const d=await api('/contacts/import/read',body);importSheetData=d;
  document.getElementById('importHeader').checked=d.has_header;
  const headers=d.rows[0];
  for(const field of ['telegram','name','role','group','kind','country','timezone'])document.getElementById('importColumn_'+field).innerHTML=importColumnOptions(headers,d.mapping[field]);
  document.getElementById('importMapping').hidden=false;document.getElementById('importMapping').open=true;
  document.getElementById('importSummary').textContent=d.rows.length+' rows read. Check the columns, then preview.';
}
async function previewImportSheet(){
  if(!importSheetData)throw Error('Read a sheet first.');
  clearImportPreview();const mapping={};
  for(const field of ['telegram','name','role','group','kind','country','timezone']){const value=document.getElementById('importColumn_'+field).value;mapping[field]=value===''?null:Number(value)}
  const d=await api('/contacts/import/preview',{rows:importSheetData.rows,mapping,has_header:document.getElementById('importHeader').checked,default_kind:document.getElementById('importDefaultKind').value,source_name:importSheetData.source_name});
  importBatchId=d.batch_id;document.getElementById('importMapping').open=false;
  document.getElementById('importPreviewBody').innerHTML=d.items.map(row=>'<tr><td>'+row.row+'</td><td>'+esc(row.name||'—')+'<div class="tiny">'+esc(row.telegram)+'</div></td><td>'+esc(row.kind||'—')+'<div class="tiny">'+esc(row.country||'Country unknown')+(row.timezone?' · '+esc(row.timezone):'')+'</div></td><td><b>'+esc(row.status)+'</b><div class="tiny">'+esc(row.reason)+'</div></td></tr>').join('');
  document.getElementById('importSummary').textContent=d.ready+' ready to add · '+d.duplicates+' duplicates · '+d.skipped+' skipped. Nothing has been sent.';
  document.getElementById('confirmImport').disabled=!d.ready;
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('[data-stop-pending]').forEach(b=>b.onclick=async()=>{pendingSendStopped=true;if(serverFeatures.background_sends){await rawApi('/send-queue/cancel',{});await refreshQueuedSends()}showSendWait('Pending sends stopped. A message already in flight may finish.');document.querySelectorAll('[data-stop-pending]').forEach(e=>e.hidden=true)});
  document.getElementById('saveSendDelay').onclick=()=>action(document.getElementById('saveSendDelay'),async()=>{await api('/sending-pace',{delay_seconds:Number(document.getElementById('sendDelay').value)});await refresh(false);toast('Sending delay saved for all accounts. Existing cooldowns are preserved.');});
  document.getElementById('openImport').onclick=()=>{clearImportPreview();document.getElementById('importDialog').showModal()};
  document.getElementById('closeImport').onclick=()=>{if(!busy)document.getElementById('importDialog').close()};
  document.getElementById('readImport').onclick=()=>action(document.getElementById('readImport'),readImportSheet);
  document.getElementById('previewImport').onclick=()=>action(document.getElementById('previewImport'),previewImportSheet);
  document.getElementById('confirmImport').onclick=()=>action(document.getElementById('confirmImport'),async()=>{
    if(!importBatchId)throw Error('Preview the sheet again before importing.');
    const d=await api('/contacts/import/confirm',{batch_id:importBatchId});importBatchId=null;
    await refresh(false);document.getElementById('importDialog').close();view('saved');toast(d.added+' contacts added to Saved data · '+d.duplicates+' newly detected duplicates skipped.');log('Sheet imported',d.added+' contacts added; no messages sent.');
  });
  document.querySelectorAll('#importMapping select,#importHeader').forEach(e=>e.addEventListener('change',clearImportPreview));
  for(const id of ['importFile','importSheetUrl','importWorksheet'])document.getElementById(id).addEventListener('change',()=>{clearImportPreview();importSheetData=null;document.getElementById('importMapping').hidden=true});
});
