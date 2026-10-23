const activeHeartbeatInterval=10*60*1000;
let activeHeartbeatTimer=null,activeHeartbeatController=null,activeHeartbeatTarget='',activeHeartbeatLast=0;
function activeHeartbeatUrl(){
  const base=typeof gateway==='string'&&gateway?gateway.replace(/\/$/,''):window.location.hostname.endsWith('.onrender.com')?window.location.origin:'';
  return base?base+'/api/health':'';
}
function heartbeatStatus(text){const node=document.getElementById('activeHeartbeatStatus');if(node)node.textContent=text}
async function pingWhileVisible(force=false){
  if(document.visibilityState!=='visible')return;
  const url=activeHeartbeatUrl();if(!url){heartbeatStatus('Connect your gateway to start the browser heartbeat.');return}
  if(activeHeartbeatController)return;
  if(!force&&url===activeHeartbeatTarget&&Date.now()-activeHeartbeatLast<activeHeartbeatInterval)return;
  activeHeartbeatTarget=url;activeHeartbeatLast=Date.now();activeHeartbeatController=new AbortController();
  const controller=activeHeartbeatController,timeout=setTimeout(()=>controller.abort(),90000);
  heartbeatStatus('Checking server…');
  try{
    const options={cache:'no-store',credentials:'omit',signal:controller.signal};
    let response=await fetch(url,options);
    // Existing gateways already expose /health. Keep them compatible until redeployed.
    if(response.status===404)response=await fetch(url.replace(/\/api\/health$/,'/health'),options);
    const data=await response.json();
    if(!response.ok||data.ok!==true||data.service!=='teamradar')throw Error('Health check unavailable');
    heartbeatStatus('Browser heartbeat active · checked '+new Date().toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour12:true,timeZoneName:'short'})+'. Next check in 10 minutes while this page is visible.');
  }catch{heartbeatStatus('Server is waking up or unavailable. The next browser heartbeat will try again; you can also use Check server now.');}
  finally{clearTimeout(timeout);if(activeHeartbeatController===controller)activeHeartbeatController=null}
}
function startVisibleHeartbeat(){if(!activeHeartbeatTimer)activeHeartbeatTimer=setInterval(()=>pingWhileVisible(true),activeHeartbeatInterval);void pingWhileVisible()}
function stopVisibleHeartbeat(){clearInterval(activeHeartbeatTimer);activeHeartbeatTimer=null;if(activeHeartbeatController)activeHeartbeatController.abort();activeHeartbeatController=null}
function renderKeepAliveSetup(){
  if(!document.querySelector('#serverHealthUrl'))return;
  document.querySelector('#serverHealthUrl').value=gateway?gateway.replace(/\/$/,'')+'/health':'';
  document.querySelector('#copyHealthUrl').disabled=!gateway;
  document.querySelector('#testServerHealth').disabled=!gateway;
  startVisibleHeartbeat();
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelector('#copyHealthUrl').onclick=()=>action(document.querySelector('#copyHealthUrl'),async()=>{
    const value=document.querySelector('#serverHealthUrl').value;if(!value)throw Error('Connect your gateway first.');
    try{await navigator.clipboard.writeText(value);toast('Health URL copied. Use it for the external keep-alive setup.')}catch{document.querySelector('#serverHealthUrl').select();toast('Select and copy the health URL shown above.')}
  });
  document.querySelector('#testServerHealth').onclick=()=>action(document.querySelector('#testServerHealth'),async()=>{
    const value=document.querySelector('#serverHealthUrl').value;if(!value)throw Error('Connect your gateway first.');
    const result=document.querySelector('#serverHealthResult'),controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),90000);
    result.textContent='Checking the server… A sleeping Render service can take a minute to wake up.';
    try{const response=await fetch(value,{cache:'no-store',signal:controller.signal}),data=await response.json();if(!response.ok||data.ok!==true||data.service!=='teamradar')throw Error('This URL did not return a healthy WMM server response.');result.textContent='Server is responding · checked '+new Date().toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:true,timeZoneName:'short'})+'. Configure the external schedule with this server URL to keep checking every 10 minutes.';toast('WMM server is responding.')}catch(error){result.textContent=error.name==='AbortError'?'The server is still waking up or unavailable. Try the health check again shortly.':'Could not verify the WMM health endpoint. Check your Render service and gateway URL.';throw error}finally{clearTimeout(timeout)}
  });
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')void pingWhileVisible(true);else heartbeatStatus('Browser heartbeat paused while this page is hidden. It resumes when you return.');});
  window.addEventListener('pagehide',stopVisibleHeartbeat);
  window.addEventListener('pageshow',()=>{startVisibleHeartbeat();void pingWhileVisible(true)});
  renderKeepAliveSetup();
});
