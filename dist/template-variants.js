(function(root){
  function normalize(options,fallback=''){return Array.from({length:5},(_,i)=>String(options?.[i]??(i===0?fallback:'')))}
  function pick(options,random=Math.random){
    const filled=normalize(options).map((text,index)=>({text:text.trim(),index})).filter(v=>v.text);
    if(!filled.length)throw Error('Add at least one saved message option for this message type.');
    return filled[Math.min(filled.length-1,Math.floor(random()*filled.length))];
  }
  root.WMMTemplateVariants={normalize,pick};
})(typeof window==='undefined'?globalThis:window);
let savedTemplateVariants={},templateVariantDrafts={},templateVariantActive={},contactAutoTemplates=null,initialBatchPlan=null;
function legacyTemplateValue(key){return ({template:savedTemplate,followup_template:savedFollowupTemplate,yes_pitch_template:savedYesPitch,yes_demo_template:savedYesDemo})[key]||({template:WMMMessageModel.introduction,followup_template:WMMMessageModel.followup,yes_pitch_template:WMMMessageModel.yesPitch,yes_demo_template:WMMMessageModel.yesDemo})[key]}
function hydrateTemplateVariants(cfg){
  const previous=JSON.stringify(savedTemplateVariants);savedTemplateVariants={};
  for(const [,key,fallback] of templateFields)savedTemplateVariants[key]=WMMTemplateVariants.normalize(cfg.template_variants?.[key],cfg[key]||WMMMessageModel[fallback]);
  if(previous!==JSON.stringify(savedTemplateVariants))initialBatchPlan=null;
}
function pickSavedTemplate(key){const options=savedTemplateVariants[key];return WMMTemplateVariants.pick(options?.some(text=>text.trim())?options:[legacyTemplateValue(key)])}
function loadVariantEditors(){
  for(const [id,key,fallback] of templateFields){
    templateVariantDrafts[id]=WMMTemplateVariants.normalize(savedTemplateVariants[key],legacyTemplateValue(key)||WMMMessageModel[fallback]);if(!templateVariantDrafts[id].some(text=>text.trim()))templateVariantDrafts[id][0]=legacyTemplateValue(key)||WMMMessageModel[fallback];
    templateVariantActive[id]??=0;
    document.getElementById(id+'TemplateEditor').value=templateVariantDrafts[id][templateVariantActive[id]];
    renderVariantTabs(id);
  }
}
function renderVariantTabs(id){
  const host=document.getElementById(id+'VariantTabs');if(!host)return;
  const active=templateVariantActive[id]||0,options=templateVariantDrafts[id]||[];
  host.innerHTML=Array.from({length:5},(_,i)=>'<button type="button" role="tab" aria-selected="'+(active===i)+'" aria-controls="'+id+'TemplateEditor" data-variant-slot="'+i+'">Option '+(i+1)+' <span>'+(options[i]?.trim()?'●':'○')+'</span></button>').join('');
  host.querySelectorAll('button').forEach(button=>button.onclick=()=>{
    templateVariantDrafts[id][active]=document.getElementById(id+'TemplateEditor').value;
    templateVariantActive[id]=Number(button.dataset.variantSlot);
    document.getElementById(id+'TemplateEditor').value=templateVariantDrafts[id][templateVariantActive[id]];
    renderVariantTabs(id);host.querySelector('[data-variant-slot="'+templateVariantActive[id]+'"]').focus();updateTemplatePreviews();
  });
  const count=options.filter(s=>s.trim()).length;
  document.getElementById(id+'VariantHint').textContent=count+' of 5 options ready · editing option '+(active+1)+'. Blank options are ignored.';
  document.querySelector('label[for="'+id+'TemplateEditor"]').textContent='Option '+(active+1)+' message text';
}
function updateVariantDraft(id){
  if(!templateVariantDrafts[id])return;
  templateVariantDrafts[id][templateVariantActive[id]||0]=document.getElementById(id+'TemplateEditor').value;
  // Preserve focus/caret while typing; tab buttons only change when switching options.
  const active=templateVariantActive[id]||0,host=document.getElementById(id+'VariantTabs');
  if(host){const dot=host.querySelector('[data-variant-slot="'+active+'"] span');if(dot)dot.textContent=templateVariantDrafts[id][active].trim()?'●':'○'}
  document.getElementById(id+'VariantHint').textContent=templateVariantDrafts[id].filter(s=>s.trim()).length+' of 5 options ready · editing option '+(active+1)+'. Blank options are ignored.';
}
function readVariantDrafts(){
  const variants={};for(const [id,key] of templateFields){updateVariantDraft(id);variants[key]=templateVariantDrafts[id].map(s=>s.trim());if(!variants[key].some(Boolean))throw Error('Add at least one option for each message type.');}
  return variants;
}
function chooseContactInitial(){
  const choice=pickSavedTemplate('template');document.getElementById('contactMessageText').value=choice.text;
  document.getElementById('contactVariantChoice').textContent='Random initial message · option '+(choice.index+1)+' selected. This text is sent exactly as previewed.';
}
function chooseContactAutoTemplates(){
  contactAutoTemplates={};const choices=[];
  for(const [key,label] of [['yes_pitch_template','yes pitch'],['yes_demo_template','call invitation']]){const pick=pickSavedTemplate(key);contactAutoTemplates[key]=pick.text;choices.push(label+' option '+(pick.index+1));}
  document.getElementById('contactAutoVariantChoice').textContent='Selected for this contact: '+choices.join(' · ')+'. These texts are kept with this conversation.';
}
function chooseFollowupTemplate(){
  const choice=pickSavedTemplate('followup_template');document.getElementById('followupMessage').value=choice.text;
  document.getElementById('followupVariantChoice').textContent='Random follow-up · option '+(choice.index+1)+' selected. Review or edit it before sending.';
}
function getInitialBatchPlan(ids){
  const signature=JSON.stringify([ids,savedTemplateVariants.template||[legacyTemplateValue('template')]]);
  if(!initialBatchPlan||initialBatchPlan.signature!==signature)initialBatchPlan={signature,messages:new Map(ids.map(id=>[id,pickSavedTemplate('template')]))};
  return initialBatchPlan.messages;
}
function composeUsesVariants(){return document.getElementById('composeTemplateMode').value==='random'}
function renderComposeVariantMode(){
  const random=composeUsesVariants(),editor=document.getElementById('template');editor.readOnly=random;editor.hidden=random;
  const heading=editor.previousElementSibling,tokens=editor.nextElementSibling;if(heading?.classList.contains('messagehead'))heading.hidden=random;if(tokens?.classList.contains('tokenrow'))tokens.hidden=random;document.getElementById('saveMessage').hidden=random;
  document.getElementById('composeVariantHint').textContent=random?'Each recipient gets one random saved initial option. Use Preview to see their exact text; the choices stay fixed for this batch. Edit your saved options in Message templates.':'The custom text below will be used for every selected recipient.';
  document.getElementById('previewBox').hidden=true;
}
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('composeToken').addEventListener('input',()=>{document.getElementById('previewBox').hidden=true});
  document.getElementById('composeTemplateMode').onchange=()=>{initialBatchPlan=null;renderComposeVariantMode()};renderComposeVariantMode();
  document.getElementById('rerollContactTemplate').onclick=()=>{chooseContactInitial();document.getElementById('contactMessageFormat').value='saved';updateContactPreview()};
  document.getElementById('rerollFollowupTemplate').onclick=()=>{chooseFollowupTemplate();updateFollowupPreview()};
});
