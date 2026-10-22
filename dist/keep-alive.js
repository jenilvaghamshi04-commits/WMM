function renderKeepAliveSetup(){
  if(!document.querySelector('#serverHealthUrl'))return;
  document.querySelector('#serverHealthUrl').value=gateway?gateway.replace(/\/$/,'')+'/health':'';
  document.querySelector('#copyHealthUrl').disabled=!gateway;
  document.querySelector('#testServerHealth').disabled=!gateway;
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
    try{const response=await fetch(value,{cache:'no-store',signal:controller.signal}),data=await response.json();if(!response.ok||data.ok!==true||data.service!=='teamradar')throw Error('This URL did not return a healthy WMM server response.');result.textContent='Server is responding · checked '+new Date().toLocaleString()+'. Configure the external schedule with this server URL to keep checking every 10 minutes.';toast('WMM server is responding.')}catch(error){result.textContent=error.name==='AbortError'?'The server is still waking up or unavailable. Try the health check again shortly.':'Could not verify the WMM health endpoint. Check your Render service and gateway URL.';throw error}finally{clearTimeout(timeout)}
  });
  renderKeepAliveSetup();
});
