import os,json,sqlite3,asyncio,secrets,re
from datetime import datetime,timezone
from pathlib import Path
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,SecretStr,Field
from telethon import TelegramClient,functions,types,errors

ROOT=Path(os.getenv('DATA_DIR','./data')); ROOT.mkdir(parents=True,exist_ok=True); os.chmod(ROOT,0o700)
KEY=os.environ['DASHBOARD_KEY']
API_ID=os.getenv('TELEGRAM_API_ID'); API_HASH=os.getenv('TELEGRAM_API_HASH')
app=FastAPI(title='TeamRadar gateway')
app.add_middleware(CORSMiddleware,allow_origins=[os.getenv('SITE_ORIGIN','https://teamradar-telegram-desk.jenilvaghamshi04.chatgpt.site')],allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
client=None
lock=asyncio.Lock(); phone_hash={}
db=sqlite3.connect(ROOT/'desk.db',check_same_thread=False)
db.execute('create table if not exists contacts(id text primary key, data text)')
db.execute('create table if not exists settings(id integer primary key, data text)')
db.execute('create table if not exists telegram_api(id integer primary key, api_id integer, api_hash text)')
db.execute('create table if not exists deliveries(id text primary key, status text, at text, error text)');db.commit()

def make_client():
    row=db.execute('select api_id,api_hash from telegram_api where id=1').fetchone()
    api_id,api_hash=row if row else (API_ID,API_HASH)
    return TelegramClient(str(ROOT/'telegram'),int(api_id),api_hash,flood_sleep_threshold=0) if api_id and api_hash else None

client=make_client()
def require_client():
    if client is None:raise HTTPException(409,'Save your Telegram API ID and API Hash in Connections first')

def auth(authorization:str=Header(default='')):
    if not secrets.compare_digest(authorization,'Bearer '+KEY): raise HTTPException(401,'Invalid dashboard key')

def settings():
    row=db.execute('select data from settings where id=1').fetchone();return json.loads(row[0]) if row else {'template':'','sheet_url':''}
def contacts(): return [json.loads(r[0]) for r in db.execute('select data from contacts')]
def save(c): db.execute('insert or replace into contacts values(?,?)',(c['id'],json.dumps(c)));db.commit()
def stamp():return datetime.now(timezone.utc).isoformat()
@app.on_event('startup')
async def start():
    if client:await client.connect()
@app.on_event('shutdown')
async def stop():
    if client:await client.disconnect()
@app.exception_handler(errors.FloodWaitError)
async def flood(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=429,content={'detail':f'Telegram requires a {exc.seconds} second wait. Try later; no automatic retry.'})
class Login(BaseModel): phone:str
class Verify(BaseModel): phone:str; code:str=''; password:str=''
class Scan(BaseModel): link:str; join:bool=False
class Config(BaseModel): template:str=''; sheet_url:str=''
class Send(BaseModel): id:str
class TelegramAPI(BaseModel):
    api_id:int=Field(gt=0)
    api_hash:SecretStr

@app.get('/health')
async def health():return {'service':'teamradar','ok':True}

@app.post('/telegram-api',dependencies=[Depends(auth)])
async def configure_telegram_api(body:TelegramAPI):
    global client
    value=body.api_hash.get_secret_value().strip()
    if not re.fullmatch(r'[a-fA-F0-9]{32}',value):raise HTTPException(400,'API Hash must contain 32 hexadecimal characters from my.telegram.org')
    async with lock:
        if client and await client.is_user_authorized():raise HTTPException(409,'Disconnect your Telegram session before replacing API credentials')
        candidate=TelegramClient(str(ROOT/'telegram'),body.api_id,value,flood_sleep_threshold=0)
        if client:await client.disconnect()
        try:await candidate.connect()
        except Exception:
            await candidate.disconnect()
            if client:await client.connect()
            raise HTTPException(502,'Could not reach Telegram. API settings were not saved; try again later.')
        db.execute('insert or replace into telegram_api values(1,?,?)',(body.api_id,value));db.commit()
        client=candidate
    return {'api_configured':True}

@app.get('/status',dependencies=[Depends(auth)])
async def status(): return {'api_configured':client is not None,'authorized':await client.is_user_authorized() if client else False,'contacts':contacts(),'settings':settings(),'deliveries':[dict(zip(['id','status','at','error'],r)) for r in db.execute('select * from deliveries')]}
@app.post('/login',dependencies=[Depends(auth)])
async def login(body:Login):
    require_client()
    async with lock:
        r=await client.send_code_request(body.phone);phone_hash[body.phone]=r.phone_code_hash
    return {'ok':True}
@app.post('/verify',dependencies=[Depends(auth)])
async def verify(body:Verify):
    require_client()
    async with lock:
        try:
            if body.password: await client.sign_in(password=body.password)
            else: await client.sign_in(body.phone,body.code,phone_code_hash=phone_hash.get(body.phone))
        except errors.SessionPasswordNeededError:return {'password_required':True}
    return {'authorized':True}
@app.post('/logout',dependencies=[Depends(auth)])
async def logout():
    require_client()
    async with lock: await client.log_out();await client.connect()
    return {'ok':True}
@app.post('/scan',dependencies=[Depends(auth)])
async def scan(body:Scan):
    require_client()
    if not await client.is_user_authorized():raise HTTPException(409,'Connect your Telegram account first')
    link=body.link.strip().replace('https://t.me/','').replace('http://t.me/','').strip('/')
    if not link or '/' in link and not link.startswith('joinchat/'):raise HTTPException(400,'Use a group username or invite link, not a post link')
    async with lock:
        try:
            if link.startswith('+') or link.startswith('joinchat/'):
                invite=link.split('/')[-1].lstrip('+')
                if body.join:
                    try:r=await client(functions.messages.ImportChatInviteRequest(invite));entity=r.chats[0]
                    except errors.UserAlreadyParticipantError:
                        r=await client(functions.messages.CheckChatInviteRequest(invite));entity=r.chat
                else:
                    r=await client(functions.messages.CheckChatInviteRequest(invite))
                    if not isinstance(r,types.ChatInviteAlready):raise HTTPException(409,'Enable Join before scan to join this private group')
                    entity=r.chat
            else:
                entity=await client.get_entity(link.lstrip('@'))
                if body.join and isinstance(entity,types.Channel):await client(functions.channels.JoinChannelRequest(entity))
            if isinstance(entity,types.Chat):
                full=await client(functions.messages.GetFullChatRequest(entity.id)); users={u.id:u for u in full.users}
                people=[(users[p.user_id],p) for p in full.full_chat.participants.participants if isinstance(p,(types.ChatParticipantAdmin,types.ChatParticipantCreator))]
            else:
                users=await client.get_participants(entity,filter=types.ChannelParticipantsAdmins)
                people=[(u,u.participant) for u in users]
            result=[]
            for u,p in people:
                if u.bot or u.deleted:continue
                rank=getattr(p,'rank',None) or ''
                owner=isinstance(p,(types.ChannelParticipantCreator,types.ChatParticipantCreator))
                c={'id':str(entity.id)+':'+str(u.id),'user_id':str(u.id),'name':(' '.join(filter(None,[u.first_name,u.last_name])) or 'Unnamed admin'),'username':u.username or '', 'group':entity.title,'link':body.link,'role':'Owner' if owner else (rank or 'Admin'),'title':rank,'source':'Telegram admin title' if rank else 'Telegram permissions','scanned_at':stamp(),'status':'Ready'}
                save(c);result.append(c)
            return {'contacts':result,'group':entity.title,'count':len(result)}
        except errors.InviteRequestSentError:raise HTTPException(409,'Join request sent. Scan after an administrator approves it.')
        except errors.ChatAdminRequiredError:raise HTTPException(403,'Telegram hides this admin list from your account. Try its linked discussion group or ask for access.')
        except HTTPException:raise
        except errors.RPCError as exc:raise HTTPException(400,str(exc))
@app.post('/settings',dependencies=[Depends(auth)])
async def config(body:Config):
    if body.sheet_url and 'docs.google.com/spreadsheets/d/' not in body.sheet_url:raise HTTPException(400,'Paste a Google Sheets URL, not a Google Doc')
    db.execute('insert or replace into settings values(1,?)',(body.model_dump_json(),));db.commit();return {'ok':True}
async def deliver(cid):
    require_client()
    async with lock:
        row=db.execute('select data from contacts where id=?',(cid,)).fetchone()
        if not row:raise HTTPException(404,'Contact not found')
        previous=db.execute('select status from deliveries where id=?',(cid,)).fetchone()
        if previous and previous[0] in ('Sent','Sending','Uncertain'):raise HTTPException(409,'Already sent or awaiting review. Duplicate blocked.')
        template=settings()['template'].strip()
        if not template:raise HTTPException(400,'Save your custom message first')
        c=json.loads(row[0]);msg=template.replace('{{name}}',c['name']).replace('{{role}}',c['role']).replace('{{group}}',c['group'])
        db.execute('insert or replace into deliveries values(?,?,?,?)',(cid,'Sending',stamp(),''));db.commit()
        try:
            await client.send_message(await client.get_input_entity(int(c['user_id'])),msg)
        except errors.FloodWaitError as exc:
            db.execute('update deliveries set status=?,error=? where id=?',('Failed',f'Wait {exc.seconds}s',cid));db.commit();raise
        except errors.RPCError as exc:
            db.execute('update deliveries set status=?,error=? where id=?',('Failed',str(exc),cid));db.commit();raise HTTPException(400,str(exc))
        except Exception:
            db.execute('update deliveries set status=?,error=? where id=?',('Uncertain','Check Telegram before retrying',cid));db.commit();raise HTTPException(502,'Delivery uncertain; check Telegram before retrying')
        db.execute('update deliveries set status=?,at=? where id=?',('Sent',stamp(),cid));db.commit();return {'status':'Sent','id':cid}
@app.post('/send',dependencies=[Depends(auth)])
async def send(body:Send):return await deliver(body.id)
@app.post('/sheet-send',dependencies=[Depends(auth)])
async def sheet_send(body:Send):return await deliver(body.id)
def sync_sheet():
    import gspread
    cfg=settings()
    if not cfg['sheet_url']:raise HTTPException(400,'Save a Google Sheets URL first')
    if not os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'):raise HTTPException(409,'Configure GOOGLE_SERVICE_ACCOUNT_JSON on the gateway and share the sheet with its client_email')
    gc=gspread.service_account_from_dict(json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']))
    book=gc.open_by_url(cfg['sheet_url'])
    try:ws=book.worksheet('TeamRadar')
    except gspread.WorksheetNotFound:ws=book.add_worksheet('TeamRadar',rows=1000,cols=12)
    existing=ws.get_all_values();checks={r[0]:r[6] for r in existing[1:] if len(r)>6}
    rows=[['Contact ID','Name','Username','Role / title','Group','Profile','Send message','Delivery status','Scanned at']]
    for c in contacts():
        d=db.execute('select status from deliveries where id=?',(c['id'],)).fetchone()
        rows.append([c['id'],c['name'],'@'+c['username'] if c['username'] else '',c['role'],c['group'],'https://t.me/'+c['username'] if c['username'] else '',checks.get(c['id'],'FALSE'),d[0] if d else 'Ready',c['scanned_at']])
    ws.clear();ws.update(values=rows,range_name='A1',value_input_option='RAW');ws.freeze(rows=1)
    if len(rows)>1:book.batch_update({'requests':[{'setDataValidation':{'range':{'sheetId':ws.id,'startRowIndex':1,'endRowIndex':len(rows),'startColumnIndex':6,'endColumnIndex':7},'rule':{'condition':{'type':'BOOLEAN'},'strict':True,'showCustomUi':True}}}]})
    return {'ok':True,'rows':len(rows)-1}
@app.post('/sync',dependencies=[Depends(auth)])
async def sync():return sync_sheet()

# Serve the dashboard on the same origin when this repository is deployed as one app.
from fastapi.staticfiles import StaticFiles
STATIC_DIR=Path(__file__).resolve().parent/"dist"
if not STATIC_DIR.exists():STATIC_DIR=Path(__file__).resolve().parent.parent/"dist"
if STATIC_DIR.exists():app.mount("/",StaticFiles(directory=str(STATIC_DIR),html=True),name="dashboard")
