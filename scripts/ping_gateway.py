"""Public WMM health check for GitHub Actions or another external scheduler."""
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,urlopen

CONFIG=Path(__file__).resolve().parents[1]/'config'/'keep-alive.json'

def health_url(value):
    raw=str(value or '').strip()
    if not raw:return ''
    parsed=urlsplit(raw)
    try:port=parsed.port
    except ValueError:raise ValueError('Use your public HTTPS Render server URL')
    host=parsed.hostname or ''
    if parsed.scheme!='https' or not host.endswith('.onrender.com') or host=='.onrender.com' or parsed.username or parsed.password or port not in (None,443) or parsed.query or parsed.fragment or parsed.path not in ('','/','/health','/health/'):
        raise ValueError('Use the public HTTPS .onrender.com server URL without credentials, query parameters or other paths')
    return 'https://'+host+'/health'

def configured_url():
    override=os.getenv('WMM_GATEWAY_URL','').strip()
    if override:return health_url(override)
    saved=json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    return health_url(saved.get('gateway_url',''))

def ping(url,attempts=3):
    for attempt in range(attempts):
        try:
            req=Request(url,headers={'Accept':'application/json','Cache-Control':'no-cache','User-Agent':'WMM-KeepAlive/1.0'})
            with urlopen(req,timeout=75) as response:
                body=json.loads(response.read(16384))
                if response.status!=200 or not isinstance(body,dict) or body.get('ok') is not True or body.get('service')!='teamradar':raise ValueError('The endpoint did not return a healthy WMM gateway response')
            return body
        except (HTTPError,URLError,OSError,ValueError) as exc:
            if attempt==attempts-1:raise RuntimeError('WMM health check failed after bounded wake-up retries') from exc
            time.sleep(10)

def main():
    try:
        target=configured_url()
        if not target:
            print('::notice::Keep-alive is not configured. Set gateway_url in config/keep-alive.json or the WMM_GATEWAY_URL repository variable.')
            return 0
        result=ping(target)
        print('WMM gateway is responding: '+target+' (version '+str(result.get('version','unknown'))+')')
        return 0
    except (ValueError,RuntimeError,OSError) as exc:
        print('::error::'+str(exc));return 1

if __name__=='__main__':sys.exit(main())
