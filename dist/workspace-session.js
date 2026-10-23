/* Same-tab dashboard sessions. Telegram credentials and workspace records stay on the server. */
(function(root){
  const name='wmm.dashboard.session.v1';
  const pages=new Set(['directory','groups','saved','sent','replies','pipeline','templates','health','activity','connections']);
  const filterIds=['savedType','role','sentScope','sentStatus','replyMessageOrder','replyAccount','leadFilter','leadType'];
  function create(storage){
    function clear(){try{storage.removeItem(name)}catch{}}
    function read(){
      try{
        const value=JSON.parse(storage.getItem(name)||'null');
        if(!value)return null;
        const url=new URL(value.gateway);
        if(url.protocol!=='https:'||url.username||url.password||!value.token||typeof value.token!=='string'||!Number.isFinite(Date.parse(value.expiresAt))||Date.parse(value.expiresAt)<=Date.now()){clear();return null}
        return {gateway:value.gateway,token:value.token,expiresAt:value.expiresAt,page:pages.has(value.page)?value.page:'directory',filters:Object.fromEntries(filterIds.filter(id=>typeof value.filters?.[id]==='string'&&value.filters[id].length<64).map(id=>[id,value.filters[id]]))};
      }catch{clear();return null}
    }
    function save(session){try{storage.setItem(name,JSON.stringify(session));return !!read()}catch{return false}}
    function page(value){const session=read();if(session&&pages.has(value))save({...session,page:value})}
    function filter(id,value){const session=read();if(session&&filterIds.includes(id))save({...session,filters:{...session.filters,[id]:value}})}
    return {read,save,page,filter,clear};
  }
  const api={create};if(typeof module==='object'&&module.exports)module.exports=api;else root.WMMWorkspaceSession=api;
})(typeof window==='object'?window:globalThis);
