import os,json,sqlite3,asyncio,secrets,re,hashlib,uuid,copy,math
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Depends,Header,HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,SecretStr,Field
from telethon import TelegramClient,functions,types,errors,utils,events
from telethon.extensions import BinaryReader

ROOT=Path(os.getenv('DATA_DIR','./data'));ROOT.mkdir(parents=True,exist_ok=True);os.chmod(ROOT,0o700)
KEY=os.environ['DASHBOARD_KEY']
API_ID=os.getenv('TELEGRAM_API_ID');API_HASH=os.getenv('TELEGRAM_API_HASH')
TZ=ZoneInfo('Asia/Kolkata');LIMITS={'dm':15,'group':30};DAILY_GOAL=10
app=FastAPI(title='WMM Team',version='3.7')
app.add_middleware(CORSMiddleware,allow_origins=[os.getenv('SITE_ORIGIN','https://teamradar-telegram-desk.jenilvaghamshi04.chatgpt.site')],allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
lock=asyncio.Lock();login_pending={};clients={};startup_errors={};reply_task=None;folder_task=None;auto_yes_task=None;auto_yes_lock=asyncio.Lock();auto_followup_task=None;auto_followup_lock=asyncio.Lock()
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
db.execute('create table if not exists send_pacing(principal text primary key,last_attempt_at text)')
db.execute('create table if not exists import_batches(id text primary key,data text,expires_at text)')
db.execute('create table if not exists meta(key text primary key, value text)')
db.execute('create table if not exists workspace_reset_requests(request_id text primary key,result text)')
if 'telegram_message_id' not in {r[1] for r in db.execute('pragma table_info(message_details)')}:db.execute("alter table message_details add column telegram_message_id integer not null default 0")
db.execute("create table if not exists folder_routes(principal text, target text, slot integer, desired text, applied text not null default '', revision integer not null default 1, applied_revision integer not null default 0, queued_at text, checked_at text not null default '', error text not null default '', next_attempt_at text not null default '', primary key(principal,target))")
db.execute('create table if not exists folder_pauses(principal text primary key, until_at text, error text)')
db.execute('create table if not exists empty_folder_templates(principal text, title text, folder_id integer, body blob, primary key(principal,title))')
db.execute("create table if not exists lead_settings(key text primary key, stage text, reminder_days integer not null default 3, reminders_enabled integer not null default 1, acknowledged_at text not null default '', updated_at text not null default '')")
db.execute('create table if not exists replies(principal text, target text, message_id integer, slot integer, at text, body text, primary key(principal,target,message_id))')
for column,definition in [('exchange',"text not null default ''"),('automation_step','integer not null default 0')]:
    if column not in {r[1] for r in db.execute('pragma table_info(message_details)')}:db.execute(f'alter table message_details add column {column} {definition}')
db.execute('create table if not exists auto_yes_enrollments(principal text,target text,root_id text,contact_id text,slot integer,exchange text,token_symbol text,pitch text,demo text,enabled integer,armed_at text,primary key(principal,target))')
db.execute("create table if not exists auto_yes_jobs(id text primary key,principal text,target text,reply_id integer,root_id text,pitch text,demo text,step integer not null default 0,status text not null default 'Pending',error text not null default '',next_attempt_at text not null default '',created_at text,unique(principal,target))")
for table,column,declaration in [('auto_yes_enrollments','no_reply',"TEXT NOT NULL DEFAULT ''"),('auto_yes_jobs','branch',"TEXT NOT NULL DEFAULT 'yes'")]:
    if column not in [r[1] for r in db.execute('pragma table_info('+table+')')]:db.execute('alter table '+table+' add column '+column+' '+declaration)
db.execute("update auto_yes_jobs set status='Pending' where status='Sending'")
# Completed conversations cannot be re-armed after upgrading or restarting.
db.execute("update auto_yes_enrollments set enabled=0 where exists(select 1 from auto_yes_jobs j where j.principal=auto_yes_enrollments.principal and j.target=auto_yes_enrollments.target and j.status='Complete')")
db.execute("create table if not exists auto_followup_jobs(root_id text primary key,principal text,target text unique,slot integer,contact_id text,due_at text,token_symbol text,exchange text,body text not null default '',status text not null default 'Scheduled',error text not null default '',next_attempt_at text not null default '')")
db.execute("update auto_followup_jobs set status='Pending' where status='Sending'")
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
EXCHANGES={'bingx':'BingX','bitget':'Bitget','bitunix':'Bitunix','blofin':'BloFin','gateio':'Gate.io','htx':'HTX','lbank':'LBank','lovelylegends':'Lovely Legends','mexc':'MEXC','okx':'OKX','poloniex':'Poloniex','toobit':'Toobit','weex':'WEEX','xt':'XT.com'}
DEFAULT_YES_PITCH="Nice to meet you @username,\nThis is mark from WMM\n\nI saw the @TOKEN chart on {{exchange}}, candlesticks look broken, we provide a professional trading team for market making, {{exchange}} trading fees are quite high but we make it good in the same daily fee spending budget\n\nWe make the chart most compatible with trading views and other trading signals tools to activate more real traders."
DEFAULT_YES_DEMO="We can give you a free demo also\nIf you have time we can jump on call and discuss further"
DEFAULT_NO_REPLY="We can also offer a free demo so you can see how we work before making a decision. Would you be open to a quick call to discuss what could work for your project?"
def settings():
    r=db.execute('select data from settings where id=1').fetchone()
    return {'template':'','followup_template':DEFAULT_FOLLOWUP,'sheet_url':'','sender_account':1,'token_symbol':'','yes_pitch_template':DEFAULT_YES_PITCH,'yes_demo_template':DEFAULT_YES_DEMO,'no_reply_template':DEFAULT_NO_REPLY,'auto_yes_enabled':True,'auto_followup_enabled':True,'send_delay_seconds':120,**(json.loads(r[0]) if r else {})}
def pacing_status(principal):
    row=db.execute('select last_attempt_at from send_pacing where principal=?',(principal,)).fetchone()
    # Cover deliveries made before the pacing migration too.
    prior=db.execute('select max(at) from outbox where principal=?',(principal,)).fetchone()[0]
    last=max(filter(None,[row[0] if row else None,prior]),default=None)
    delay=max(120,int(settings().get('send_delay_seconds',120)))
    next_at=(datetime.fromisoformat(last)+timedelta(seconds=delay)) if last else None
    remaining=max(0,math.ceil((next_at-datetime.now(timezone.utc)).total_seconds())) if next_at else 0
    return {'delay_seconds':delay,'retry_after':remaining,'next_available_at':next_at.isoformat() if remaining else None}
def pause_for_telegram(principal,exc):
    seconds=exc.seconds if isinstance(exc,errors.FloodWaitError) else 86400
    blocked=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()
    db.execute("update account_info set blocked_until=max(coalesce(blocked_until,''),?) where principal=?",(blocked,str(principal)));db.commit()
def enforce_send_pacing(principal,slot=None):
    pace=pacing_status(principal)
    if pace['retry_after']:
        raise HTTPException(429,{'code':'send_cooldown','account_id':slot,'message':f"Account is cooling down. Next message in {pace['retry_after']} seconds.",**pace},headers={'Retry-After':str(pace['retry_after'])})
class SendingPace(BaseModel):
    delay_seconds:Literal[120,300,600]=120
@app.post('/sending-pace',dependencies=[Depends(auth)])
async def update_sending_pace(body:SendingPace):
    async with lock:
        cfg={**settings(),'send_delay_seconds':body.delay_seconds}
        db.execute('insert or replace into settings values(1,?)',(json.dumps(cfg),));db.commit()
    return {'ok':True,'delay_seconds':body.delay_seconds}

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
        d=dict(zip(keys,r));detail=db.execute('select body,recipient_name,username,sender_label,followup_of,token_symbol,exchange,automation_step from message_details where delivery_id=?',(d['delivery_id'],)).fetchone()
        saved=db.execute('select data from contacts where id=?',(d['id'],)).fetchone();contact=json.loads(saved[0]) if saved else {}
        d.update(dict(zip(['message','recipient_name','username','sender_label','followup_of','token_symbol','exchange','automation_step'],detail)) if detail else {'message':None,'recipient_name':contact.get('name',d['target']),'username':contact.get('username',''),'sender_label':f"Account {d['account_id']}",'followup_of':None,'token_symbol':'','exchange':'','automation_step':0})
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
    if cursor.rowcount:
        advance_lead('dm:'+str(target),'Replied')
        last=db.execute("select o.at,coalesce(d.telegram_message_id,0) from outbox o left join message_details d on d.delivery_id=o.id where o.principal=? and o.target=? and o.kind='dm' and o.status='Sent' order by o.at desc limit 1",(str(principal),str(target))).fetchone()
        if is_affirmative_reply(text) or (last and (message.id>last[1] if last[1] else at>=datetime.fromisoformat(last[0]).replace(microsecond=0))):
            queue_folder_route(str(principal),str(target),slot,'🟡',force=True)
        queue_auto_yes(str(principal),str(target),slot,message)
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
        result.append({'key':key,'contact_id':contact['id'],'name':contact.get('name',target),'username':contact.get('username',''),'group':contact.get('group',''),'kind':kind,'target':target,'stage':stage,'reply_status':'Replied' if replied else 'Awaiting reply' if sent and kind=='dm' else 'Not tracked' if kind=='group' else 'Not contacted','latest_reply':latest_reply,'replies':replies,'needs_attention':bool(replied and latest_reply['at']>cfg['acknowledged_at'] and stage!='Client'),'reminder_days':cfg['reminder_days'],'reminders_enabled':bool(cfg['reminders_enabled']),'reminder_active':reminder_active,'due_at':due_at if reminder_active else None,'followup_due':bool(reminder_active and datetime.fromisoformat(due_at)<=now),'reminder_reason':'Stopped — reply received' if replied else 'Complete' if stage=='Client' else 'Paused' if not cfg['reminders_enabled'] else 'Review uncertain delivery' if pending else 'Direct messages only' if kind=='group' else 'Waiting for first send' if not last_sent else 'Scheduled','last_sent_at':last_sent['at'] if last_sent else None,'followup_delivery_id':last_sent['delivery_id'] if last_sent else None,'last_activity_at':last_activity,'sync_checked_at':max([r[1] or '' for r in sync_rows],default=''),'sync_complete':fully_checked,'sync_error':sync_error,'folder_routes':folder_route_records(target,principals) if kind=='dm' else [],'auto_followup':auto_followup_summary(target) if kind=='dm' else None,'auto_yes':auto_yes_summary(target,principals) if kind=='dm' else None})
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
        if not db.execute("select 1 from outbox where principal=? and target=? and kind='dm' and status='Sent'",(principal,target)).fetchone():return {'target':target,'ok':True,'complete':True,'skipped':True}
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

# Telegram emoji folders are separate from delivery status and lead stages.
def has_positive_reply(principal,target):
    return any(is_affirmative_reply(row[0]) for row in db.execute('select body from replies where principal=? and target=?',(str(principal),str(target))))
def queue_folder_route(principal,target,slot,desired,force=False):
    # A qualified yes keeps this conversation yellow, including after our own replies.
    if desired=='🔵' and has_positive_reply(principal,target):desired='🟡'
    row=db.execute('select desired from folder_routes where principal=? and target=?',(str(principal),str(target))).fetchone()
    if row and row[0]==desired and not force:return
    db.execute("insert into folder_routes(principal,target,slot,desired,queued_at) values(?,?,?,?,?) on conflict(principal,target) do update set slot=excluded.slot,desired=excluded.desired,revision=folder_routes.revision+1,queued_at=excluded.queued_at,error='',next_attempt_at=''",(str(principal),str(target),slot,desired,stamp()));db.commit()
def seed_folder_routes():
    # Catch up confirmed DMs and repair positive conversations moved blue by older versions.
    for principal,target,slot,last_at in db.execute("select principal,target,slot,max(at) from outbox where kind='dm' and status='Sent' group by principal,target").fetchall():
        if has_positive_reply(principal,target):
            queue_folder_route(principal,target,slot,'🟡');continue
        if db.execute('select 1 from folder_routes where principal=? and target=?',(principal,target)).fetchone():continue
        replied=db.execute('select 1 from replies where principal=? and target=? and at>=? limit 1',(principal,target,datetime.fromisoformat(last_at).replace(microsecond=0).isoformat())).fetchone()
        queue_folder_route(principal,target,slot,'🟡' if replied else '🔵')
def folder_route_records(target,principals):
    rows=db.execute('select principal,slot,desired,applied,revision,applied_revision,checked_at,error from folder_routes where target=? order by queued_at desc',(target,)).fetchall()
    return [{'account_id':slot,'desired':desired,'applied':applied,'status':'Needs attention' if error else 'Synced' if revision==applied_revision else 'Pending','checked_at':checked,'error':error} for principal,slot,desired,applied,revision,applied_revision,checked,error in rows if principal in principals]
def folder_title(folder):
    title=getattr(folder,'title','');return str(getattr(title,'text',title)).strip().replace('\ufe0f','')
def matching_folder(filters,title):
    matches=[f for f in filters if folder_title(f)==title]
    if len(matches)>1:raise HTTPException(409,f'Multiple {title} folders exist. Give the intended folder a unique name before retrying.')
    if matches and not isinstance(matches[0],types.DialogFilter):raise HTTPException(409,f'{title} must be a personal Telegram folder, not a shared folder.')
    return matches[0] if matches else None
def same_folder_peer(peer,target,principal):
    return str(getattr(peer,'user_id',''))==str(target) or (isinstance(peer,types.InputPeerSelf) and str(target)==str(principal))
async def fetch_folders(client):
    result=await client(functions.messages.GetDialogFiltersRequest())
    return list(getattr(result,'filters',result if isinstance(result,(list,tuple)) else []))
async def save_folder(client,folder):
    if not await client(functions.messages.UpdateDialogFilterRequest(id=folder.id,filter=folder)):raise HTTPException(502,'Telegram did not confirm the folder update. Retry folder sync.')
async def move_chat_folder(client,principal,target,desired):
    peer=await client.get_input_entity(int(target));filters=await fetch_folders(client)
    destination=matching_folder(filters,desired)
    if destination is None:
        used={getattr(f,'id',0) for f in filters}
        folder_id=next((i for i in range(2,256) if i not in used),None)
        if folder_id is None:raise HTTPException(409,'No free Telegram folder ID is available.')
        template=db.execute('select folder_id,body from empty_folder_templates where principal=? and title=?',(principal,desired)).fetchone()
        if template:
            with BinaryReader(template[1]) as reader:destination=reader.tgread_object()
            if not isinstance(destination,types.DialogFilter) or folder_title(destination)!=desired:raise HTTPException(409,'The saved empty-folder settings need to be recreated in Telegram.')
            destination.id=template[0] if template[0] not in used else folder_id
            destination.include_peers=[peer]
            destination.exclude_peers=[p for p in destination.exclude_peers if not same_folder_peer(p,target,principal)]
        else:
            title=types.TextWithEntities(text=desired,entities=[])
            destination=types.DialogFilter(id=folder_id,title=title,pinned_peers=[],include_peers=[peer],exclude_peers=[])
        await save_folder(client,destination)
    else:
        destination=copy.deepcopy(destination);before=destination.to_dict()
        destination.exclude_peers=[p for p in destination.exclude_peers if not same_folder_peer(p,target,principal)]
        if not any(same_folder_peer(p,target,principal) for p in destination.include_peers+destination.pinned_peers):destination.include_peers.append(peer)
        if destination.to_dict()!=before:await save_folder(client,destination)
    # Fetch again so that edits made in Telegram while adding the destination are retained.
    opposite='🟡' if desired=='🔵' else '🔵'
    source=matching_folder(await fetch_folders(client),opposite)
    if source is None:return
    source=copy.deepcopy(source);before=source.to_dict()
    source.include_peers=[p for p in source.include_peers if not same_folder_peer(p,target,principal)]
    source.pinned_peers=[p for p in source.pinned_peers if not same_folder_peer(p,target,principal)]
    if any(getattr(source,name,False) for name in ('contacts','non_contacts','groups','broadcasts','bots')) and not any(same_folder_peer(p,target,principal) for p in source.exclude_peers):source.exclude_peers.append(peer)
    if source.to_dict()!=before:
        try:await save_folder(client,source)
        except errors.FilterIncludeEmptyError:
            if source.include_peers or source.pinned_peers or any(getattr(source,name,False) for name in ('contacts','non_contacts','groups','broadcasts','bots')):raise
            # Telegram cannot keep an explicit-only folder with no chats. Retain its exact settings
            # before removing just the now-empty routing folder; chats are never deleted.
            db.execute('insert or replace into empty_folder_templates values(?,?,?,?)',(principal,opposite,source.id,sqlite3.Binary(bytes(source))));db.commit()
            if not await client(functions.messages.UpdateDialogFilterRequest(id=source.id)):raise HTTPException(502,'Telegram did not confirm the empty-folder update.')
async def folder_client(principal,preferred):
    for slot in [preferred]+[other for other in (1,2,3) if other!=preferred]:
        if slot not in clients:continue
        try:
            client=await ready(slot);me=await client.get_me()
            if str(me.id)==principal:return client,slot
        except (HTTPException,errors.RPCError,OSError):continue
    raise HTTPException(409,'Reconnect the original Telegram sender to sync this chat folder.')
async def sync_folder_routes(key=None,limit=1):
    results=[]
    async with lock:
        seed_folder_routes();seed_auto_followups()
        rows=db.execute("select r.principal,r.target,r.slot,r.desired,r.revision from folder_routes r left join folder_pauses p on p.principal=r.principal where r.revision!=r.applied_revision and r.next_attempt_at<=? and (p.until_at is null or p.until_at<=?) order by r.queued_at",(stamp(),stamp())).fetchall()
        if key:rows=[r for r in rows if key=='dm:'+r[1]]
        for principal,target,slot,desired,revision in rows[:limit]:
            try:
                client,slot=await folder_client(principal,slot)
                await asyncio.wait_for(move_chat_folder(client,principal,target,desired),timeout=20)
                db.execute("update folder_routes set slot=?,applied=?,applied_revision=?,checked_at=?,error='',next_attempt_at='' where principal=? and target=? and revision=?",(slot,desired,revision,stamp(),principal,target,revision));db.commit()
                results.append({'target':target,'ok':True,'folder':desired})
            except Exception as exc:
                detail=exc.detail if isinstance(exc,HTTPException) else 'Telegram folder sync failed. Check the folder names and account folder limits, then retry.'
                delay=300
                if isinstance(exc,errors.FloodWaitError):
                    delay=max(300,exc.seconds+5);detail=f'Telegram requests a {exc.seconds}s wait before folder changes.'
                    db.execute('insert or replace into folder_pauses values(?,?,?)',(principal,(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(),detail))
                elif type(exc).__name__=='FilterIncludeEmptyError':detail='Telegram rejected an empty source folder. Manage its last chat in Telegram, then retry folder sync.'
                elif isinstance(exc,asyncio.TimeoutError):detail='Telegram folder sync timed out. The message is still sent; retry folder sync only.'
                db.execute('update folder_routes set slot=?,checked_at=?,error=?,next_attempt_at=? where principal=? and target=? and revision=?',(slot,stamp(),detail,(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(),principal,target,revision));db.commit()
                results.append({'target':target,'ok':False,'error':detail})
        return {'checked':len(results),'remaining':max(0,len(rows)-len(results)),'results':results}
@app.post('/folders/sync',dependencies=[Depends(auth)])
async def check_chat_folders(body:ReplySync):
    if body.key and (not body.key.startswith('dm:') or not any(l['key']==body.key and l['last_sent_at'] for l in lead_records())):raise HTTPException(400,'Choose a contacted direct-message lead.')
    # Manual retries may clear a per-chat delay, but never bypass an account's Telegram wait.
    if body.key:db.execute("update folder_routes set next_attempt_at='' where target=?",(body.key.split(':',1)[1],));db.commit()
    return await sync_folder_routes(body.key,limit=3)
async def folder_routing_loop():
    while True:
        await asyncio.sleep(5)
        try:await sync_folder_routes(limit=1)
        except asyncio.CancelledError:raise
        except Exception:pass

def is_affirmative_reply(text):
    if '?' in text:return False
    value=re.sub(r"[^a-z0-9\s]",'',str(text).casefold())
    value=' '.join(value.split())
    return value in {'yes','yeah','yeh','yep','yup','yes please','yeah please','yeh please','yes sure','yeah sure','yes i am','yes im the right person','yes thats me','yes that is me','yes correct','yes go ahead','yes send details','yes please send details'}
def is_negative_reply(text):
    if '?' in str(text):return False
    return ' '.join(re.sub(r"[^a-z0-9\s]",'',str(text).casefold()).split()) in {'no','nope','nah','no i am not','no im not','no thats not me','no that is not me'}
def is_opt_out(text):return bool(re.search(r"\b(stop|unsubscribe|not interested|no thanks|no thank you|dont message|do not message|dont contact|do not contact)\b",str(text).casefold().replace("'",'')))
def arm_auto_yes(principal,target,slot,root_id,contact_id,exchange,token_symbol,pitch,demo,no_reply):
    db.execute('insert or ignore into auto_yes_enrollments(principal,target,root_id,contact_id,slot,exchange,token_symbol,pitch,demo,enabled,armed_at,no_reply) values(?,?,?,?,?,?,?,?,?,?,?,?)',(principal,target,root_id,contact_id,slot,exchange,token_symbol,pitch,demo,1,stamp(),no_reply));db.commit()
def queue_auto_yes(principal,target,slot,message):
    enrollment=db.execute('select root_id,contact_id,exchange,token_symbol,pitch,demo,enabled,no_reply from auto_yes_enrollments where principal=? and target=?',(principal,target)).fetchone()
    if not enrollment:return
    root_id,cid,exchange,token,pitch,demo,enabled,no_reply=enrollment
    text=getattr(message,'raw_text',None) or getattr(message,'message',None) or ''
    root=db.execute("select o.at,coalesce(d.telegram_message_id,0) from outbox o left join message_details d on d.delivery_id=o.id where o.id=? and o.principal=? and o.target=? and o.kind='dm' and o.status='Sent'",(root_id,principal,target)).fetchone()
    if not root:return
    at=message.date.replace(tzinfo=message.date.tzinfo or timezone.utc)
    if (message.id<=root[1] if root[1] else at<datetime.fromisoformat(root[0]).replace(microsecond=0)):return
    if getattr(message,'fwd_from',None):return
    if is_opt_out(text):
        db.execute('update auto_yes_enrollments set enabled=0 where principal=? and target=?',(principal,target))
        db.execute("update auto_yes_jobs set status='Cancelled',error='Stopped after an opt-out' where principal=? and target=? and status not in ('Complete','Cancelled') and reply_id<?",(principal,target,message.id));db.commit();return
    if not enabled or getattr(message,'fwd_from',None):return
    branch='yes' if is_affirmative_reply(text) else 'no' if is_negative_reply(text) else None
    if not branch:return
    contact=db.execute('select data from contacts where id=?',(cid,)).fetchone()
    if not contact:return
    contact=json.loads(contact[0]);texts=[personalize_message(value,contact,token,exchange) for value in ((pitch,demo) if branch=='yes' else (no_reply or DEFAULT_NO_REPLY,''))]
    db.execute('insert or ignore into auto_yes_jobs(id,principal,target,reply_id,root_id,pitch,demo,created_at,branch) values(?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,principal,target,message.id,root_id,*texts,stamp(),branch));db.commit()
def auto_yes_summary(target,principals):
    row=db.execute('select principal,exchange,token_symbol,enabled from auto_yes_enrollments where target=? order by armed_at desc',(target,)).fetchall()
    row=next((r for r in row if r[0] in principals),None)
    if not row:return None
    principal,exchange,token,enabled=row
    job=db.execute('select id,status,step,error,branch from auto_yes_jobs where principal=? and target=?',(principal,target)).fetchone()
    status=job[1] if job else 'Waiting for yes / no'
    if status not in ('Complete','Cancelled','Needs attention') and (not enabled or not settings()['auto_yes_enabled']):status='Paused'
    return {'exchange':exchange,'exchange_name':EXCHANGES.get(exchange,exchange),'token_symbol':token,'enabled':bool(enabled),'status':status,'sent_parts':job[2] if job else 0,'error':job[3] if job else '','job_id':job[0] if job else None,'branch':job[4] if job else None,'completed_once':bool(job and job[1]=='Complete'),'total_parts':(1 if job[4]=='no' else 2) if job else 0}
def validate_auto_yes_send(job_id,principal,target):
    row=db.execute('select j.status,e.enabled from auto_yes_jobs j join auto_yes_enrollments e on e.principal=j.principal and e.target=j.target where j.id=? and j.principal=? and j.target=?',(job_id,principal,target)).fetchone()
    if not row or row[0] in ('Cancelled','Complete','Needs attention'):raise HTTPException(409,'This automatic sequence is no longer pending')
    if not row[1] or not settings()['auto_yes_enabled']:raise HTTPException(423,'Automatic replies are paused')
class AutoYesControl(BaseModel):
    key:str=Field(max_length=100)
    enabled:bool
@app.post('/auto-yes/update',dependencies=[Depends(auth)])
async def update_auto_yes(body:AutoYesControl):
    if not body.key.startswith('dm:'):raise HTTPException(400,'Choose a direct-message lead')
    async with lock:
        target=body.key.split(':',1)[1]
        if not db.execute('select 1 from auto_yes_enrollments where target=?',(target,)).fetchone():raise HTTPException(404,'This contact has no automatic reply sequence')
        if body.enabled and db.execute("select 1 from auto_yes_jobs where target=? and status in ('Complete','Cancelled','Needs attention')",(target,)).fetchone():raise HTTPException(409,'This automatic response has finished or stopped and cannot be restarted. Each conversation receives it once.')
        db.execute('update auto_yes_enrollments set enabled=? where target=?',(int(body.enabled),target))
        db.execute("update auto_yes_jobs set status=? where target=? and status in ('Pending','Paused')",('Pending' if body.enabled else 'Paused',target));db.commit()
    return {'ok':True}
async def process_auto_yes(limit=1):
    async with auto_yes_lock:
        if not settings()['auto_yes_enabled']:return {'processed':0,'results':[]}
        rows=db.execute("select j.id,j.principal,j.target,j.root_id,j.pitch,j.demo,j.step,e.slot,e.contact_id,e.exchange,e.token_symbol,j.branch from auto_yes_jobs j join auto_yes_enrollments e on e.principal=j.principal and e.target=j.target where j.status in ('Pending','Paused') and e.enabled=1 and j.next_attempt_at<=? order by j.created_at limit ?",(stamp(),limit)).fetchall();results=[]
        for job_id,principal,target,root_id,pitch,demo,step,preferred,cid,exchange,token,branch in rows:
            current_part=step+1;total_parts=1 if branch=='no' else 2
            try:
                try:client,slot=await folder_client(principal,preferred)
                except HTTPException:raise HTTPException(409,'Reconnect the original sender to continue the automatic sequence')
                for part in range(step+1,total_parts+1):
                    current_part=part
                    db.execute("update auto_yes_jobs set status='Sending' where id=? and status in ('Pending','Paused')",(job_id,));db.commit()
                    await deliver(cid,slot,'dm',pitch if part==1 else demo,followup_of=root_id,request_id='auto-yes:'+job_id+':'+str(part),expected_principal=principal,token_symbol=token,exchange=exchange,automation_job=job_id,automation_step=part)
                    with db:
                        db.execute("update auto_yes_jobs set step=?,status=?,error='',next_attempt_at='' where id=?",(part,'Complete' if part==total_parts else 'Pending',job_id))
                        if part==total_parts:db.execute('update auto_yes_enrollments set enabled=0 where principal=? and target=?',(principal,target))
                results.append({'job_id':job_id,'status':'Complete'})
            except Exception as exc:
                existing=db.execute('select status from auto_yes_jobs where id=?',(job_id,)).fetchone()[0]
                attempt=db.execute('select o.status from followup_requests f join outbox o on o.id=f.delivery_id where f.request_id=?',('auto-yes:'+job_id+':'+str(current_part),)).fetchone()
                detail=(exc.detail.get('message',str(exc.detail)) if isinstance(exc.detail,dict) else exc.detail) if isinstance(exc,HTTPException) else 'Automatic message delivery failed. Review the conversation and delivery history.'
                state='Needs attention';next_at=''
                if existing=='Cancelled':state='Cancelled'
                elif isinstance(exc,HTTPException) and exc.status_code==423:state='Paused'
                elif not attempt and isinstance(exc,HTTPException) and (exc.status_code==429 or 'Reconnect the original sender' in str(detail)):
                    state='Pending';next_at=(exc.detail.get('next_available_at') if isinstance(exc.detail,dict) else None) or (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
                db.execute('update auto_yes_jobs set status=?,error=?,next_attempt_at=? where id=?',(state,detail,next_at,job_id));db.commit();results.append({'job_id':job_id,'status':state,'error':detail})
        return {'processed':len(results),'results':results}
async def auto_yes_loop():
    while True:
        await asyncio.sleep(3)
        try:await process_auto_yes(limit=1)
        except asyncio.CancelledError:raise
        except Exception:pass

# One automatic follow-up per conversation, 72 hours after its first confirmed DM.
def seed_auto_followups():
    rows=db.execute("select o.id,o.principal,o.target,o.slot,o.contact_id,o.at,coalesce(d.token_symbol,''),coalesce(d.exchange,'') from outbox o left join message_details d on d.delivery_id=o.id where o.kind='dm' and o.status='Sent' and d.followup_of is null order by o.at,o.rowid").fetchall()
    for root,principal,target,slot,cid,at,token,exchange in rows:
        due=(datetime.fromisoformat(at)+timedelta(days=3)).isoformat()
        db.execute("insert or ignore into auto_followup_jobs(root_id,principal,target,slot,contact_id,due_at,token_symbol,exchange) values(?,?,?,?,?,?,?,?)",(root,principal,target,slot,cid,due,token,exchange))
    db.commit()
def auto_followup_gate(job):
    root,principal,target=job[:3]
    source=db.execute("select principal,target,kind,status from outbox where id=?",(root,)).fetchone()
    if source!=(principal,target,'dm','Sent'):return 'Cancelled','Original delivery is unavailable'
    if db.execute('select 1 from replies where target=? limit 1',(target,)).fetchone():return 'Cancelled','Stopped — reply received'
    if lead_config('dm:'+target)['stage'] in ('Replied','Meeting','Proposal','Client'):return 'Cancelled','Stopped — lead has progressed'
    own=db.execute('select delivery_id from followup_requests where request_id=?',('auto-followup:'+root,)).fetchone()
    if db.execute("select 1 from outbox o join message_details d on d.delivery_id=o.id where o.target=? and o.kind='dm' and o.status='Sent' and d.followup_of is not null and o.id!=? limit 1",(target,own[0] if own else '')).fetchone():return 'Cancelled','A follow-up has already been sent'
    if not settings()['auto_followup_enabled'] or not lead_config('dm:'+target)['reminders_enabled']:return 'Paused','Automatic follow-up paused'
    if db.execute("select 1 from outbox where target=? and kind='dm' and status in ('Sending','Uncertain') limit 1",(target,)).fetchone():return 'Needs attention','Review uncertain delivery before sending'
    return None,''
def auto_followup_summary(target):
    row=db.execute('select root_id,principal,target,slot,due_at,status,error from auto_followup_jobs where target=?',(target,)).fetchone()
    if not row:
        root=db.execute("select o.id,o.principal,o.target,o.slot,o.at from outbox o left join message_details d on d.delivery_id=o.id where o.kind='dm' and o.status='Sent' and o.target=? and d.followup_of is null order by o.at,o.rowid limit 1",(target,)).fetchone()
        if not root:return None
        row=(*root[:4],(datetime.fromisoformat(root[4])+timedelta(days=3)).isoformat(),'Scheduled','')
    root,principal,target,slot,due,status,error=row
    if status not in ('Complete','Cancelled','Needs attention'):
        gate,reason=auto_followup_gate((root,principal,target))
        if gate:status,error=gate,reason
    current=db.execute('select slot from account_info where principal=? order by slot limit 1',(principal,)).fetchone()
    return {'root_id':root,'principal':principal,'account_id':current[0] if current else slot,'due_at':due,'status':status,'error':error,'days':3,'enabled':bool(settings()['auto_followup_enabled'] and lead_config('dm:'+target)['reminders_enabled'])}
def validate_auto_followup_send(root_id,principal,target):
    row=db.execute('select root_id,principal,target,due_at,status from auto_followup_jobs where root_id=?',(root_id,)).fetchone()
    if not row or row[1:3]!=(principal,target):raise HTTPException(409,'Automatic follow-up must use the first message sender and recipient')
    if row[4] in ('Cancelled','Complete','Needs attention'):raise HTTPException(409,'This automatic follow-up is no longer pending')
    gate,reason=auto_followup_gate(row)
    if gate:raise HTTPException(423 if gate=='Paused' else 409,reason)
    if datetime.fromisoformat(row[3])>datetime.now(timezone.utc):raise HTTPException(409,'The three-day follow-up is not due yet')
    sync=db.execute('select checked_at,complete,error from reply_sync where principal=? and target=?',(principal,target)).fetchone()
    if not sync or not sync[1] or sync[2] or not sync[0] or datetime.now(timezone.utc)-datetime.fromisoformat(sync[0])>timedelta(minutes=2):raise HTTPException(409,'Reply history must be fully checked before the automatic follow-up')
async def process_auto_followups(limit=1):
    async with auto_followup_lock:
        seed_auto_followups()
        if not settings()['auto_followup_enabled']:return {'processed':0,'results':[]}
        rows=db.execute("select root_id,principal,target,slot,contact_id,due_at,token_symbol,exchange,body from auto_followup_jobs where status in ('Scheduled','Pending','Paused','Waiting') and due_at<=? and next_attempt_at<=? order by due_at limit ?",(stamp(),stamp(),limit)).fetchall();results=[]
        for root,principal,target,preferred,cid,due,token,exchange,body in rows:
            state='Waiting';error='';retry=''
            try:
                gate,reason=auto_followup_gate((root,principal,target))
                if gate:
                    state=gate;raise HTTPException(423 if gate=='Paused' else 409,reason)
                try:client,slot=await folder_client(principal,preferred)
                except (HTTPException,errors.RPCError,OSError):raise HTTPException(503,'Reconnect the original sender; no other account will be used')
                first=db.execute('select at from outbox where id=?',(root,)).fetchone()[0]
                sync=await sync_reply_pair(principal,target,slot,first)
                gate,reason=auto_followup_gate((root,principal,target))
                if gate:
                    state=gate;raise HTTPException(423 if gate=='Paused' else 409,reason)
                if not sync.get('ok') or not sync.get('complete'):raise HTTPException(503,sync.get('error') or 'Waiting for the remaining reply history to be checked')
                if not body:
                    contact=db.execute('select data from contacts where id=?',(cid,)).fetchone()
                    if not contact:state='Needs attention';raise HTTPException(409,'Saved recipient is unavailable')
                    body=personalize_message(settings()['followup_template'],json.loads(contact[0]),token,exchange)
                    db.execute('update auto_followup_jobs set body=? where root_id=?',(body,root));db.commit()
                db.execute("update auto_followup_jobs set status='Sending' where root_id=?",(root,));db.commit()
                await deliver(cid,slot,'dm',body,followup_of=root,request_id='auto-followup:'+root,expected_principal=principal,token_symbol=token,exchange=exchange,automatic_followup=root)
                state='Complete'
            except Exception as exc:
                error=str(exc.detail) if isinstance(exc,HTTPException) else 'Automatic follow-up failed. Check delivery history.'
                attempt=db.execute('select o.status from followup_requests f join outbox o on o.id=f.delivery_id where f.request_id=?',('auto-followup:'+root,)).fetchone()
                if attempt and attempt[0]=='Sent':state='Complete';error=''
                elif attempt:state='Needs attention'
                elif isinstance(exc,HTTPException) and exc.status_code in (429,503):state='Waiting'
                elif isinstance(exc,HTTPException) and exc.status_code==423:state='Paused'
                elif state=='Waiting':
                    gate,reason=auto_followup_gate((root,principal,target))
                    state=gate or 'Needs attention'
                    if gate:error=reason
                if state in ('Waiting','Paused'):retry=(exc.detail.get('next_available_at') if isinstance(exc,HTTPException) and isinstance(exc.detail,dict) else None) or (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
            db.execute('update auto_followup_jobs set status=?,error=?,next_attempt_at=? where root_id=?',(state,error,retry,root));db.commit()
            results.append({'root_id':root,'status':state,'error':error})
        return {'processed':len(results),'results':results}
async def auto_followup_loop():
    while True:
        await asyncio.sleep(30)
        try:await process_auto_followups(limit=1)
        except asyncio.CancelledError:raise
        except Exception:pass

@app.on_event('startup')
async def start():
    global reply_task,folder_task,auto_yes_task,auto_followup_task
    seed_folder_routes();seed_auto_followups()
    for slot in (1,2,3):
        try:
            c=make_client(slot)
            if c:clients[slot]=c;await c.connect()
        except Exception:startup_errors[slot]='Telegram connection unavailable. Reconnect this account in Connections.'
    reply_task=asyncio.create_task(reply_sync_loop())
    folder_task=asyncio.create_task(folder_routing_loop())
    auto_yes_task=asyncio.create_task(auto_yes_loop())
    auto_followup_task=asyncio.create_task(auto_followup_loop())
@app.on_event('shutdown')
async def stop():
    for task in (reply_task,folder_task,auto_yes_task,auto_followup_task):
        if task:
            task.cancel()
            try:await task
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
class Verify(Account):phone:str='';code:str='';password:str=''
class Scan(Account):link:str;join:bool=False;leave_after_scan:bool=False
class Config(BaseModel):template:str='';sheet_url:str='';sender_account:int=Field(default=1,ge=1,le=3);token_symbol:str=Field(default='',max_length=33)
class Templates(BaseModel):
    template:str=Field(min_length=1,max_length=4096)
    followup_template:str=Field(min_length=1,max_length=4096)
    yes_pitch_template:str|None=Field(default=None,min_length=1,max_length=4096)
    yes_demo_template:str|None=Field(default=None,min_length=1,max_length=4096)
    no_reply_template:str|None=Field(default=None,min_length=1,max_length=4096)
    auto_yes_enabled:bool|None=None
    auto_followup_enabled:bool|None=None
class Send(Account):id:str;kind:Literal['dm','group']='dm';message:str|None=None;token_symbol:str|None=Field(default=None,max_length=33);exchange:str=Field(default='',max_length=64);auto_yes:bool=False
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
async def health():
    from fastapi.responses import JSONResponse
    return JSONResponse({'service':'teamradar','ok':True,'version':'3.7'},headers={'Cache-Control':'no-store, max-age=0'})
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
        clients[slot]=attach_reply_listener(candidate,slot);login_pending.pop(slot,None);startup_errors.pop(slot,None)
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
        accounts.append({'id':slot,'label':label,'phone':phone,'api_configured':c is not None,'authorized':authorized,'usage':u,'daily_goal':DAILY_GOAL,'sent_today':sent,'blocked_until':blocked,'error':startup_errors.get(slot,''),'health':account_health(principal,c,authorized,blocked,startup_errors.get(slot,'')),'pacing':pacing_status(principal),**login_progress(slot)})
    return {'version':'3.7','api_configured':accounts[0]['api_configured'],'authorized':any(a['authorized'] for a in accounts),'accounts':accounts,'quota_date':today(),'quota_timezone':'Asia/Kolkata','contacts':contacts(),'settings':settings(),'deliveries':records(),'quota_resets':reset_records(),'leads':lead_records(),'features':{'token_personalization':True,'new_recipient_dm_quota':True,'message_templates':True,'lead_management':True,'telegram_folder_routing':True,'code_first_login':True,'automatic_yes_sequence':True,'automatic_followups':True,'original_sender_lock':True,'workspace_reset':True,'reply_inbox':True,'send_pacing':True,'contact_import':True}}
# Workspace reset never disconnects Telegram or changes message templates.
WORKSPACE_DATA_TABLES=('contacts','deliveries','outbox','message_details','followup_requests','quota_resets','lead_settings','replies','reply_sync','folder_routes','empty_folder_templates','auto_yes_jobs','auto_yes_enrollments','auto_followup_jobs','import_batches')
def workspace_reset_counts():
    count=lambda table:db.execute('select count(*) from '+table).fetchone()[0]
    return {'contacts':count('contacts'),'messages':count('outbox'),'replies':count('replies'),'leads':len(lead_records()),'automations':count('auto_yes_jobs')+count('auto_yes_enrollments')+count('auto_followup_jobs')}
class WorkspaceReset(BaseModel):
    confirmation:Literal['RESET DATA']
    request_id:str=Field(min_length=8,max_length=128)
@app.get('/workspace/reset-preview',dependencies=[Depends(auth)])
async def preview_workspace_reset():
    async with lock:return {'counts':workspace_reset_counts(),'preserves':['Telegram accounts','API credentials','message templates','workspace login','Telegram-imposed waits']}
@app.post('/workspace/reset',dependencies=[Depends(auth)])
async def reset_workspace(body:WorkspaceReset):
    # Wait for existing send/check jobs, then prevent a stale job from writing after reset.
    async with auto_yes_lock:
        async with auto_followup_lock:
            async with lock:
                previous=db.execute('select result from workspace_reset_requests where request_id=?',(body.request_id,)).fetchone()
                if previous:return {**json.loads(previous[0]),'already_reset':True}
                result={'ok':True,'counts':workspace_reset_counts(),'at':stamp()}
                with db:
                    for table in WORKSPACE_DATA_TABLES:db.execute('delete from '+table)
                    db.execute("insert or replace into meta values('outbox_migrated','1')")
                    db.execute('insert into workspace_reset_requests values(?,?)',(body.request_id,json.dumps(result)))
                return result

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

LOGIN_AUTH_ERRORS=(errors.AuthKeyUnregisteredError,errors.AuthKeyInvalidError,errors.SessionRevokedError,errors.SessionExpiredError,errors.AuthRestartError)
def normalize_login_phone(phone):
    value=re.sub(r'[\s().-]','',phone)
    if not re.fullmatch(r'\+[1-9][0-9]{6,14}',value):raise HTTPException(400,'Enter your phone number with + and country code, for example +91…')
    return value
def login_progress(slot):
    state=login_pending.get(slot)
    if state and state['expires_at']<=stamp():login_pending.pop(slot,None);state=None
    return {'login_step':('password' if state['password_required'] else 'code') if state else 'phone','login_phone_hint':('••••'+state['phone'][-4:]) if state else ''}
async def renew_login_client(slot,old):
    # Reset only a rejected Telegram transport key for this slot; retain app records and API settings.
    await old.disconnect()
    session=getattr(old,'session',None)
    if session is None:raise HTTPException(409,'This Telegram login expired. Request a new login code to start again.')
    session.auth_key=None;session.save();session.close()
    replacement=make_client(slot)
    if replacement is None:raise HTTPException(409,'Configure the Telegram API for this account first.')
    clients[slot]=replacement;await replacement.connect();return replacement
@app.post('/login',dependencies=[Depends(auth)])
async def login(body:Login):
    phone=normalize_login_phone(body.phone)
    async with lock:
        c=require_client(body.account_id)
        if not c.is_connected():await c.connect()
        if await c.is_user_authorized():
            await identify(body.account_id,c);login_pending.pop(body.account_id,None)
            return {'authorized':True,'account_id':body.account_id}
        login_pending.pop(body.account_id,None)
        try:
            try:r=await c.send_code_request(phone)
            except LOGIN_AUTH_ERRORS:
                c=await renew_login_client(body.account_id,c);r=await c.send_code_request(phone)
        except LOGIN_AUTH_ERRORS:raise HTTPException(409,'Telegram could not start this login. Request a new code for this account again.')
        except errors.PhoneNumberInvalidError:raise HTTPException(400,'Telegram rejected this phone number. Check the +country code and number.')
        if not getattr(r,'phone_code_hash',None):raise HTTPException(409,'Telegram did not start a code login. Request a new login code.')
        login_pending[body.account_id]={'phone':phone,'hash':r.phone_code_hash,'password_required':False,'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}
    return {'ok':True,'account_id':body.account_id,'login_step':'code'}
@app.post('/verify',dependencies=[Depends(auth)])
async def verify(body:Verify):
    async with lock:
        c=require_client(body.account_id)
        if not c.is_connected():await c.connect()
        if await c.is_user_authorized():
            await identify(body.account_id,c);login_pending.pop(body.account_id,None)
            return {'authorized':True,'account_id':body.account_id}
        login_progress(body.account_id);state=login_pending.get(body.account_id)
        if not state:raise HTTPException(409,'Request a new login code for this account first. Pending logins expire after a restart or timeout.')
        if body.phone and normalize_login_phone(body.phone)!=state['phone']:raise HTTPException(409,'This login code belongs to another phone number. Request a new code for the number shown.')
        try:
            if not state['password_required']:
                code=re.sub(r'[\s-]','',body.code)
                if not code:raise HTTPException(400,'Enter the Telegram login code first. The two-step password is checked after the code.')
                try:await c.sign_in(state['phone'],code,phone_code_hash=state['hash'])
                except errors.SessionPasswordNeededError:state['password_required']=True
            if state['password_required']:
                if not body.password:return {'password_required':True,'account_id':body.account_id,'login_step':'password'}
                await c.sign_in(password=body.password)
        except (errors.PhoneCodeExpiredError,errors.PhoneCodeHashEmptyError):
            login_pending.pop(body.account_id,None);raise HTTPException(409,'This Telegram login code expired. Request a new login code.')
        except (errors.PhoneCodeInvalidError,errors.PhoneCodeEmptyError):raise HTTPException(400,'That Telegram login code is incorrect. Check the latest code and try again.')
        except errors.PasswordHashInvalidError:raise HTTPException(400,'The Telegram two-step password is incorrect. Try your Telegram account password again.')
        except LOGIN_AUTH_ERRORS:
            login_pending.pop(body.account_id,None);raise HTTPException(409,'This Telegram login session expired. Request a new login code, verify the code first, then enter the two-step password only when asked.')
        try:await identify(body.account_id,c)
        except HTTPException:
            login_pending.pop(body.account_id,None);await c.log_out();raise
        login_pending.pop(body.account_id,None)
    return {'authorized':True,'account_id':body.account_id}
@app.post('/logout',dependencies=[Depends(auth)])
async def logout(body:Account):
    async with lock:
        c=require_client(body.account_id);login_pending.pop(body.account_id,None);await c.log_out()
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
    values={k:(v.strip() if isinstance(v,str) else v) for k,v in body.model_dump(exclude_none=True).items()}
    if any(isinstance(v,str) and not v for v in values.values()):raise HTTPException(400,'Message templates must contain text')
    merged={**settings(),**values}
    db.execute('insert or replace into settings values(1,?)',(json.dumps(merged),));db.commit()
    return {'ok':True,**values}
def normalize_token(value):
    symbol=(value or '').strip().lstrip('$')
    if symbol and not re.fullmatch(r'[A-Za-z0-9._-]{1,32}',symbol):raise HTTPException(400,'Use a token symbol of up to 32 letters, numbers, dots, underscores or hyphens')
    return symbol

def normalize_exchange(value):
    value=(value or '').strip()
    if not value:return ''
    for key,label in EXCHANGES.items():
        if re.sub(r'[^a-z0-9]','',value.lower()) in (key,re.sub(r'[^a-z0-9]','',label.lower())):return key
    raise HTTPException(400,'Choose an exchange from the dropdown')

def personalize_message(text,contact,token_symbol='',exchange=''):
    symbol=normalize_token(token_symbol)
    if (re.search(r'[$@]TOKEN\b',text) or '{{token}}' in text) and not symbol:raise HTTPException(400,'Enter the token name above the message preview before sending')
    exchange=normalize_exchange(exchange)
    if '{{exchange}}' in text and not exchange:raise HTTPException(400,'Select the exchange before sending')
    text=text.replace('{{exchange}}',EXCHANGES.get(exchange,''))
    handle='@'+contact['username'].lstrip('@') if contact.get('username') else (contact.get('name') or 'there')
    text=text.replace('@{{username}}',handle).replace('{{username}}',handle).replace('@username',handle)
    text=text.replace('{{name}}',contact.get('name','')).replace('{{role}}',contact.get('role','')).replace('{{group}}',contact.get('group',''))
    text=text.replace('{{token}}','$'+symbol if symbol else '')
    return re.sub(r'[$@]TOKEN\b',lambda match:'$'+symbol,text)

async def deliver(cid,slot=1,kind='dm',message=None,followup_of=None,request_id=None,expected_principal=None,token_symbol=None,exchange='',auto_yes=False,automation_job=None,automation_step=0,automatic_followup=None):
    async with lock:
        c=await ready(slot);principal=await identify(slot,c)
        row=db.execute('select data from contacts where id=?',(cid,)).fetchone()
        if not row:raise HTTPException(404,'Contact not found')
        contact=json.loads(row[0])
        if contact.get('is_bot'):raise HTTPException(400,'Bot admins are excluded from messaging')
        if expected_principal and expected_principal!=principal:raise HTTPException(409,'The original sender is not logged into this account slot. Reconnect the original Telegram account to send this follow-up.')
        if (kind=='group') != (contact.get('kind')=='group'):raise HTTPException(400,'Choose a group chat for group messages or a team member for DMs')
        if kind=='group' and contact.get('membership',{}).get(str(slot))=='left':raise HTTPException(409,f'Account {slot} left this group. Rejoin and rescan with Leave group after scan switched off before sending group messages.')
        resolved_peer=None
        if contact.get('import_unresolved'):
            pause=db.execute('select blocked_until from account_info where slot=?',(slot,)).fetchone()
            if pause and pause[0] and pause[0]>stamp():raise HTTPException(429,'This account is paused by Telegram until '+pause[0])
            enforce_send_pacing(principal,slot)
            try:resolved=await c.get_entity(contact['username'])
            except (errors.FloodWaitError,errors.PeerFloodError) as exc:
                pause_for_telegram(principal,exc);raise
            except (ValueError,TypeError):raise HTTPException(409,'Telegram could not find this imported username. Check the link or scan the group first.')
            if kind=='dm' and (not isinstance(resolved,types.User) or getattr(resolved,'bot',False) or getattr(resolved,'deleted',False)):raise HTTPException(400,'This imported link is not a person. Use a Group chat import or Find team for groups; bots are excluded.')
            if kind=='group' and not (isinstance(resolved,types.Chat) or getattr(resolved,'megagroup',False)):raise HTTPException(400,'This imported link is not a group chat. Channels cannot receive group messages.')
            field='group_id' if kind=='group' else 'user_id'
            contact[field]=str(utils.get_peer_id(resolved) if kind=='group' else resolved.id)
            contact['import_unresolved']=False;save(contact);resolved_peer=resolved
        text=(message if message is not None else settings()['template']).strip()
        if not text:raise HTTPException(400,'Write your message before sending')
        symbol=normalize_token(settings().get('token_symbol','') if token_symbol is None else token_symbol)
        exchange=normalize_exchange(exchange)
        if followup_of:
            parent=db.execute('select principal,target,kind,status from outbox where id=?',(followup_of,)).fetchone()
            destination=str(contact['group_id'] if kind=='group' else contact['user_id'])
            if parent!=(principal,destination,kind,'Sent'):raise HTTPException(409,'Every follow-up must use the original Telegram sender and recipient')
            if kind=='dm':
                first_sender=db.execute("select o.principal from outbox o left join message_details d on d.delivery_id=o.id where o.kind='dm' and o.target=? and o.status='Sent' and d.followup_of is null order by o.at,o.rowid limit 1",(destination,)).fetchone()
                if not first_sender or first_sender[0]!=principal:raise HTTPException(409,'All conversation messages must stay with the first message sender')
        if automatic_followup:validate_auto_followup_send(automatic_followup,principal,str(contact['user_id']))
        if automation_job:validate_auto_yes_send(automation_job,principal,str(contact['user_id']))
        yes_cfg=settings() if auto_yes else None
        if auto_yes:
            if kind!='dm' or followup_of:raise HTTPException(400,'Automatic replies can be enabled only on a new direct message')
            if not exchange or not symbol:raise HTTPException(400,'Select the exchange and enter the token to enable automatic replies')
            personalize_message(yes_cfg['yes_pitch_template'],contact,symbol,exchange)
            personalize_message(yes_cfg['yes_demo_template'],contact,symbol,exchange)
            personalize_message(yes_cfg['no_reply_template'],contact,symbol,exchange)
        text=personalize_message(text,contact,symbol,exchange)
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
        enforce_send_pacing(principal,slot)
        # Resolve the destination using this sender's own Telegram permissions before reserving a send.
        try:
            if resolved_peer is not None:peer=resolved_peer
            elif kind=='group':peer=await c.get_entity(int(target))
            elif contact.get('username'):
                peer=await c.get_entity(contact['username'])
                if str(peer.id)!=target:raise HTTPException(409,'Username now belongs to another user. Rescan this contact before sending.')
            else:peer=await c.get_input_entity(int(target))
        except (errors.FloodWaitError,errors.PeerFloodError) as exc:
            pause_for_telegram(principal,exc);raise
        except (ValueError,TypeError):raise HTTPException(409,'This sender cannot resolve the recipient. Scan its group with this account first.')
        if kind=='dm' and getattr(peer,'bot',False):raise HTTPException(400,'This contact is a Telegram bot. Bot admins are excluded.')
        if kind=='group' and not (isinstance(peer,types.Chat) or getattr(peer,'megagroup',False)):raise HTTPException(400,'The selected destination is not a group chat')
        delivery_id=uuid.uuid4().hex
        # Record all attempts. DM quota counts unique new recipients; group quota counts attempts.
        sender_label=db.execute('select label from account_info where slot=?',(slot,)).fetchone()[0]
        with db:
            db.execute('insert into outbox values(?,?,?,?,?,?,?,?,?,?,?)',(delivery_id,principal,slot,kind,target,cid,'Sending',date,stamp(),'',digest))
            db.execute('insert into message_details(delivery_id,body,recipient_name,username,sender_label,followup_of,token_symbol) values(?,?,?,?,?,?,?)',(delivery_id,text,contact['name'],contact.get('username',''),sender_label,followup_of,symbol))
            db.execute('update message_details set exchange=?,automation_step=? where delivery_id=?',(exchange,automation_step,delivery_id))
            if followup_of:db.execute('insert into followup_requests values(?,?,?,?)',(request_id,delivery_id,followup_of,digest))
        db.execute('insert or replace into send_pacing values(?,?)',(principal,stamp()));db.commit()
        try:sent_message=await c.send_message(peer,text)
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
        if kind=='dm':
            db.execute('update message_details set telegram_message_id=? where delivery_id=?',(getattr(sent_message,'id',0) or 0,delivery_id));db.commit()
            queue_folder_route(principal,target,slot,'🔵',force=True)
            if auto_yes:arm_auto_yes(principal,target,slot,delivery_id,cid,exchange,symbol,yes_cfg['yes_pitch_template'],yes_cfg['yes_demo_template'],yes_cfg['no_reply_template'])
        return {'status':'Sent','id':cid,'account_id':slot,'kind':kind,'usage':usage(principal)}
@app.post('/send',dependencies=[Depends(auth)])
async def send(body:Send):return await deliver(body.id,body.account_id,body.kind,body.message,token_symbol=body.token_symbol,exchange=body.exchange,auto_yes=body.auto_yes)
@app.post('/follow-up',dependencies=[Depends(auth)])
async def follow_up(body:Followup):
    parent=db.execute('select principal,slot,kind,contact_id,status from outbox where id=?',(body.delivery_id,)).fetchone()
    if not parent:raise HTTPException(404,'Original message not found')
    principal,slot,kind,cid,status=parent
    if status!='Sent':raise HTTPException(409,'Follow-ups require a confirmed sent message')
    try:client,slot=await folder_client(principal,slot)
    except HTTPException:raise HTTPException(409,'Reconnect the original sender to send this follow-up. No other Telegram account will be used.')
    saved_token=db.execute('select token_symbol,exchange from message_details where delivery_id=?',(body.delivery_id,)).fetchone()
    symbol=body.token_symbol if body.token_symbol is not None else (saved_token[0] if saved_token else '')
    return await deliver(cid,slot,kind,body.message,followup_of=body.delivery_id,request_id=body.request_id,expected_principal=principal,token_symbol=symbol,exchange=saved_token[1] if saved_token else '')

# Spreadsheet imports are staged for review; they never join chats or send messages.
try:from backend import contact_import as importer
except ImportError:import contact_import as importer
class ImportRead(BaseModel):
    filename:str=Field(default='',max_length=200)
    content_base64:str=Field(default='',max_length=7*1024*1024)
    sheet_url:str=Field(default='',max_length=2000)
    worksheet:str=Field(default='',max_length=100)
class ImportPreview(BaseModel):
    rows:list[list[str]]=Field(max_length=1001)
    mapping:dict[str,int|None]
    has_header:bool=True
    default_kind:Literal['dm','group']='dm'
    source_name:str=Field(default='Spreadsheet import',max_length=200)
class ImportConfirm(BaseModel):
    batch_id:str=Field(max_length=64)

def import_error(exc):raise HTTPException(400,str(exc))
@app.post('/contacts/import/read',dependencies=[Depends(auth)])
async def read_import(body:ImportRead):
    if bool(body.content_base64)==bool(body.sheet_url):raise HTTPException(400,'Choose one file or Google Sheets URL.')
    if body.sheet_url:
        try:book_id=importer.sheet_identifier(body.sheet_url)
        except ValueError as exc:import_error(exc)
        if not os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'):raise HTTPException(409,'Google Sheets import needs the service account configured on your gateway. You can also download the tab as CSV or XLSX and upload it here.')
        def read_google():
            import gspread
            gc=gspread.service_account_from_dict(json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']))
            book=gc.open_by_key(book_id)
            ws=book.worksheet(body.worksheet) if body.worksheet else book.get_worksheet(0)
            return importer.bounded_matrix(ws.get('A1:AE1003'))
        try:rows=await asyncio.to_thread(read_google)
        except ValueError as exc:import_error(exc)
        except Exception:raise HTTPException(400,'Could not read that tab. Share the sheet with your gateway service-account email as Viewer, check the tab name, or upload a CSV/XLSX export.')
    else:
        try:rows=await asyncio.to_thread(importer.read_file,body.filename,body.content_base64)
        except ValueError as exc:import_error(exc)
    mapping,has_header=importer.default_mapping(rows)
    return {'rows':rows,'mapping':mapping,'has_header':has_header,'source_name':body.filename or 'Google Sheets import','columns':len(rows[0])}

def import_candidates(rows,mapping,has_header,default_kind):
    try:rows=importer.bounded_matrix(rows)
    except ValueError as exc:import_error(exc)
    if any(len(v)>500 for r in rows for v in r):raise HTTPException(400,'Cells may contain at most 500 characters.')
    if mapping.get('telegram') is None:raise HTTPException(400,'Choose the column containing Telegram usernames or links.')
    if any(v is not None and (v<0 or v>=len(rows[0])) for v in mapping.values()):raise HTTPException(400,'Choose a valid spreadsheet column.')
    data=rows[1:] if has_header else rows
    if len(data)>1000:raise HTTPException(400,'Import at most 1,000 contacts at a time.')
    known={c.get('username','').lower() for c in contacts() if c.get('username')};seen=set();items=[];candidates=[]
    def value(row,field):
        col=mapping.get(field)
        return row[col] if col is not None else ''
    for number,row in enumerate(data,2 if has_header else 1):
        item={'row':number,'telegram':value(row,'telegram'),'name':value(row,'name'),'status':'Ready','reason':''}
        try:
            handle=importer.telegram_handle(item['telegram'])
            kind=value(row,'kind').strip().lower() or default_kind
            if kind in ('person','people','user','contact'):kind='dm'
            if kind in ('gc','group chat','groupchat'):kind='group'
            if kind not in ('dm','group'):raise ValueError('Type must be dm or group.')
            if handle in known or handle in seen:item.update(status='Duplicate',reason='Already saved or repeated in this import.')
            else:
                cid='import:'+kind+':'+handle
                c={'id':cid,'name':item['name'] or '@'+handle,'username':handle,'user_id':cid if kind=='dm' else '', 'group_id':cid if kind=='group' else '', 'kind':kind,'role':value(row,'role') or ('Group chat' if kind=='group' else 'Imported contact'),'group':value(row,'group') or 'Spreadsheet import','link':'https://t.me/'+handle,'source':'Spreadsheet import · role not verified','status':'Ready','is_bot':False,'import_unresolved':True}
                candidates.append(c);seen.add(handle)
            item.update(username=handle,kind=kind,name=item['name'] or '@'+handle)
        except ValueError as exc:item.update(status='Skipped',reason=str(exc))
        items.append(item)
    return candidates,items
@app.post('/contacts/import/preview',dependencies=[Depends(auth)])
async def preview_import(body:ImportPreview):
    async with lock:
        candidates,items=import_candidates(body.rows,body.mapping,body.has_header,body.default_kind)
        batch=uuid.uuid4().hex;expiry=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
        db.execute('delete from import_batches where expires_at<?',(stamp(),))
        db.execute('insert into import_batches values(?,?,?)',(batch,json.dumps({'contacts':candidates,'source':body.source_name}),expiry));db.commit()
        return {'batch_id':batch,'items':items,'ready':len(candidates),'duplicates':sum(i['status']=='Duplicate' for i in items),'skipped':sum(i['status']=='Skipped' for i in items),'expires_at':expiry}
@app.post('/contacts/import/confirm',dependencies=[Depends(auth)])
async def confirm_import(body:ImportConfirm):
    async with lock:
        batch=db.execute('select data,expires_at from import_batches where id=?',(body.batch_id,)).fetchone()
        if not batch or batch[1]<stamp():raise HTTPException(409,'This preview expired or was already imported. Preview the sheet again.')
        payload=json.loads(batch[0]);known={c.get('username','').lower() for c in contacts() if c.get('username')};added=0;duplicates=0
        with db:
            for c in payload['contacts']:
                if c['username'] in known:duplicates+=1;continue
                c.update(scanned_at=stamp(),imported_at=stamp(),import_source=payload['source'])
                db.execute('insert or ignore into contacts values(?,?)',(c['id'],json.dumps(c)))
                known.add(c['username']);added+=1
            db.execute('delete from import_batches where id=?',(body.batch_id,))
        return {'ok':True,'added':added,'duplicates':duplicates}

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
