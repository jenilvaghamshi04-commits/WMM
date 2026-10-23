let countryOptions=null,locationContactId=null;
function localDate(at,zone){if(!at)return 'Not scheduled';try{return new Date(at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'})+' IST'}catch{return 'Choose a timezone'}}
function countryBadge(location){
  const l=location||{},known=!!l.country_code,source=l.country_source||'Unknown';
  const label=known?l.country_name:'Country unknown';
  return '<div class="country-badge '+(known?'known':'unknown')+'"><b>'+esc(label)+'</b>'+(known?'<span>'+esc(source)+'</span>':'')+'<span>'+esc(l.timezone||'Timezone needed for automatic follow-up')+(l.timezone_inferred?' · inferred':'')+'</span></div>';
}
function locationButton(contact){if((contact.kind||'dm')==='group')return '';return '<button type="button" data-location-id="'+esc(contact.contact_id||contact.id)+'">Country / timezone</button>'}
function contactLocation(contact){return contact?.location||leads.find(l=>l.contact_id===(contact?.id||contact?.contact_id))?.location||{}}
function bindLocationActions(container=document){container.querySelectorAll('[data-location-id]').forEach(button=>button.onclick=()=>action(button,()=>openLocationEditor(button.dataset.locationId)))}
function dialogLocation(id,contact){const target=document.getElementById(id);if(!target)return;target.innerHTML=(contact?.kind==='group'?'<span class="hint">Country scheduling applies to individual contacts.</span>':countryBadge(contactLocation(contact))+locationButton(contact));bindLocationActions(target)}
function timezoneOptions(country,current=''){
  const info=countryOptions?.countries.find(c=>c.code===country),zones=info?.timezones?.length?info.timezones:countryOptions?.timezones||[];
  const list=current&&!zones.includes(current)?[current,...zones]:zones;
  document.getElementById('locationTimezone').innerHTML='<option value="">Automatic only for a single-timezone country</option>'+list.map(z=>'<option value="'+esc(z)+'">'+esc(z)+'</option>').join('');
  document.getElementById('locationTimezone').value=current;
  updateLocationHint();
}
function updateLocationHint(){
  const select=document.getElementById('locationCountry'),code=select.value||select.dataset.detected||'',info=countryOptions?.countries.find(c=>c.code===code),chosen=document.getElementById('locationTimezone').value;
  document.getElementById('locationScheduleHint').textContent=chosen?'Automatic follow-up starts at 10:00 in '+chosen+'.':info?.timezones?.length===1?'Automatic timezone: '+info.timezones[0]+' · follow-up starts at 10:00 local.':info?.timezones?.length>1?'This country has multiple timezones. Choose the contact’s timezone; automatic follow-up waits until it is set.':'Country/timezone unknown. Choose a timezone to enable the local 10:00 follow-up.';
}
async function openLocationEditor(id){
  if(!live||!serverFeatures.country_timezones)throw Error('Deploy the latest WMM backend on Render to use country and timezone scheduling.');
  const contact=people.find(c=>c.id===id)||leads.find(l=>l.contact_id===id);if(!contact)throw Error('Refresh to load this saved contact.');
  if(!countryOptions)countryOptions=await api('/locations/options');locationContactId=id;
  const l=contactLocation(contact),select=document.getElementById('locationCountry');
  document.getElementById('locationName').textContent=contact.name;
  document.getElementById('locationEvidence').textContent=l.phone_country_code?'Telegram phone country: '+l.phone_country_name+'. A phone country does not verify where this person currently lives.':'Telegram has not provided a phone country for this contact.';
  select.dataset.detected=l.phone_country_code||'';select.innerHTML='<option value="">'+(l.phone_country_code?'Use Telegram phone country · '+esc(l.phone_country_name):'Country unknown')+'</option>'+countryOptions.countries.map(c=>'<option value="'+c.code+'">'+esc(c.name)+'</option>').join('');select.value=l.country_override||'';
  timezoneOptions(l.country_code||'',l.timezone_override||'');document.getElementById('locationEditor').showModal();
}
function refreshLocationViews(){bindLocationActions();if(savedMessageContact)savedMessageContact=people.find(c=>c.id===savedMessageContact.id)||savedMessageContact;if(followupDelivery)followupDelivery=deliveries.find(d=>d.delivery_id===followupDelivery.delivery_id)||followupDelivery;if(savedMessageContact)dialogLocation('contactLocationSummary',savedMessageContact);if(followupDelivery)dialogLocation('followupLocationSummary',contactForDelivery(followupDelivery));}
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('locationCountry').onchange=()=>{const e=document.getElementById('locationCountry');timezoneOptions(e.value||e.dataset.detected||'')};
  document.getElementById('locationTimezone').onchange=updateLocationHint;
  document.getElementById('closeLocationEditor').onclick=()=>{if(!busy)document.getElementById('locationEditor').close()};
  document.getElementById('saveLocation').onclick=()=>action(document.getElementById('saveLocation'),async()=>{
    await api('/locations/update',{contact_id:locationContactId,country:document.getElementById('locationCountry').value,timezone:document.getElementById('locationTimezone').value});await refresh(false);
    if(activeLeadKey&&document.getElementById('leadDialog').open){const lead=leads.find(l=>l.key===activeLeadKey);if(lead)populateLead(lead)}
    document.getElementById('locationEditor').close();toast('Country/timezone saved. Pending automatic follow-ups were rescheduled.');
  });
  document.getElementById('checkCountries').onclick=()=>action(document.getElementById('checkCountries'),async()=>{if(!serverFeatures.country_timezones)throw Error('Deploy the latest WMM backend on Render first.');const d=await api('/locations/check',{});await refresh(false);toast(d.checked?'Country lookup checked. Remaining contacts continue slowly in the background.':'Country checks are waiting for their next permitted time.');});
});
