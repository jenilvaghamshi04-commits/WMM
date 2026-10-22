const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('backend/sheet-trigger.gs','utf8');
for(const scenario of [{response:429,body:{detail:{code:'send_cooldown',message:'Wait 120 seconds'}},expected:'Wait 120 seconds',unchecked:true},{response:200,body:{status:'Sent'},expected:'Sent',unchecked:false}]){
 let writes=[],unchecked=false,fetches=0;const status={getValue:()=>'',setValue:value=>writes.push(value)};
 const sheet={getName:()=>'TeamRadar',getRange:(row,column)=>column===8?status:{getValue:()=>'qa-contact'}};
 const range={getSheet:()=>sheet,getColumn:()=>7,getRow:()=>2,getNumRows:()=>1,getNumColumns:()=>1,setValue:value=>{unchecked=value===false}};
 const context=vm.createContext({LockService:{getScriptLock:()=>({tryLock:()=>true,releaseLock(){}})},PropertiesService:{getScriptProperties:()=>({getProperty:name=>name==='GATEWAY_URL'?'https://synthetic.example':'qa-key'})},UrlFetchApp:{fetch:()=>{fetches++;return {getContentText:()=>JSON.stringify(scenario.body),getResponseCode:()=>scenario.response}}},event:{range,value:'TRUE'}});
 vm.runInContext(code+'\nteamRadarOnEdit(event)',context);
 assert.equal(writes.at(-1),scenario.expected);assert.equal(unchecked,scenario.unchecked);assert.equal(fetches,1);
}
console.log('2 sheet pacing scenarios passed: readable cooldown/manual retry and confirmed success.');
