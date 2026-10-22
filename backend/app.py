import os,json,sqlite3,asyncio,secrets,re,hashlib,uuid
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Depends,Header,HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,SecretStr,Field
from telethon import TelegramClient,functions,types,errors,utils,events

ROOT=Path(os.getenv('DATA_DIR','./data'));ROOT.mkdir(parents=True,exist_ok=True);os.chmod(ROOT,0o700)
KEY=os.environ['DASHBOARD_KEY']
API_ID=os.getenv('TELEGRAM_API_ID');API_HASH=os.getenv('TELEGRAM_API_HASH')
TZ=ZoneInfo('Asia/Kolkata');LIMITS={'dm':15,'group':30};DAILY_GOAL=10
app=FastAPI(title='WMM Team',version='3.2')
app.add_middleware(CORSMiddleware,allow_origins=[os.getenv('SITE_ORIGIN','https://teamradar-telegram-desk.jenilvaghamshi04.chatgpt.site')],allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
lock=asyncio.Lock();phone_hash={};clients={};startup_errors={};reply_task=None
db=sqlite3.connect(ROOT/'desk.db',check_same_thread=False)
db.execute('create table if not exists contacts(id text primary key, data text)')
db.execute('create table if not exists settings(id integer primary key, data text)')
db.execute('create table if not exists telegram_api(id integer primary key, api_id integer, api_hash text)')
db.execute('create table if not exists deliveries(id text primary key, status text, at text, error text)')
db.execute('create table if not exists account_info(slot integer primary key, principal text, label text, phone text, blocked_until text)')
db.execute('create table if not exists outbox(id text primary key, principal text, slot integer, kind text, target text, contact_id text, status text, day text, at text, error text, message_hash text)')
db.execute('create table if not exists quota_resets(id text primary key, principal text, slot integer, kind text, day text, after_rowid integer, at text, before_used integer, request_id text, unique(request_id,kind))')
db.execute('create table if not exists dashboard_sessions(token_hash text primary key, username text, expires_at text)')
db.execute('create table if not exists login_failures(client_hash text, at text)')
db.execute('create table if not exists message_details(delivery_id text primary key, body text, recipient_name text, username text, sender_label text, followup_of text)')
if 'token_symbol' not in {r[1] for r in db.execute('pragma table_info(message_details)')}:db.execute("alter table message_details add column token_symbol text not null default ''")
db.execute('create table if not exists followup_requests(request_id text primary key, delivery_id text, parent_id text, message_hash text)')
db.execute('create table if not exists meta(key text primary key, value text)')
db.execute("create table if not exists lead_settings(key text primary key, stage text, reminder_days integer not null default 3, reminders_enabled integer not null default 1, acknowledged_at text not null default '', updated_at text not null default '')")
db.execute('create table if not exists replies(principal text, target text, message_id integer, slot integer, at text, body text, primary key(principal,target,message_id))')
db.execute('create index if not exists reply_target on replies(target,at)')
db.execute('create table if not exists reply_sync(principal text, target text, cursor integer not null default 0, checked_at text, next_check_at text, complete integer not null default 0, error text, primary key(principal,target))')
# Preserve confirmed legacy deliveries when upgrading from the single-account version.
if not db.execute("select 1 from meta where key='outbox_migrated'").fetchone():
    for cid,status,at,error in db.execute('select * from deliveries').fetchall():
        c=db.execute('select data from contacts where id=?',(cid,)).fetchone()
        target=json.loads(c[0]).get('user_id',cid) if c else cid
        try:day=datetime.fromisoformat(at).astimezone(TZ).date().isoformat()
        except ValueError:day=datetime.now(TZ).date().isoformat()
        db.execute('insert into outbox values(?,?,?,?,?,?,?,?,?,?,?)',('legacy:'+cid,'slot:1',1,'dm',str(target),cid,status,day,at,error,''))
    db.execute("insert into meta values('outbox_migrated','1')")
# A process may have stopped after Telegram accepted a message. Never resend blindly.
db.execute("update outbox set status='Uncertain',error='Server restarted during delivery; check Telegram' where status='Sending'");db.commit()

DASHBOARD_USERNAME=os.getenv('DASHBOARD_USERNAME','admin')
DASHBOARD_PASSWORD=os.getenv('DASHBOARD_PASSWORD') or KEY

def auth(authorization:str=Header(default='')):
    if secrets.compare_digest(authorization.encode(),('Bearer '+KEY).encode()):return DASHBOARD_USERNAME
    token=authorization.removeprefix('Bearer ')
    row=db.execute('select username,expires_at from dashboard_sessions where token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row and row[1]>datetime.now(timezone.utc).isoformat():return row[0]
    raise HTTPException(401,'Please log in to WMM Team')

class DashboardLogin(BaseModel):
    username:str=Field(max_length=128)
    password:SecretStr

@app.post('/auth/login')
async def dashboard_login(body:DashboardLogin,request:Request):
    ip=request.client.host if request.client else 'unknown'
    client_hash=hashlib.sha256(ip.encode()).hexdigest()
    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    db.execute('delete from login_failures where at<?',(cutoff,));db.commit()
    if db.execute('select count(*) from login_failures where client_hash=?',(client_hash,)).fetchone()[0]>=5:
        raise HTTPException(429,'Too many failed logins. Try again after 15 minutes.')
    valid_user=secrets.compare_digest(body.username.encode(),DASHBOARD_USERNAME.encode())
    valid_password=secrets.compare_digest(body.password.get_secret_value().encode(),DASHBOARD_PASSWORD.encode())
    if not (valid_user and valid_password):
        db.execute('insert into login_failures values(?,?)',(client_hash,datetime.now(timezone.utc).isoformat()));db.commit()
        raise HTTPException(401,'Incorrect username or password')
    token=secrets.token_urlsafe(32)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
    db.execute('delete from dashboard_sessions where expires_at<=?',(datetime.now(timezone.utc).isoformat(),))
    db.execute('insert into dashboard_sessions values(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),DASHBOARD_USERNAME,expiry));db.commit()
    return {'access_token':token,'username':DASHBOARD_USERNAME,'expires_at':expiry}

@app.post('/auth/logout',dependencies=[Depends(auth)])
async def dashboard_logout(authorization:str=Header(default='')):
    db.execute('delete from dashboard_sessions where token_hash=?',(hashlib.sha256(authorization.removeprefix('Bearer ').encode()).hexdigest(),));db.commit()
    return {'ok':True}

def stamp():return datetime.now(timezone.utc).isoformat()
def today():return datetime.now(TZ).date().isoformat()
DEFAULT_FOLLOWUP="Hey, just following up on my previous message. Is improving liquidity and order-book depth something your team is currently exploring?\nHappy to share how WMM could help. If someone else handles this, could you point me their way?"
def settings():
    r=db.execute('select data from settings where id=1').fetchone()
    return {'template':'','followup_template':DEFAULT_FOLLOWUP,'sheet_url':'','sender_account':1,'token_symbol':'',**(json.loads(r[0]) if r else {})}
def contacts():
    rows=[c for r in db.execute('select data from contacts order by rowid desc') if not (c:=json.loads(r[0])).get('is_bot',False)]
    return sorted(rows,key=lambda c:c.get('scanned_at') or '',reverse=True)
def save(c):db.execute('insert or replace into contacts values(?,?)',(c['id'],json.dumps(c)));db.commit()
def session_path(slot):return str(ROOT/('telegram' if slot==1 else f'telegram_{slot}'))
def make_client(slot):
    r=db.execute('select api_id,api_hash from telegram_api where id=?',(slot,)).fetchone()
    api_id,api_hash=r if r else ((API_ID,API_HASH) if slot==1 else (None,None))
    return attach_reply_listener(TelegramClient(session_path(slot),int(api_id),api_hash,flood_sleep_threshold=0),slot) if api_id and api_hash else None
def require_client(slot):
    c=clients.get(slot)
    if c is None:raise HTTPException(409,f'Configure the API for Account {slot} in Connections first')
    return c
async def ready(slot):
    c=require_client(slot)
    if not c.is_connected():await c.connect()
    if not await c.is_user_authorized():raise HTTPException(409,f'Log in to Account {slot} first')
    return c
async def identify(slot,c):
    me=await c.get_me();principal=str(me.id)
    # One Telegram identity cannot consume three independent sets of limits.
    for other in (1,2,3):
        if other==slot:continue
        oc=clients.get(other)
        if oc and oc.is_connected() and await oc.is_user_authorized():
            om=await oc.get_me()
            if om.id==me.id:raise HTTPException(409,f'This Telegram account is already logged in as Account {other}')
    label=' '.join(filter(None,[getattr(me,'first_name',''),getattr(me,'last_name','')])) or f'Account {slot}'
    phone=getattr(me,'phone','') or ''
    old=db.execute('select blocked_until from account_info where principal=? order by blocked_until desc limit 1',(principal,)).fetchone()
    db.execute('insert or replace into account_info values(?,?,?,?,?)',(slot,principal,label,('••••'+phone[-4:]) if phone else '',old[0] if old else ''))
    db.execute('update outbox set principal=? where principal=?',(principal,f'slot:{slot}'));db.commit()
    return principal

def quota_floor(principal,kind,date):
    r=db.execute('select max(after_rowid) from quota_resets where principal=? and kind=? and day=?',(principal,kind,date)).fetchone()
    return r[0] or 0

def new_dm_count(principal,date,floor=0,confirmed_only=False):
    successful=" and o.status='Sent'" if confirmed_only else ''
    query="""select count(distinct o.target) from outbox o
        where o.principal=? and o.kind='dm' and o.day=? and o.rowid>?
        and not exists(select 1 from outbox prior where prior.principal=o.principal and prior.kind='dm'
        and prior.target=o.target and prior.status='Sent' and prior.rowid<o.rowid)"""+successful
    return db.execute(query,(principal,date,floor)).fetchone()[0]

def dm_needs_new_slot(principal,target,date):
    existing=db.execute("select 1 from outbox where principal=? and kind='dm' and target=? and status='Sent' limit 1",(principal,target)).fetchone()
    counted=db.execute("select 1 from outbox where principal=? and kind='dm' and target=? and day=? and rowid>? limit 1",(principal,target,date,quota_floor(principal,'dm',date))).fetchone()
    return not (existing or counted)

def usage(principal):
    date=today();result={}
    for kind,limit in LIMITS.items():
        floor=quota_floor(principal,kind,date)
        count=new_dm_count(principal,date,floor) if kind=='dm' else db.execute('select count(*) from outbox where principal=? and kind=? and day=? and rowid>?',(principal,kind,date,floor)).fetchone()[0]
        result[kind]={'used':count,'limit':limit,'remaining':max(0,limit-count),'basis':'new_recipients' if kind=='dm' else 'message_attempts'}
    return result

def sent_in_current_quota(principal):
    date=today()
    return new_dm_count(principal,date,quota_floor(principal,'dm',date),True)+db.execute("select count(*) from outbox where principal=? and kind='group' and day=? and rowid>? and status='Sent'",(principal,date,quota_floor(principal,'group',date))).fetchone()[0]

def reset_records():
    keys=['reset_id','principal','account_id','kind','day','after_rowid','at','before_used','request_id']
    return [dict(zip(keys,r)) for r in db.execute('select * from quota_resets order by rowid desc limit 100')]
def account_health(principal,client,authorized,blocked_until,startup_error=''):
    try:connected=bool(client and client.is_connected())
    except Exception:connected=False
    metrics=dict(db.execute('select status,count(*) from outbox where principal=? and day=? group by status',(principal,today())).fetchall())
    uncertain_total=db.execute("select count(*) from outbox where principal=? and status='Uncertain'",(principal,)).fetchone()[0]
    last_sent=db.execute("select at from outbox where principal=? and status='Sent' order by at desc limit 1",(principal,)).fetchone()
    last_error=db.execute("select error,at from outbox where principal=? and status in ('Failed','Uncertain') order by at desc limit 1",(principal,)).fetchone()
    paused=bool(blocked_until and blocked_until>stamp())
    if not client:state='Not configured'
    elif not connected:state='Disconnected'
    elif not authorized:state='Login required'
    elif paused:state='Paused'
    elif metrics.get('Failed',0) or uncertain_total or startup_error:state='Needs review'
    else:state='Ready'
    return {'state':state,'connected':connected,'checked_at':stamp(),'failed_today':metrics.get('Failed',0),'uncertain_today':metrics.get('Uncertain',0),'uncertain_total':uncertain_total,'sent_today_total':metrics.get('Sent',0),'last_sent_at':last_sent[0] if last_sent else None,'last_error':startup_error or (last_error[0] if last_error else ''),'last_error_at':last_error[1] if last_error else None,'blocked_until':blocked_until if paused else None}

def records():
    keys=['delivery_id','principal','account_id','kind','target','id','status','day','at','error','message_hash']
    result=[]
    for r in db.execute('select * from outbox order by at desc').fetchall():
        d=dict(zip(keys,r));detail=db.execute('select body,recipient_name,username,sender_label,followup_of,token_symbol from message_details where delivery_id=?',(d['delivery_id'],)).fetchone()
        saved=db.execute('select data from contacts where id=?',(d['id'],)).fetchone();contact=json.loads(saved[0]) if saved else {}
        d.update(dict(zip(['message','recipient_name','username','sender_label','followup_of','token_symbol'],detail)) if detail else {'message':None,'recipient_name':contact.get('name',d['target']),'username':contact.get('username',''),'sender_label':f"Account {d['account_id']}",'followup_of':None,'token_symbol':''})
        result.append(d)
    return result
LEAD_STAGES=('New','Contacted','Replied','Meeting','Proposal','Client')
def lead_key(contact):return ('group:'+str(contact.get('group_id'))) if contact.get('kind')=='group' else ('dm:'+str(contact.get('user_id')))
def lead_config(key):
    row=db.execute('select stage,reminder_days,reminders_enabled,acknowledged_at,updated_at from lead_settings where key=?',(key,)).fetchone()
    return dict(zip(('stage','reminder_days','reminders_enabled','acknowledged_at','updated_at'),row)) if row else {'stage':None,'reminder_days':3,'reminders_enabled':1,'acknowledged_at':'','updated_at':''}
def advance_lead(key,stage):
    cfg=lead_config(key);current=cfg['stage'] or 'New'
    if LEAD_STAGES.index(current)>=LEAD_STAGES.index(stage):return
    db.execute('insert into lead_settings(key,stage,updated_at) values(?,?,?) on conflict(key) do update set stage=excluded.stage,updated_at=excluded.updated_at',(key,stage,stamp()));db.commit()
def record_reply(principal,target,slot,message):
    if getattr(message,'out',False) or getattr(message,'action',None) or not getattr(message,'date',None) or not getattr(message,'id',None):return False
    first=db.execute("select min(at) from outbox where principal=? and target=? and kind='dm' and status='Sent'",(str(principal),str(target))).fetchone()[0]
    if not first:return False
    at=message.date
    if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
    if at<datetime.fromisoformat(first).replace(microsecond=0):return False
    text=(getattr(message,'raw_text',None) or getattr(message,'message',None) or '[Media message]')[:4096]
    cursor=db.execute('insert or ignore into replies values(?,?,?,?,?,?)',(str(principal),str(target),message.id,slot,at.astimezone(timezone.utc).isoformat(),text));db.commit()
    if cursor.rowcount:advance_lead('dm:'+str(target),'Replied')
    return bool(cursor.rowcount)
def attach_reply_listener(client,slot):
    if not hasattr(client,'add_event_handler'):return client
    async def incoming(event):
        if not getattr(event,'is_private',False) or not getattr(event,'sender_id',None):return
        target=str(event.sender_id)
        if not db.execute("select 1 from outbox where target=? and kind='dm' and status='Sent'",(target,)).fetchone():return
        try:
            me=await client.get_me()
            async with lock:record_reply(str(me.id),target,slot,event.message)
        except (errors.RPCError,OSError,asyncio.TimeoutError):pass
    client.add_event_handler(incoming,events.NewMessage(incoming=True))
    return client

def lead_records():
    contacts_by_key={}
    for c in contacts():contacts_by_key.setdefault(lead_key(c),c)
    grouped={}
    for d in records():
        key=d['kind']+':'+str(d['target']);grouped.setdefault(key,[]).append(d)
        contacts_by_key.setdefault(key,{'id':d['id'],'name':d['recipient_name'],'username':d['username'],'kind':d['kind'],'user_id':d['target'],'group_id':d['target'],'group':''})
    result=[];now=datetime.now(timezone.utc)
    for key,contact in contacts_by_key.items():
        rows=grouped.get(key,[]);sent=[d for d in rows if d['status']=='Sent'];pending=any(d['status'] in ('Sending','Uncertain') for d in rows)
        cfg=lead_config(key);kind,target=key.split(':',1)
        reply_rows=db.execute('select r.principal,r.slot,r.at,r.body,r.message_id from replies r where r.target=? and exists(select 1 from outbox o where o.principal=r.principal and o.target=r.target and o.kind=\'dm\' and o.status=\'Sent\') order by r.at desc,r.message_id desc limit 20',(target,)).fetchall() if kind=='dm' else []
        replies=[dict(zip(('principal','account_id','at','body','message_id'),r)) for r in reply_rows]
        replied=bool(replies);latest_reply=replies[0] if replied else None
        stage=cfg['stage'] or ('Replied' if replied else 'Contacted' if sent else 'New')
        last_sent=sent[0] if sent else None
        due_at=(datetime.fromisoformat(last_sent['at'])+timedelta(days=cfg['reminder_days'])).isoformat() if last_sent and kind=='dm' else None
        reminder_active=bool(kind=='dm' and last_sent and cfg['reminders_enabled'] and not replied and stage!='Client' and not pending)
        sync_rows=db.execute('select principal,checked_at,complete,error from reply_sync where target=?',(target,)).fetchall() if kind=='dm' else []
        principals={d['principal'] for d in sent};sync_rows=[r for r in sync_rows if r[0] in principals]
        sync_error=next((r[3] for r in sync_rows if r[3]),'')
        fully_checked=bool(principals and len(sync_rows)==len(principals) and all(r[2] and not r[3] for r in sync_rows))
        last_activity=max([contact.get('scanned_at') or '',cfg['updated_at'] or '',latest_reply['at'] if replied else '',rows[0]['at'] if rows else ''])
        result.append({'key':key,'contact_id':contact['id'],'name':contact.get('name',target),'username':contact.get('username',''),'group':contact.get('group',''),'kind':kind,'target':target,'stage':stage,'reply_status':'Replied' if replied else 'Awaiting reply' if sent and kind=='dm' else 'Not tracked' if kind=='group' else 'Not contacted','latest_reply':latest_reply,'replies':replies,'needs_attention':bool(replied and latest_reply['at']>cfg['acknowledged_at'] and stage!='Client'),'reminder_days':cfg['reminder_days'],'reminders_enabled':bool(cfg['reminders_enabled']),'reminder_active':reminder_active,'due_at':due_at if reminder_active else None,'followup_due':bool(reminder_active and datetime.fromisoformat(due_at)<=now),'reminder_reason':'Stopped — reply received' if replied else 'Complete' if stage=='Client' else 'Paused' if not cfg['reminders_enabled'] else 'Review uncertain delivery' if pending else 'Direct messages only' if kind=='group' else 'Waiting for first send' if not last_sent else 'Scheduled','last_sent_at':last_sent['at'] if last_sent else None,'followup_delivery_id':last_sent['delivery_id'] if last_sent else None,'last_activity_at':last_activity,'sync_checked_at':max([r[1] or '' for r in sync_rows],default=''),'sync_complete':fully_checked,'sync_error':sync_error})
    return sorted(result,key=lambda r:r['last_activity_at'],reverse=True)

class LeadUpdate(BaseModel):
    key:str=Field(max_length=100)
    stage:Literal['New','Contacted','Replied','Meeting','Proposal','Client']|None=None
    reminder_days:Literal[3,5,7]|None=None
    reminders_enabled:bool|None=None
    acknowledge:bool=False
class ReplySync(BaseModel):key:str|None=Field(default=None,max_length=100)
@app.post('/leads/update',dependencies=[Depends(auth)])
async def update_lead(body:LeadUpdate):
    async with lock:
        if not any(r['key']==body.key for r in lead_records()):raise HTTPException(404,'Lead not found')
        cfg=lead_config(body.key)
        if body.stage is not None:cfg['stage']=body.stage
        if body.reminder_days is not None:cfg['reminder_days']=body.reminder_days
        if body.reminders_enabled is not None:cfg['reminders_enabled']=int(body.reminders_enabled)
        if body.acknowledge:cfg['acknowledged_at']=stamp()
        cfg['updated_at']=stamp()
        db.execute('insert or replace into lead_settings values(?,?,?,?,?,?)',(body.key,cfg['stage'],cfg['reminder_days'],cfg['reminders_enabled'],cfg['acknowledged_at'],cfg['updated_at']));db.commit()
        return {'ok':True,'lead':next(r for r in lead_records() if r['key']==body.key)}

async def sync_reply_pair(principal,target,slot,first_at):
    async with lock:
        checked=stamp();row=db.execute('select cursor from reply_sync where principal=? and target=?',(principal,target)).fetchone();cursor=row[0] if row else 0
        try:
            client=None
            for candidate_slot in [slot]+[other for other in (1,2,3) if other!=slot]:
                candidate=clients.get(candidate_slot)
                if not candidate:continue
                try:
                    candidate=await ready(candidate_slot);me=await candidate.get_me()
                    if str(me.id)==principal:client=candidate;slot=candidate_slot;break
                except (HTTPException,errors.RPCError,OSError):continue
            if client is None:raise HTTPException(409,'Reconnect the original sender to check replies')
            peer=await client.get_input_entity(int(target))
            options={'limit':100,'min_id':cursor,'reverse':True}
            if not cursor:options['offset_date']=datetime.fromisoformat(first_at).replace(microsecond=0)-timedelta(seconds=1)
            messages=await asyncio.wait_for(client.get_messages(peer,**options),timeout=12)
            for message in messages:
                if message:record_reply(principal,target,slot,message)
            cursor=max([cursor]+[m.id for m in messages if m and getattr(m,'id',None)])
            complete=len(messages)<100
            next_at=(datetime.now(timezone.utc)+timedelta(seconds=300 if complete else 15)).isoformat()
            db.execute('insert or replace into reply_sync values(?,?,?,?,?,?,?)',(principal,target,cursor,checked,next_at,int(complete),''));db.commit()
            return {'target':target,'ok':True,'complete':complete}
        except (errors.RPCError,HTTPException,ValueError,OSError,asyncio.TimeoutError) as exc:
            delay=max(600,getattr(exc,'seconds',0)+5)
            detail=exc.detail if isinstance(exc,HTTPException) else 'Telegram reply check failed. Retry when this account is available.'
            if isinstance(exc,errors.FloodWaitError):detail=f'Telegram requests a {exc.seconds}s wait before checking again.'
            next_at=(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat()
            db.execute('insert or replace into reply_sync values(?,?,?,?,?,?,?)',(principal,target,cursor,checked,next_at,0,detail));db.commit()
            return {'target':target,'ok':False,'error':detail}
async def sync_replies(key=None,limit=1):
    pairs=db.execute("select principal,target,slot,min(at) from outbox where kind='dm' and status='Sent' group by principal,target").fetchall()
    candidates=[];now=stamp()
    for principal,target,slot,first in pairs:
        if key and key!='dm:'+target:continue
        state=db.execute('select checked_at,next_check_at,error from reply_sync where principal=? and target=?',(principal,target)).fetchone()
        # Preserve Telegram/error backoff; an explicit check can refresh a successful check after 30 seconds.
        if state and state[1]>now and (not key or state[2] or (datetime.now(timezone.utc)-datetime.fromisoformat(state[0])).total_seconds()<30):continue
        candidates.append((state[0] if state else '',principal,target,slot,first))
    candidates.sort(key=lambda r:r[0]);results=[]
    for _,principal,target,slot,first in candidates[:limit]:results.append(await sync_reply_pair(principal,target,slot,first))
    return {'checked':len(results),'remaining':max(0,len(candidates)-len(results)),'results':results}
@app.post('/replies/sync',dependencies=[Depends(auth)])
async def check_replies(body:ReplySync):
    if body.key and (not body.key.startswith('dm:') or not any(r['key']==body.key for r in lead_records())):raise HTTPException(400,'Choose a direct-message lead')
    return await sync_replies(body.key,limit=3)
async def reply_sync_loop():
    while True:
        await asyncio.sleep(15)
        try:await sync_replies(limit=1)
        except asyncio.CancelledError:raise
        except Exception:pass  # One unavailable session must not stop checking other senders.

@app.on_event('startup')
async def start():
    global reply_task
    for slot in (1,2,3):
        try:
            c=make_client(slot)
            if c:clients[slot]=c;await c.connect()
        except Exception:startup_errors[slot]='Telegram connection unavailable. Reconnect this account in Connections.'
    reply_task=asyncio.create_task(reply_sync_loop())
@app.on_event('shutdown')
async def stop():
    if reply_task:
        reply_task.cancel()
        try:await reply_task
        except asyncio.CancelledError:pass
    for c in clients.values():await c.disconnect()
@app.exception_handler(errors.FloodWaitError)
async def flood(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=429,content={'detail':f'Telegram requires a {exc.seconds} second wait. Sending stopped; no automatic retry or sender switch.'})
@app.exception_handler(errors.RPCError)
async def rpc_error(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400,content={'detail':str(exc)})
class Account(BaseModel):account_id:int=Field(default=1,ge=1,le=3)
class Login(Account):phone:str
class Verify(Account):phone:str;code:str='';password:str=''
class Scan(Account):link:str;join:bool=False;leave_after_scan:bool=False
class Config(BaseModel):template:str='';sheet_url:str='';sender_account:int=Field(default=1,ge=1,le=3);token_symbol:str=Field(default='',max_length=33)
class Templates(BaseModel):
    template:str=Field(min_length=1,max_length=4096)
    followup_template:str=Field(min_length=1,max_length=4096)
class Send(Account):id:str;kind:Literal['dm','group']='dm';message:str|None=None;token_symbol:str|None=Field(default=None,max_length=33)
class SheetSend(BaseModel):id:str
class Followup(BaseModel):
    token_symbol:str|None=Field(default=None,max_length=33)
    delivery_id:str
    message:str=Field(min_length=1,max_length=4096)
    request_id:str=Field(min_length=8,max_length=128)
class ResetQuota(Account):
    scope:Literal['dm','group','both']='both'
    request_id:str=Field(min_length=8,max_length=128)
class TelegramAPI(Account):api_id:int=Field(gt=0);api_hash:SecretStr
@app.get('/health')
async def health():return {'service':'teamradar','ok':True,'version':'3.2'}
@app.post('/telegram-api',dependencies=[Depends(auth)])
async def configure_telegram_api(body:TelegramAPI):
    slot=body.account_id;value=body.api_hash.get_secret_value().strip()
    if not re.fullmatch(r'[a-fA-F0-9]{32}',value):raise HTTPException(400,'API Hash must contain 32 hexadecimal characters from my.telegram.org')
    async with lock:
        old=clients.get(slot)
        if old and old.is_connected() and await old.is_user_authorized():raise HTTPException(409,'Disconnect this Telegram account before replacing its API credentials')
        if old:await old.disconnect()
        candidate=TelegramClient(session_path(slot),body.api_id,value,flood_sleep_threshold=0)
        try:await candidate.connect()
        except Exception:
            await candidate.disconnect()
            raise HTTPException(502,'Could not reach Telegram. API settings were not saved; try again later.')
        db.execute('insert or replace into telegram_api values(?,?,?)',(slot,body.api_id,value));db.commit()
        clients[slot]=attach_reply_listener(candidate,slot);startup_errors.pop(slot,None)
    return {'api_configured':True,'account_id':slot}
@app.get('/status',dependencies=[Depends(auth)])
async def status():
    accounts=[]
    for slot in (1,2,3):
        c=clients.get(slot);authorized=False
        try:authorized=bool(c and c.is_connected() and await c.is_user_authorized())
        except Exception:pass
        row=db.execute('select principal,label,phone,blocked_until from account_info where slot=?',(slot,)).fetchone()
        principal,label,phone,blocked=row if row else (f'slot:{slot}',f'Account {slot}','','')
        if authorized and not row:
            try:principal=await identify(slot,c)
            except HTTPException:authorized=False
            row=db.execute('select principal,label,phone,blocked_until from account_info where slot=?',(slot,)).fetchone()
            if row:principal,label,phone,blocked=row
        u=usage(principal)
        sent=sent_in_current_quota(principal)
        accounts.append({'id':slot,'label':label,'phone':phone,'api_configured':c is not None,'authorized':authorized,'usage':u,'daily_goal':DAILY_GOAL,'sent_today':sent,'blocked_until':blocked,'error':startup_errors.get(slot,''),'health':account_health(principal,c,authorized,blocked,startup_errors.get(slot,''))})
    return {'version':'3.2','api_configured':accounts[0]['api_configured'],'authorized':any(a['authorized'] for a in accounts),'accounts':accounts,'quota_date':today(),'quota_timezone':'Asia/Kolkata','contacts':contacts(),'settings':settings(),'deliveries':records(),'quota_resets':reset_records(),'leads':lead_records(),'features':{'token_personalization':True,'new_recipient_dm_quota':True,'message_templates':True,'lead_management':True}}
@app.post('/reset-daily-limits',dependencies=[Depends(auth)])
async def reset_daily_limits(body:ResetQuota):
    async with lock:
        client=await ready(body.account_id)
        principal=await identify(body.account_id,client)
        kinds=list(LIMITS) if body.scope=='both' else [body.scope]
        previous=db.execute('select principal,kind,day from quota_resets where request_id=?',(body.request_id,)).fetchall()
        if previous:
            if any(r[0]!=principal or r[2]!=today() for r in previous) or {r[1] for r in previous}!=set(kinds):
                raise HTTPException(409,'This reset request was already used for another account, day or scope. Start a new reset.')
            return {'ok':True,'account_id':body.account_id,'scope':body.scope,'already_applied':True,'usage':usage(principal)}
        date=today();before=usage(principal)
        # Advance only the quota baseline. Delivery/duplicate records and Telegram pauses are untouched.
        floor=db.execute('select coalesce(max(rowid),0) from outbox').fetchone()[0]
        with db:
            for kind in kinds:
                db.execute('insert into quota_resets values(?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,principal,body.account_id,kind,date,floor,stamp(),before[kind]['used'],body.request_id))
        return {'ok':True,'account_id':body.account_id,'scope':body.scope,'already_applied':False,'usage':usage(principal)}

@app.post('/login',dependencies=[Depends(auth)])
async def login(body:Login):
    async with lock:
        c=require_client(body.account_id)
        if not c.is_connected():await c.connect()
        r=await c.send_code_request(body.phone);phone_hash[(body.account_id,body.phone)]=r.phone_code_hash
    return {'ok':True,'account_id':body.account_id}
@app.post('/verify',dependencies=[Depends(auth)])
async def verify(body:Verify):
    async with lock:
        c=require_client(body.account_id)
        if not c.is_connected():await c.connect()
        try:
            if body.password:await c.sign_in(password=body.password)
            else:await c.sign_in(body.phone,body.code,phone_code_hash=phone_hash.get((body.account_id,body.phone)))
        except errors.SessionPasswordNeededError:return {'password_required':True}
        try:await identify(body.account_id,c)
        except HTTPException:
            await c.log_out();raise
    return {'authorized':True,'account_id':body.account_id}
@app.post('/logout',dependencies=[Depends(auth)])
async def logout(body:Account):
    async with lock:
        c=require_client(body.account_id);await c.log_out()
        clients.pop(body.account_id,None)
        replacement=make_client(body.account_id)
        if replacement:clients[body.account_id]=replacement;await replacement.connect()
    return {'ok':True}
@app.post('/scan',dependencies=[Depends(auth)])
async def scan(body:Scan):
    client=await ready(body.account_id)
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
                if getattr(u,'bot',False) or getattr(u,'deleted',False):continue
                rank=getattr(p,'rank',None) or ''
                owner=isinstance(p,(types.ChannelParticipantCreator,types.ChatParticipantCreator))
                c={'id':str(entity.id)+':'+str(u.id),'user_id':str(u.id),'name':(' '.join(filter(None,[u.first_name,u.last_name])) or 'Unnamed admin'),'username':u.username or '', 'group':entity.title,'link':body.link,'role':'Owner' if owner else (rank or 'Admin'),'title':rank,'source':'Telegram admin title' if rank else 'Telegram permissions','scanned_at':stamp(),'status':'Ready','is_bot':False,'scan_account':body.account_id,'group_id':str(utils.get_peer_id(entity))}
                save(c);result.append(c)
            group={'id':'group:'+str(utils.get_peer_id(entity)),'name':entity.title,'username':getattr(entity,'username','') or '', 'role':'Group chat','group':entity.title,'link':body.link,'group_id':str(utils.get_peer_id(entity)),'kind':'group','scan_account':body.account_id,'source':'Telegram group','scanned_at':stamp(),'status':'Ready'}
            stored=db.execute('select data from contacts where id=?',(group['id'],)).fetchone()
            group['membership']=json.loads(stored[0]).get('membership',{}) if stored else {}
            if body.join:group['membership'][str(body.account_id)]='member'
            is_group=getattr(entity,'megagroup',False) or isinstance(entity,types.Chat)
            if is_group:save(group)
            leave={'requested':body.leave_after_scan,'status':'not_requested','error':''}
            # All collected contacts and the group record have committed before any leave request.
            if body.leave_after_scan:
                if not result:
                    leave['status']='skipped'
                    leave['error']='No visible admin records collected; account remains in the group.'
                else:
                    try:
                        if isinstance(entity,types.Channel):
                            await client(functions.channels.LeaveChannelRequest(entity))
                        elif isinstance(entity,types.Chat):
                            await client(functions.messages.DeleteChatUserRequest(entity.id,types.InputUserSelf()))
                        else:raise ValueError('Unsupported chat type')
                        leave['status']='left'
                    except errors.UserNotParticipantError:
                        leave['status']='already_left'
                    except errors.RPCError as exc:
                        leave['status']='failed';leave['error']=str(exc)
                    except Exception:
                        leave['status']='uncertain';leave['error']='Could not confirm leaving. Check Telegram membership before retrying.'
                    if leave['status'] in ('left','already_left'):
                        group['membership'][str(body.account_id)]='left'
                    elif leave['status']=='uncertain':
                        group['membership'][str(body.account_id)]='unknown'
                    group['last_leave']={**leave,'account_id':body.account_id,'at':stamp()}
                    if is_group:save(group)
            return {'contacts':result,'group':entity.title,'count':len(result),'leave':leave,'account_id':body.account_id}
        except errors.InviteRequestSentError:raise HTTPException(409,'Join request sent. Scan after an administrator approves it.')
        except errors.ChatAdminRequiredError:raise HTTPException(403,'Telegram hides this admin list from your account. Try its linked discussion group or ask for access.')
        except HTTPException:raise
        except errors.RPCError as exc:raise HTTPException(400,str(exc))
@app.post('/settings',dependencies=[Depends(auth)])
async def config(body:Config):
    body.token_symbol=normalize_token(body.token_symbol)
    if body.sheet_url and 'docs.google.com/spreadsheets/d/' not in body.sheet_url:raise HTTPException(400,'Paste a Google Sheets URL, not a Google Doc')
    merged={**settings(),**body.model_dump()}
    db.execute('insert or replace into settings values(1,?)',(json.dumps(merged),));db.commit();return {'ok':True}
@app.post('/templates',dependencies=[Depends(auth)])
async def save_templates(body:Templates):
    values={k:v.strip() for k,v in body.model_dump().items()}
    if not all(values.values()):raise HTTPException(400,'Both message templates must contain text')
    merged={**settings(),**values}
    db.execute('insert or replace into settings values(1,?)',(json.dumps(merged),));db.commit()
    return {'ok':True,**values}
def normalize_token(value):
    symbol=(value or '').strip().lstrip('$')
    if symbol and not re.fullmatch(r'[A-Za-z0-9._-]{1,32}',symbol):raise HTTPException(400,'Use a token symbol of up to 32 letters, numbers, dots, underscores or hyphens')
    return symbol

def personalize_message(text,contact,token_symbol=''):
    symbol=normalize_token(token_symbol)
    if (re.search(r'\$TOKEN\b',text) or '{{token}}' in text) and not symbol:raise HTTPException(400,'Enter the token name above the message preview before sending')
    handle='@'+contact['username'].lstrip('@') if contact.get('username') else (contact.get('name') or 'there')
    text=text.replace('@{{username}}',handle).replace('{{username}}',handle).replace('@username',handle)
    text=text.replace('{{name}}',contact.get('name','')).replace('{{role}}',contact.get('role','')).replace('{{group}}',contact.get('group',''))
    text=text.replace('{{token}}','$'+symbol if symbol else '')
    return re.sub(r'\$TOKEN\b',lambda match:'$'+symbol,text)

async def deliver(cid,slot=1,kind='dm',message=None,followup_of=None,request_id=None,expected_principal=None,token_symbol=None):
    async with lock:
        c=await ready(slot);principal=await identify(slot,c)
        row=db.execute('select data from contacts where id=?',(cid,)).fetchone()
        if not row:raise HTTPException(404,'Contact not found')
        contact=json.loads(row[0])
        if contact.get('is_bot'):raise HTTPException(400,'Bot admins are excluded from messaging')
        if expected_principal and expected_principal!=principal:raise HTTPException(409,'The original sender is not logged into this account slot. Reconnect the original Telegram account to send this follow-up.')
        if (kind=='group') != (contact.get('kind')=='group'):raise HTTPException(400,'Choose a group chat for group messages or a team member for DMs')
        if kind=='group' and contact.get('membership',{}).get(str(slot))=='left':raise HTTPException(409,f'Account {slot} left this group. Rejoin and rescan with Leave group after scan switched off before sending group messages.')
        text=(message if message is not None else settings()['template']).strip()
        if not text:raise HTTPException(400,'Write your message before sending')
        symbol=normalize_token(settings().get('token_symbol','') if token_symbol is None else token_symbol)
        text=personalize_message(text,contact,symbol)
        digest=hashlib.sha256(text.encode()).hexdigest()
        target=str(contact['group_id'] if kind=='group' else contact['user_id'])
        date=today()
        if followup_of:
            previous=db.execute('select delivery_id,parent_id,message_hash from followup_requests where request_id=?',(request_id,)).fetchone()
            if previous:
                if previous[1]!=followup_of or previous[2]!=digest:raise HTTPException(409,'Request ID was already used for a different follow-up')
                d=db.execute('select status,slot from outbox where id=?',(previous[0],)).fetchone()
                if d and d[0]=='Sent':return {'status':'Sent','id':cid,'account_id':d[1],'kind':kind,'usage':usage(principal),'already_sent':True}
                raise HTTPException(409,'This follow-up was already processed. Review its delivery status before sending again.')
            uncertain=db.execute("select 1 from outbox where kind=? and target=? and status in ('Sending','Uncertain')",(kind,target)).fetchone()
            if uncertain:raise HTTPException(409,'An earlier message to this recipient is still uncertain. Check Telegram before following up.')
            prior=db.execute("select 1 from outbox where kind=? and target=? and message_hash=? and status='Sent'",(kind,target,digest)).fetchone()
        else:
            prior=db.execute("select 1 from outbox where kind=? and target=? and status in ('Sent','Sending','Uncertain')"+(" and day=? and message_hash=?" if kind=='group' else ''),([kind,target,date,digest] if kind=='group' else [kind,target])).fetchone()
        if prior:raise HTTPException(409,'Already sent or awaiting review. Duplicate blocked across sender accounts.')
        info=db.execute('select blocked_until from account_info where slot=?',(slot,)).fetchone()
        if info and info[0] and info[0]>stamp():raise HTTPException(429,'This account is paused by Telegram until '+info[0])
        u=usage(principal)[kind]
        if u['remaining']<=0 and (kind!='dm' or dm_needs_new_slot(principal,target,date)):raise HTTPException(429,f"Account {slot} reached today's {LIMITS[kind]} {'new DM recipient' if kind=='dm' else 'group message'} limit. Resets at midnight Asia/Kolkata.")
        # Resolve the destination using this sender's own Telegram permissions before reserving a send.
        try:
            if kind=='group':peer=await c.get_entity(int(target))
            elif contact.get('username'):
                peer=await c.get_entity(contact['username'])
                if str(peer.id)!=target:raise HTTPException(409,'Username now belongs to another user. Rescan this contact before sending.')
            else:peer=await c.get_input_entity(int(target))
        except (ValueError,TypeError):raise HTTPException(409,'This sender cannot resolve the recipient. Scan its group with this account first.')
        if kind=='dm' and getattr(peer,'bot',False):raise HTTPException(400,'This contact is a Telegram bot. Bot admins are excluded.')
        if kind=='group' and not (isinstance(peer,types.Chat) or getattr(peer,'megagroup',False)):raise HTTPException(400,'The selected destination is not a group chat')
        delivery_id=uuid.uuid4().hex
        # Record all attempts. DM quota counts unique new recipients; group quota counts attempts.
        sender_label=db.execute('select label from account_info where slot=?',(slot,)).fetchone()[0]
        with db:
            db.execute('insert into outbox values(?,?,?,?,?,?,?,?,?,?,?)',(delivery_id,principal,slot,kind,target,cid,'Sending',date,stamp(),'',digest))
            db.execute('insert into message_details(delivery_id,body,recipient_name,username,sender_label,followup_of,token_symbol) values(?,?,?,?,?,?,?)',(delivery_id,text,contact['name'],contact.get('username',''),sender_label,followup_of,symbol))
            if followup_of:db.execute('insert into followup_requests values(?,?,?,?)',(request_id,delivery_id,followup_of,digest))
        try:await c.send_message(peer,text)
        except errors.FloodWaitError as exc:
            blocked=(datetime.now(timezone.utc)+timedelta(seconds=exc.seconds)).isoformat()
            db.execute('update account_info set blocked_until=? where principal=?',(blocked,principal))
            db.execute('update outbox set status=?,error=? where id=?',('Failed',f'Telegram wait: {exc.seconds}s',delivery_id));db.commit();raise
        except errors.RPCError as exc:
            if isinstance(exc,errors.PeerFloodError):
                db.execute('update account_info set blocked_until=? where principal=?',((datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),principal))
            db.execute('update outbox set status=?,error=? where id=?',('Failed',str(exc),delivery_id));db.commit();raise
        except Exception:
            db.execute('update outbox set status=?,error=? where id=?',('Uncertain','Check Telegram before retrying',delivery_id));db.commit();raise HTTPException(502,'Delivery uncertain. Check Telegram before retrying.')
        db.execute('update outbox set status=?,at=? where id=?',('Sent',stamp(),delivery_id));db.commit()
        advance_lead(kind+':'+target,'Contacted')
        return {'status':'Sent','id':cid,'account_id':slot,'kind':kind,'usage':usage(principal)}
@app.post('/send',dependencies=[Depends(auth)])
async def send(body:Send):return await deliver(body.id,body.account_id,body.kind,body.message,token_symbol=body.token_symbol)
@app.post('/follow-up',dependencies=[Depends(auth)])
async def follow_up(body:Followup):
    parent=db.execute('select principal,slot,kind,contact_id,status from outbox where id=?',(body.delivery_id,)).fetchone()
    if not parent:raise HTTPException(404,'Original message not found')
    principal,slot,kind,cid,status=parent
    if status!='Sent':raise HTTPException(409,'Follow-ups require a confirmed sent message')
    saved_token=db.execute('select token_symbol from message_details where delivery_id=?',(body.delivery_id,)).fetchone()
    symbol=body.token_symbol if body.token_symbol is not None else (saved_token[0] if saved_token else '')
    return await deliver(cid,slot,kind,body.message,followup_of=body.delivery_id,request_id=body.request_id,expected_principal=principal,token_symbol=symbol)

@app.post('/sheet-send',dependencies=[Depends(auth)])
async def sheet_send(body:SheetSend):
    cfg=settings();return await deliver(body.id,cfg['sender_account'],'dm')
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
        if c.get('kind')=='group':continue
        d=db.execute('select status from outbox where contact_id=? order by at desc limit 1',(c['id'],)).fetchone()
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
