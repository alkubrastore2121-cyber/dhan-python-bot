#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║     DHAN QUANTUM TRADER v5.2 — FULL AUTO TOKEN REFRESH      ║
║   Auto Login + Token Refresh + Real Trading — 24/7          ║
║   Built on Mobile 📱 — Made in India 🇮🇳                   ║
╚═══════════════════════════════════════════════════════════════╝
"""

import os, time, json, logging, threading, random, hashlib, hmac, base64, struct
import requests, schedule, numpy as np
from datetime import datetime, time as dtime
from collections import deque
from flask import Flask, jsonify, request, render_template_string

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('DhanQuantum')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CFG = {
    'client_id':    os.environ.get('DHAN_CLIENT_ID', ''),
    'token':        os.environ.get('DHAN_TOKEN', ''),
    'api_key':      os.environ.get('DHAN_API_KEY', ''),
    'api_secret':   os.environ.get('DHAN_API_SECRET', ''),
    'capital':      int(os.environ.get('CAPITAL', '5000')),
    'max_trades':   int(os.environ.get('MAX_TRADES', '6')),
    'strategy':     os.environ.get('STRATEGY', 'MOMENTUM'),
    'max_loss':     int(os.environ.get('MAX_LOSS', '2000')),
    'max_profit':   int(os.environ.get('MAX_PROFIT', '5000')),
    'tg_token':     os.environ.get('TELEGRAM_TOKEN', ''),
    'tg_chat':      os.environ.get('TELEGRAM_CHAT', ''),
    'openrouter':   os.environ.get('OPENROUTER_KEY', ''),
    'risk_pct':     float(os.environ.get('RISK_PCT', '1.5')),
    'trailing_sl':  True,
}

DHAN_API = 'https://api.dhan.co'
app = Flask(__name__)
app.secret_key = 'dhan-quantum-2024'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WATCHLIST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WATCHLIST = [
    {'sym':'RELIANCE',   'id':'500325',  'sector':'Energy'},
    {'sym':'TCS',        'id':'532540',  'sector':'IT'},
    {'sym':'HDFCBANK',   'id':'500180',  'sector':'Banking'},
    {'sym':'INFY',       'id':'500209',  'sector':'IT'},
    {'sym':'ICICIBANK',  'id':'532174',  'sector':'Banking'},
    {'sym':'SBIN',       'id':'500112',  'sector':'Banking'},
    {'sym':'AXISBANK',   'id':'532215',  'sector':'Banking'},
    {'sym':'WIPRO',      'id':'507685',  'sector':'IT'},
    {'sym':'TATAMOTORS', 'id':'500570',  'sector':'Auto'},
    {'sym':'BAJFINANCE', 'id':'500034',  'sector':'NBFC'},
    {'sym':'ADANIENT',   'id':'512599',  'sector':'Infra'},
    {'sym':'KOTAKBANK',  'id':'500247',  'sector':'Banking'},
    {'sym':'MARUTI',     'id':'532500',  'sector':'Auto'},
    {'sym':'LTIM',       'id':'540005',  'sector':'IT'},
    {'sym':'BHARTIARTL', 'id':'532454',  'sector':'Telecom'},
    {'sym':'SUNPHARMA',  'id':'524715',  'sector':'Pharma'},
    {'sym':'TATASTEEL',  'id':'500470',  'sector':'Metal'},
    {'sym':'NTPC',       'id':'532555',  'sector':'Power'},
    {'sym':'HINDALCO',   'id':'500440',  'sector':'Metal'},
    {'sym':'POWERGRID',  'id':'532898',  'sector':'Power'},
]

STRATS = {
    'SCALP':       {'sl':0.30,'tgt':0.65,'rlo':30,'rhi':70,'conf':55},
    'MOMENTUM':    {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':58},
    'SWING':       {'sl':1.50,'tgt':3.50,'rlo':30,'rhi':70,'conf':60},
    'BREAKOUT':    {'sl':0.60,'tgt':1.80,'rlo':45,'rhi':55,'conf':65},
    'REVERSAL':    {'sl':0.70,'tgt':1.80,'rlo':25,'rhi':75,'conf':62},
    'AGGRESSIVE':  {'sl':0.50,'tgt':1.20,'rlo':35,'rhi':65,'conf':55},
    'CONSERVATIVE':{'sl':1.20,'tgt':3.00,'rlo':35,'rhi':65,'conf':68},
    'AI_AUTO':     {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':58},
}

STATE = {
    'running': False,
    'positions': {},
    'trades': deque(maxlen=100),
    'logs': deque(maxlen=500),
    'signals': [],
    'prices': {},
    'funds': 0.0,
    'last_scan': None,
    'last_price_update': None,
    'ai_analysis': '',
    'market_sentiment': 'NEUTRAL',
    'data_source': 'initializing',
    'token_status': 'unknown',
    'token_expiry': None,
    'error_count': 0,
    'stats': {
        'trades':0,'wins':0,'losses':0,
        'today_pnl':0.0,'total_pnl':0.0,
        'best_trade':0.0,'worst_trade':0.0,
        'streak':0,'max_streak':0,'today_trades':0,
    },
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTO TOKEN REFRESH — DHAN API KEY METHOD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_totp(secret):
    """Generate TOTP code from secret key"""
    try:
        # Clean secret
        secret = secret.upper().replace(' ', '')
        # Add padding
        padding = len(secret) % 8
        if padding: secret += '=' * (8 - padding)
        key = base64.b32decode(secret)
        # Time counter
        counter = int(time.time()) // 30
        msg = struct.pack('>Q', counter)
        # HMAC
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0f
        code = struct.unpack('>I', h[offset:offset+4])[0] & 0x7fffffff
        return str(code % 1000000).zfill(6)
    except Exception as e:
        add_log(f'TOTP error: {e}', 'WARNING')
        return None

def refresh_token_via_api():
    """
    Refresh Dhan token using API Key + Secret
    Dhan v2 API token generation
    """
    api_key = CFG.get('api_key', '')
    api_secret = CFG.get('api_secret', '')

    if not api_key or not api_secret:
        add_log('⚠️ API Key/Secret not set — cannot auto-refresh token', 'WARNING')
        return False

    try:
        add_log('🔄 Auto-refreshing Dhan token...', 'INFO')

        # Method 1: Dhan v2 token API
        payload = {
            'clientId': CFG['client_id'],
            'apiKey': api_key,
            'apiSecret': api_secret,
        }
        r = requests.post(
            'https://api.dhan.co/v2/token',
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=15
        )
        data = r.json()
        token = data.get('accessToken') or data.get('access_token') or data.get('token')

        if token:
            CFG['token'] = token
            STATE['token_status'] = 'auto_refreshed'
            STATE['token_expiry'] = datetime.now().strftime('%d %b %H:%M')
            add_log(f'✅ Token auto-refreshed successfully!', 'INFO')
            telegram('🔑 <b>Token auto-refreshed!</b> Bot continues trading.')
            return True
        else:
            add_log(f'Token refresh response: {str(data)[:150]}', 'WARNING')
            # Try Method 2
            return refresh_token_method2()

    except Exception as e:
        add_log(f'Token refresh error: {e}', 'WARNING')
        return refresh_token_method2()

def refresh_token_method2():
    """Method 2: Generate token via Dhan partner API"""
    try:
        api_key = CFG.get('api_key', '')
        api_secret = CFG.get('api_secret', '')

        # Dhan partner token endpoint
        r = requests.post(
            'https://dhanhq.co/api/v2/generateToken',
            json={
                'clientId': CFG['client_id'],
                'apiKey': api_key,
                'apiSecret': api_secret,
            },
            headers={'Content-Type': 'application/json'},
            timeout=15
        )
        data = r.json()
        token = (data.get('data') or {}).get('accessToken') or data.get('accessToken')

        if token:
            CFG['token'] = token
            STATE['token_status'] = 'auto_refreshed'
            add_log('✅ Token refreshed via method 2!', 'INFO')
            return True

        add_log(f'Method 2 response: {str(data)[:150]}', 'WARNING')
        return False
    except Exception as e:
        add_log(f'Method 2 error: {e}', 'WARNING')
        return False

def check_and_refresh_token():
    """Check token validity and refresh if needed"""
    if not CFG['token']:
        add_log('⚠️ No token — attempting auto-refresh...', 'WARNING')
        return refresh_token_via_api()

    # Test current token
    try:
        r = requests.get(f'{DHAN_API}/fundlimit',
            headers={'access-token': CFG['token'], 'client_id': CFG['client_id']},
            timeout=10)

        if r.status_code == 200:
            data = r.json()
            if data.get('availableBalance') is not None:
                STATE['token_status'] = 'valid'
                STATE['funds'] = float(data.get('availableBalance', 0))
                add_log(f'✅ Token valid | Funds: ₹{STATE["funds"]:,.0f}', 'INFO')
                return True

        # Token expired or invalid
        add_log('🔄 Token expired — auto-refreshing...', 'WARNING')
        return refresh_token_via_api()

    except Exception as e:
        add_log(f'Token check error: {e}', 'WARNING')
        return refresh_token_via_api()

def scheduled_token_refresh():
    """Run every day at 8:30 AM — refresh token before market opens"""
    add_log('⏰ Scheduled token refresh at 8:30 AM...', 'INFO')
    success = check_and_refresh_token()
    if success:
        add_log('✅ Daily token refresh done — Ready for trading!', 'INFO')
        telegram('🌅 <b>Good Morning!</b>\n✅ Token refreshed\n📊 Bot ready for trading\n⏰ Market opens at 9:15 AM')
    else:
        add_log('❌ Auto-refresh failed — Manual token needed!', 'ERROR')
        telegram('⚠️ <b>Token refresh failed!</b>\nPlease update token manually at:\nhttps://dhan-python-bot.onrender.com', urgent=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def add_log(msg, level='INFO'):
    now = datetime.now().strftime('%H:%M:%S')
    STATE['logs'].appendleft({'time':now,'msg':msg,'level':level})
    getattr(log, level.lower(), log.info)(msg)

def telegram(msg, urgent=False):
    if not CFG['tg_token'] or not CFG['tg_chat']: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{CFG['tg_token']}/sendMessage",
            json={'chat_id':CFG['tg_chat'],'text':('🚨 ' if urgent else '')+msg,'parse_mode':'HTML'},
            timeout=5)
    except: pass

def dhan_headers():
    return {
        'Content-Type': 'application/json',
        'access-token': CFG['token'],
        'client_id':    CFG['client_id'],
    }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MARKET TIMING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def market_open():
    n = datetime.now()
    if n.weekday() >= 5: return False
    return dtime(9,15) <= n.time() <= dtime(15,30)

def trading_time():
    return dtime(9,15) <= datetime.now().time() <= dtime(15,0)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PRICE ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def fetch_dhan_ltp():
    if not CFG['token'] or not CFG['client_id']: return False
    try:
        sec_ids = [w['id'] for w in WATCHLIST]
        r = requests.post(f"{DHAN_API}/v2/marketfeed/ltp",
            json={"NSE_EQ": sec_ids}, headers=dhan_headers(), timeout=10)
        data = r.json()
        nse = (data.get('data') or data).get('NSE_EQ', {})
        if not nse: nse = data.get('NSE_EQ', {})
        updated = 0
        for stock in WATCHLIST:
            sec = nse.get(stock['id'], {})
            price = sec.get('last_price') or sec.get('ltp') or sec.get('lastPrice')
            if price and float(price) > 0:
                prev = STATE['prices'].get(stock['sym'], {}).get('price', float(price))
                chg  = ((float(price)-prev)/prev*100) if prev else 0
                if stock['sym'] not in STATE['prices']:
                    STATE['prices'][stock['sym']] = {'closes':[],'volume':[]}
                STATE['prices'][stock['sym']].update({
                    'price':float(price),'prev':prev,'chg':round(chg,3),
                    'updated':datetime.now().strftime('%H:%M:%S'),'source':'DHAN_LTP',
                })
                STATE['prices'][stock['sym']]['closes'].append(float(price))
                if len(STATE['prices'][stock['sym']]['closes'])>100:
                    STATE['prices'][stock['sym']]['closes'].pop(0)
                updated += 1
        if updated > 0:
            STATE['data_source'] = f'Dhan LTP Real-Time ({updated}/{len(WATCHLIST)})'
            STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
            add_log(f'📡 Dhan LTP: {updated}/{len(WATCHLIST)} real-time prices', 'INFO')
            return True
        return False
    except Exception as e:
        add_log(f'LTP error: {e}', 'WARNING')
        return False

def fetch_yahoo():
    add_log('📡 Yahoo Finance fallback...', 'INFO')
    updated = 0
    for stock in WATCHLIST:
        try:
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{stock["sym"]}.NS?interval=1m&range=1d'
            r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
            d = r.json()['chart']['result'][0]
            price = d['meta']['regularMarketPrice']
            prev  = d['meta']['chartPreviousClose']
            closes= [x for x in d['indicators']['quote'][0].get('close',[]) if x]
            volume= [x for x in d['indicators']['quote'][0].get('volume',[]) if x]
            STATE['prices'][stock['sym']] = {
                'price':float(price),'prev':float(prev),
                'chg':round(((price-prev)/prev*100) if prev else 0,3),
                'closes':[float(c) for c in closes[-80:]],
                'volume':[float(v) for v in volume[-80:]],
                'updated':datetime.now().strftime('%H:%M:%S'),'source':'Yahoo(15min)',
            }
            updated += 1
        except: pass
        time.sleep(0.2)
    STATE['data_source'] = f'Yahoo Finance ({updated}/{len(WATCHLIST)}) 15min delayed'
    add_log(f'✅ Yahoo: {updated}/{len(WATCHLIST)} prices', 'INFO')

def fetch_all_prices():
    if market_open() and CFG['token']:
        if not fetch_dhan_ltp():
            fetch_yahoo()
    else:
        fetch_yahoo()
    # Update sentiment
    prices = STATE['prices']
    if prices:
        bull = sum(1 for p in prices.values() if p.get('chg',0)>0.1)
        bear = sum(1 for p in prices.values() if p.get('chg',0)<-0.1)
        total = len(prices)
        STATE['market_sentiment'] = 'BULLISH' if bull>total*0.65 else 'BEARISH' if bear>total*0.65 else 'NEUTRAL'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TECHNICAL ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def rsi(p,n=14):
    if len(p)<n+1: return 50.0
    a=np.array(p[-n*3:],dtype=float); d=np.diff(a)
    g=np.where(d>0,d,0); l=np.where(d<0,-d,0)
    ag=np.mean(g[:n]); al=np.mean(l[:n])
    for i in range(n,len(d)):
        ag=(ag*(n-1)+g[i])/n; al=(al*(n-1)+l[i])/n
    return round(100.0 if al==0 else 100-100/(1+ag/al),2)

def ema(p,n):
    if len(p)<n: return float(p[-1])
    a=np.array(p,dtype=float); k=2/(n+1)
    e=float(np.mean(a[:n]))
    for x in a[n:]: e=float(x)*k+e*(1-k)
    return round(e,2)

def bb(p,n=20):
    if len(p)<n: v=float(p[-1]); return round(v*1.02,2),round(v,2),round(v*0.98,2)
    sl=np.array(p[-n:],dtype=float); m=float(np.mean(sl)); s=float(np.std(sl))
    return round(m+2*s,2),round(m,2),round(m-2*s,2)

def macd(p):
    if len(p)<26: return 0,0,0
    m=ema(p,12)-ema(p,26); return round(m,4),round(m*0.9,4),round(m*0.1,4)

def stoch(p,n=14):
    if len(p)<n: return 50,50
    a=p[-n:]; lo=min(a); hi=max(a)
    if hi==lo: return 50,50
    k=((p[-1]-lo)/(hi-lo))*100
    return round(k,1),round(k*0.9,1)

def detect_pattern(p):
    if len(p)<5: return 'None'
    c=p[-5:]
    if c[-1]>c[-2] and c[-2]<c[-3]: return 'MORNING_STAR ⭐'
    if c[-1]<c[-2] and c[-2]>c[-3]: return 'EVENING_STAR 🌟'
    if all(c[i]>c[i-1] for i in range(1,5)): return 'UPTREND 📈'
    if all(c[i]<c[i-1] for i in range(1,5)): return 'DOWNTREND 📉'
    if abs(c[-1]-c[-2])/c[-2]<0.002: return 'DOJI ⚖️'
    return 'NEUTRAL'

def pick_strategy(prices):
    if len(prices)<20: return 'MOMENTUM'
    r=rsi(prices); mc,ms,mh=macd(prices)
    mom=(prices[-1]-prices[-5])/prices[-5]*100 if len(prices)>=5 else 0
    at=np.mean([abs(prices[i]-prices[i-1]) for i in range(1,min(15,len(prices)))])
    vol=at/prices[-1]*100 if prices[-1] else 1
    if vol>1.5: return 'BREAKOUT' if mh>0 else 'SCALP'
    if r<30 or r>70: return 'REVERSAL'
    if abs(mom)>2: return 'MOMENTUM'
    if vol<0.5: return 'CONSERVATIVE'
    return 'MOMENTUM'

def generate_signal(prices, strat_name=None):
    if strat_name is None: strat_name = CFG['strategy']
    if strat_name == 'AI_AUTO': strat_name = pick_strategy(prices)
    strat = STRATS.get(strat_name, STRATS['MOMENTUM'])
    if len(prices)<15: return 'HOLD',0,{},[],strat_name

    cur=prices[-1]
    r=rsi(prices); e9=ema(prices,9); e21=ema(prices,min(21,len(prices)))
    e50=ema(prices,min(50,len(prices))); bbu,bbm,bbl=bb(prices)
    mc,ms,mh=macd(prices); sk,sd=stoch(prices)
    vw=np.mean(prices[-20:]) if len(prices)>=20 else cur
    at=np.mean([abs(prices[i]-prices[i-1]) for i in range(1,min(15,len(prices)))])
    mom=(prices[-1]-prices[-5])/prices[-5]*100 if len(prices)>=5 else 0
    pat=detect_pattern(prices)
    sup=min(prices[-20:]) if len(prices)>=20 else cur*0.98
    res=max(prices[-20:]) if len(prices)>=20 else cur*1.02

    bull=0; bear=0; reasons=[]

    if r<strat['rlo']:        bull+=28; reasons.append(f'RSI Oversold({r:.0f})')
    elif r<45:                bull+=10
    if r>strat['rhi']:        bear+=28; reasons.append(f'RSI Overbought({r:.0f})')
    elif r>55:                bear+=10
    if e9>e21:                bull+=22; reasons.append('EMA9>21↑')
    else:                     bear+=22; reasons.append('EMA9<21↓')
    if cur>e50:               bull+=15; reasons.append('Above EMA50')
    else:                     bear+=15; reasons.append('Below EMA50')
    if cur<=bbl:              bull+=22; reasons.append('BB Lower🎯')
    if cur>=bbu:              bear+=22; reasons.append('BB Upper🎯')
    if mc>0 and mh>0:         bull+=18; reasons.append('MACD Bull↗')
    elif mc<0 and mh<0:       bear+=18; reasons.append('MACD Bear↘')
    if cur>vw*1.002:          bull+=12; reasons.append('Above VWAP')
    elif cur<vw*0.998:        bear+=12; reasons.append('Below VWAP')
    if sk<25:                 bull+=15; reasons.append('Stoch Oversold')
    if sk>75:                 bear+=15; reasons.append('Stoch Overbought')
    if mom>1.5:               bull+=12; reasons.append(f'Momentum+{mom:.1f}%')
    elif mom<-1.5:            bear+=12; reasons.append(f'Momentum{mom:.1f}%')
    if cur<=sup*1.008:        bull+=12; reasons.append('Near Support')
    if cur>=res*0.992:        bear+=12; reasons.append('Near Resistance')
    if 'MORNING_STAR' in pat or 'UPTREND' in pat:
        bull+=18; reasons.append(f'{pat}')
    if 'EVENING_STAR' in pat or 'DOWNTREND' in pat:
        bear+=18; reasons.append(f'{pat}')
    sent=STATE['market_sentiment']
    if sent=='BULLISH': bull+=8
    elif sent=='BEARISH': bear+=8

    total=bull+bear or 1
    conf=round(max(bull,bear)/total*100,1)
    inds={'rsi':r,'ema9':e9,'ema21':e21,'bbu':bbu,'bbm':bbm,'bbl':bbl,
          'macd':mc,'macd_hist':mh,'vwap':round(vw,2),'atr':round(at,2),
          'stoch':sk,'momentum':round(mom,2),'pattern':pat,
          'support':round(sup,2),'resistance':round(res,2)}

    if bull>bear and conf>strat['conf']: return 'BUY',conf,inds,reasons,strat_name
    if bear>bull and conf>strat['conf']: return 'SELL',conf,inds,reasons,strat_name
    return 'HOLD',conf,inds,reasons,strat_name

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DHAN ORDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def place_order(sym,sec_id,side,qty,otype='MARKET',price=0.0,trigger=0.0):
    if not CFG['token'] or not CFG['client_id']:
        add_log('❌ No token!','ERROR'); return None
    payload={
        'dhanClientId':CFG['client_id'],'transactionType':side,
        'exchangeSegment':'NSE_EQ','productType':'INTRADAY',
        'orderType':otype,'validity':'DAY','tradingSymbol':sym,
        'securityId':str(sec_id),'quantity':int(qty),
        'price':round(float(price),2),'triggerPrice':round(float(trigger),2),
        'disclosedQuantity':0,'afterMarketOrder':False,
        'amoTime':'OPEN','boProfitValue':0,'boStopLossValue':0,
    }
    for attempt in range(3):
        try:
            time.sleep(random.uniform(2,6))
            r=requests.post(f'{DHAN_API}/orders',json=payload,headers=dhan_headers(),timeout=10)
            try: data=r.json()
            except: data={'raw':r.text[:200]}
            oid=data.get('orderId') or (data.get('data') or {}).get('orderId')
            if oid:
                add_log(f'✅ ORDER: {side} {sym} x{qty} | #{oid}','INFO')
                STATE['error_count']=0; return oid
            else:
                # Check if token expired
                if 'token' in str(data).lower() or r.status_code==401:
                    add_log('🔄 Token expired — refreshing...','WARNING')
                    check_and_refresh_token()
                add_log(f'⚠️ {sym}: {str(data)[:150]}','WARNING')
                return None
        except requests.Timeout:
            time.sleep(3)
        except Exception as e:
            add_log(f'❌ Order error: {e}','ERROR')
            STATE['error_count']+=1; return None
    return None

def place_sl(sym,sec_id,side,qty,sl_price):
    lmt=sl_price*0.994 if side=='SELL' else sl_price*1.006
    return place_order(sym,sec_id,side,qty,'SL',round(lmt,2),round(sl_price,2))

def get_funds():
    try:
        r=requests.get(f'{DHAN_API}/fundlimit',headers=dhan_headers(),timeout=10)
        data=r.json()
        bal=float(data.get('availableBalance',0))
        STATE['funds']=bal
        add_log(f'💰 Funds: ₹{bal:,.0f}','INFO')
        return bal
    except Exception as e:
        add_log(f'Funds: {e}','WARNING'); return STATE['funds']

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POSITION MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def calc_qty(price,at,sl_pct):
    risk=CFG['capital']*CFG['risk_pct']/100
    sl_amt=price*sl_pct/100
    if sl_amt<=0: sl_amt=at or price*0.01
    return max(1,min(int(risk/sl_amt),int(CFG['capital']/price)))

def update_trailing(sym,cur):
    if not CFG['trailing_sl'] or sym not in STATE['positions']: return
    pos=STATE['positions'][sym]
    strat=STRATS.get(pos.get('strategy',CFG['strategy']),STRATS['MOMENTUM'])
    if pos['side']=='BUY':
        new_sl=cur*(1-strat['sl']/100)
        if new_sl>pos['sl']: pos['sl']=round(new_sl,2)
    else:
        new_sl=cur*(1+strat['sl']/100)
        if new_sl<pos['sl']: pos['sl']=round(new_sl,2)

def close_pos(sym,reason,exit_price=None):
    if sym not in STATE['positions']: return
    pos=STATE['positions'][sym]
    if exit_price is None:
        exit_price=STATE['prices'].get(sym,{}).get('price',pos['entry'])
    pnl=round((exit_price-pos['entry'])*pos['qty'] if pos['side']=='BUY'
              else (pos['entry']-exit_price)*pos['qty'],2)
    s=STATE['stats']
    s['today_pnl']=round(s['today_pnl']+pnl,2); s['total_pnl']=round(s['total_pnl']+pnl,2)
    s['trades']+=1; s['today_trades']+=1
    if pnl>0:
        s['wins']+=1; s['streak']=max(0,s.get('streak',0))+1
        s['max_streak']=max(s.get('max_streak',0),s['streak'])
        s['best_trade']=max(s.get('best_trade',0),pnl)
    else:
        s['losses']+=1; s['streak']=min(0,s.get('streak',0))-1
        s['worst_trade']=min(s.get('worst_trade',0),pnl)
    emoji='✅' if pnl>0 else '❌'
    add_log(f'{emoji} CLOSED {sym} | {reason} | ₹{pos["entry"]:.2f}→₹{exit_price:.2f} | PnL:₹{pnl:+.2f}','INFO')
    telegram(f'{emoji} <b>{sym} CLOSED</b>\n{reason}\nPnL: <b>₹{pnl:+.2f}</b>')
    STATE['trades'].appendleft({'sym':sym,'side':pos['side'],'qty':pos['qty'],
        'entry':pos['entry'],'exit':exit_price,'pnl':pnl,'reason':reason,
        'time':datetime.now().strftime('%H:%M'),'strategy':pos.get('strategy',CFG['strategy'])})
    exit_side='SELL' if pos['side']=='BUY' else 'BUY'
    time.sleep(1)
    place_order(sym,pos['secId'],exit_side,pos['qty'])
    del STATE['positions'][sym]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN SCAN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def scan():
    if not STATE['running']: return
    if not market_open():
        if not STATE['positions']:
            add_log('🔴 Market closed — Standby','INFO')
        return

    s=STATE['stats']
    if s['today_pnl']<=-CFG['max_loss']:
        add_log(f'🚨 MAX LOSS ₹{CFG["max_loss"]} — STOPPED!','WARNING')
        telegram(f'🚨 <b>MAX LOSS HIT!</b> ₹{abs(s["today_pnl"]):.0f}',urgent=True)
        STATE['running']=False; return
    if s['today_pnl']>=CFG['max_profit']:
        add_log(f'🎯 TARGET ₹{CFG["max_profit"]} — STOPPED!','INFO')
        telegram(f'🎯 <b>PROFIT TARGET!</b> ₹{s["today_pnl"]:.0f}')
        STATE['running']=False; return

    # Refresh LTP
    if market_open() and CFG['token']:
        fetch_dhan_ltp()

    add_log(f'🔍 Scan | {CFG["strategy"]} | {STATE["data_source"]} | Pos:{len(STATE["positions"])}/{CFG["max_trades"]} | PnL:₹{s["today_pnl"]:+.0f}','INFO')

    # Check positions
    for sym in list(STATE['positions'].keys()):
        pos=STATE['positions'][sym]
        cur=STATE['prices'].get(sym,{}).get('price',pos['entry'])
        if cur<=0: continue
        update_trailing(sym,cur)
        if pos['side']=='BUY':
            if cur<=pos['sl']:    close_pos(sym,'🛑 SL Hit',cur)
            elif cur>=pos['tgt']: close_pos(sym,'🎯 Target Hit',cur)
        else:
            if cur>=pos['sl']:    close_pos(sym,'🛑 SL Hit',cur)
            elif cur<=pos['tgt']: close_pos(sym,'🎯 Target Hit',cur)

    if not trading_time():
        add_log('⏰ New trades paused (after 3PM)','INFO'); return

    signals=[]
    for stock in WATCHLIST:
        sym=stock['sym']
        pd=STATE['prices'].get(sym,{})
        closes=pd.get('closes',[])
        price=pd.get('price',0)
        if not closes or price<=0: continue

        action,conf,inds,reasons,used=generate_signal(closes)
        signals.append({'sym':sym,'price':price,'chg':pd.get('chg',0),
            'action':action,'conf':conf,'reasons':reasons[:4],
            'rsi':inds.get('rsi',50),'macd':inds.get('macd',0),
            'pattern':inds.get('pattern','—'),'sector':stock.get('sector',''),
            'indicators':inds,'used_strategy':used,'source':pd.get('source','—')})

        if (action!='HOLD' and sym not in STATE['positions']
                and len(STATE['positions'])<CFG['max_trades']
                and conf>STRATS.get(used,STRATS['MOMENTUM'])['conf']):
            strat=STRATS.get(used,STRATS['MOMENTUM'])
            at=inds.get('atr',price*0.01)
            qty=calc_qty(price,at,strat['sl'])
            sl=round(price*(1-strat['sl']/100) if action=='BUY' else price*(1+strat['sl']/100),2)
            tgt=round(price*(1+strat['tgt']/100) if action=='BUY' else price*(1-strat['tgt']/100),2)
            rr=round(abs(tgt-price)/abs(price-sl),2) if price!=sl else 0

            add_log(f'🚀 {action} {sym} x{qty} @ ₹{price:.2f} | SL:₹{sl} Tgt:₹{tgt} RR:{rr} [{conf:.0f}%] ({used})','INFO')
            telegram(f'🚀 <b>{action} {sym}</b> x{qty} @ ₹{price:.2f}\nSL:₹{sl} | Tgt:₹{tgt} | RR:{rr}\nConf:{conf:.0f}% | {used}')

            oid=place_order(sym,stock['id'],action,qty)
            if oid:
                STATE['positions'][sym]={'sym':sym,'secId':stock['id'],'side':action,
                    'qty':qty,'entry':price,'sl':sl,'tgt':tgt,'conf':conf,'oid':oid,
                    'rr':rr,'strategy':used,'time':datetime.now().strftime('%H:%M')}
                time.sleep(2)
                sl_side='SELL' if action=='BUY' else 'BUY'
                threading.Thread(target=place_sl,args=(sym,stock['id'],sl_side,qty,sl),daemon=True).start()

    STATE['signals']=sorted(signals,key=lambda x:x['conf'],reverse=True)
    STATE['last_scan']=datetime.now().strftime('%H:%M:%S')

def squareoff_all():
    if not STATE['positions']: return
    add_log('⏰ 3:15PM Auto Square Off!','WARNING')
    telegram('⏰ <b>Auto Square Off 3:15PM</b>')
    for sym in list(STATE['positions'].keys()):
        close_pos(sym,'⏰ Auto Square Off 3:15PM')

def daily_reset():
    s=STATE['stats']
    s['today_pnl']=0.0; s['today_trades']=0
    s['wins']=0; s['losses']=0; s['trades']=0
    STATE['error_count']=0
    add_log('🔄 New trading day — Reset!','INFO')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AI ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_ai_analysis():
    if not CFG['openrouter']: return
    try:
        sigs=[s for s in STATE['signals'] if s['action']!='HOLD'][:5]
        sig_text=', '.join([f"{s['sym']}:{s['action']}({s['conf']:.0f}%)" for s in sigs])
        s=STATE['stats']
        r=requests.post('https://openrouter.ai/api/v1/chat/completions',
            headers={'Authorization':f'Bearer {CFG["openrouter"]}','Content-Type':'application/json'},
            json={'model':'anthropic/claude-3-haiku','messages':[
                {'role':'system','content':'Expert NSE trader. 3 line Hindi/Hinglish analysis.'},
                {'role':'user','content':f'Signals:{sig_text} PnL:₹{s["today_pnl"]:.0f} Sentiment:{STATE["market_sentiment"]}'}],
            'max_tokens':200},timeout=15)
        STATE['ai_analysis']=r.json()['choices'][0]['message']['content']
        add_log('🤖 AI analysis updated','INFO')
    except Exception as e:
        add_log(f'AI: {e}','WARNING')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLASK ROUTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhan Quantum v5.2</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',monospace;background:#030609;color:#d0e4f7;min-height:100vh}
.hdr{background:linear-gradient(90deg,#030609,#08101f);border-bottom:1px solid #0d1a2e;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;position:sticky;top:0;z-index:100}
.logo{font-size:14px;font-weight:800;color:#00d4ff;letter-spacing:2px}
.sub{font-size:8px;color:#4a6580;letter-spacing:1px}
.badges{display:flex;gap:5px;flex-wrap:wrap}
.bdg{padding:3px 9px;border-radius:20px;font-size:8px;font-weight:700;border:1px solid}
.token-bar{background:#05080f;border-bottom:1px solid #0d1a2e;padding:8px 14px}
.trow{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:5px}
.tlbl{font-size:8px;color:#4a6580;min-width:80px;letter-spacing:1px}
input,select{padding:5px 9px;background:#080d18;border:1px solid #0d1a2e;border-radius:5px;color:#d0e4f7;font-family:inherit;font-size:9px;outline:none}
input:focus,select:focus{border-color:#00d4ff}
.btn{padding:5px 12px;border:none;border-radius:5px;cursor:pointer;font-family:inherit;font-size:9px;font-weight:700;transition:all 0.2s}
.btn:hover{filter:brightness(1.2)}
.bg{background:linear-gradient(90deg,#005522,#00aa44);color:#fff}
.br{background:linear-gradient(90deg,#550011,#cc0033);color:#fff}
.bb{background:linear-gradient(90deg,#003388,#0066cc);color:#fff}
.bp{background:linear-gradient(90deg,#330055,#6600bb);color:#fff}
.tabs{display:flex;background:#05080f;border-bottom:1px solid #0d1a2e;overflow-x:auto;padding:0 8px}
.tab{padding:9px 12px;border:none;cursor:pointer;background:transparent;font-family:inherit;font-size:8px;font-weight:700;color:#4a6580;border-bottom:2px solid transparent;white-space:nowrap}
.tab.on{color:#00d4ff;border-bottom-color:#00d4ff;background:#080d18}
.content{padding:12px;max-width:1200px;margin:0 auto}
.tp{display:none}.tp.on{display:block}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-bottom:12px}
.stat{background:#080d18;border:1px solid #0d1a2e;border-radius:8px;padding:11px 12px}
.sl{font-size:7px;color:#4a6580;letter-spacing:1.5px;margin-bottom:3px;font-weight:700}
.sv{font-size:22px;font-weight:800}
.ss{font-size:8px;color:#4a6580;margin-top:2px}
.card{background:#080d18;border:1px solid #0d1a2e;border-radius:10px;padding:14px;margin-bottom:12px}
.ct{font-size:8px;color:#4a6580;letter-spacing:2px;margin-bottom:10px;font-weight:700;text-transform:uppercase}
.crow{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:9px}
th{padding:6px 8px;text-align:left;color:#4a6580;border-bottom:1px solid #0d1a2e;font-weight:700;font-size:8px}
td{padding:6px 8px;border-bottom:1px solid #05080f}
tr:hover td{background:#0c1422}
.buy{color:#00ff9d}.sell{color:#ff3060}.pos{color:#00ff9d}.neg{color:#ff3060}
.pill{padding:2px 7px;border-radius:4px;font-size:8px;font-weight:700}
.pb{background:#001a0d;color:#00ff9d;border:1px solid #00ff9d25}
.ps{background:#1a0008;color:#ff3060;border:1px solid #ff306025}
.ph{background:#0d1117;color:#4a6580;border:1px solid #0d1a2e}
.logbox{background:#020408;border-radius:6px;padding:10px;max-height:280px;overflow-y:auto;font-size:9px;border:1px solid #0d1a2e;line-height:1.8}
.li{color:#4a6580}.ls{color:#00ff9d}.le{color:#ff3060}.lw{color:#ffd000}
.prog{height:3px;background:#0d1a2e;border-radius:3px;overflow:hidden;margin-top:4px}
.pf{height:100%;border-radius:3px;transition:width 0.5s}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.15}}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px;vertical-align:middle}
.dg{background:#00ff9d;box-shadow:0 0 6px #00ff9d;animation:blink 1.5s infinite}
.dr{background:#ff3060}
.dy{background:#ffd000;animation:blink 1s infinite}
@media(max-width:600px){.stats{grid-template-columns:repeat(2,1fr)}}
</style></head>
<body>
<div class="hdr">
  <div><div class="logo">⚡ DHAN QUANTUM TRADER v5.2</div>
  <div class="sub">AUTO TOKEN REFRESH • REAL-TIME NSE • AI POWERED • 24/7</div></div>
  <div class="badges" id="hdrBdg"><span class="bdg" style="border-color:#4a6580;color:#4a6580">⏳ Loading...</span></div>
</div>

<div class="token-bar">
  <div class="trow">
    <span class="tlbl">🔑 DHAN TOKEN:</span>
    <input id="inpCid" placeholder="Client ID" style="width:100px">
    <input id="inpTok" type="password" placeholder="Access Token (optional — auto-refreshes)" style="flex:1;min-width:160px">
    <button class="btn bb" onclick="saveToken()">SAVE</button>
    <span id="tokStatus" style="font-size:8px;color:#4a6580"></span>
  </div>
  <div class="trow">
    <span class="tlbl">🔄 AUTO TOKEN:</span>
    <span id="autoStatus" style="font-size:9px;color:#00ff9d">Bot refreshes token automatically using API Key!</span>
    <button class="btn bp" onclick="manualRefresh()" style="font-size:8px">Force Refresh</button>
  </div>
</div>

<div class="tabs">
  <button class="tab on" onclick="sw('dash',this)">📊 DASHBOARD</button>
  <button class="tab" onclick="sw('signals',this)">🎯 SIGNALS</button>
  <button class="tab" onclick="sw('positions',this)">📂 POSITIONS</button>
  <button class="tab" onclick="sw('history',this)">📋 HISTORY</button>
  <button class="tab" onclick="sw('logs',this)">📝 LOGS</button>
</div>

<div class="content">
<div id="tab-dash" class="tp on">
  <div class="stats" id="statsGrid"></div>
  <div class="card">
    <div class="ct">BOT CONTROL</div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">
      <button class="btn bg" id="btnStart" onclick="botCmd('start')">▶ START BOT</button>
      <button class="btn br" id="btnStop" onclick="botCmd('stop')" style="display:none">⏹ STOP BOT</button>
      <button class="btn bb" onclick="doRefresh()">📡 Prices</button>
      <button class="btn bb" onclick="doFunds()">💰 Funds</button>
      <button class="btn br" onclick="doSq()">⚠️ Square Off</button>
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
      <select id="selStrat">
        <option value="MOMENTUM">Momentum (SL 0.8% | Tgt 2%)</option>
        <option value="SCALP">Scalping (SL 0.3% | Tgt 0.65%)</option>
        <option value="SWING">Swing (SL 1.5% | Tgt 3.5%)</option>
        <option value="BREAKOUT">Breakout (SL 0.6% | Tgt 1.8%)</option>
        <option value="REVERSAL">Reversal (SL 0.7% | Tgt 1.8%)</option>
        <option value="AI_AUTO">🤖 AI Auto Strategy</option>
        <option value="AGGRESSIVE">Aggressive</option>
        <option value="CONSERVATIVE">Conservative</option>
      </select>
      <input type="number" id="inpCap" value="5000" style="width:90px">
      <input type="number" id="inpMax" value="6" style="width:65px">
      <button class="btn bb" onclick="saveConfig()">SAVE</button>
    </div>
  </div>
  <div class="card" id="aiCard" style="border-color:#33005540;display:none">
    <div class="ct" style="color:#c084fc">🤖 AI MARKET ANALYSIS</div>
    <div id="aiTxt" style="font-size:9px;line-height:1.9;color:#d0b0ff;white-space:pre-wrap"></div>
  </div>
  <div class="card">
    <div class="crow">
      <div class="ct" style="margin-bottom:0">📡 LIVE NSE SCAN — <span id="srcLbl" style="color:#00d4ff;font-size:8px">--</span></div>
      <span style="font-size:8px;color:#4a6580" id="lastScan">--</span>
    </div>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>SYMBOL</th><th>LTP</th><th>CHG%</th><th>RSI</th><th>PATTERN</th><th>SIGNAL</th><th>CONF%</th><th>STRATEGY</th></tr></thead>
      <tbody id="scanTbl"><tr><td colspan="8" style="text-align:center;color:#4a6580;padding:20px">Bot start karein...</td></tr></tbody>
    </table></div>
  </div>
</div>

<div id="tab-signals" class="tp">
  <div id="sigCards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px">
    <div style="text-align:center;color:#4a6580;padding:40px;grid-column:1/-1">Bot start karein</div>
  </div>
</div>

<div id="tab-positions" class="tp">
  <div style="display:flex;justify-content:space-between;margin-bottom:10px">
    <span style="font-size:10px;color:#4a6580">Open Positions</span>
    <button class="btn br" onclick="doSq()" style="font-size:8px">Close All</button>
  </div>
  <div id="posContainer"><div style="text-align:center;color:#4a6580;padding:40px">No positions</div></div>
</div>

<div id="tab-history" class="tp">
  <div class="card"><div class="ct">TRADE HISTORY</div>
    <div style="overflow-x:auto"><table>
      <thead><tr><th>TIME</th><th>SYM</th><th>SIDE</th><th>QTY</th><th>ENTRY</th><th>EXIT</th><th>P&L</th><th>STRATEGY</th><th>REASON</th></tr></thead>
      <tbody id="histTbl"><tr><td colspan="9" style="text-align:center;color:#4a6580;padding:15px">No trades</td></tr></tbody>
    </table></div>
  </div>
</div>

<div id="tab-logs" class="tp">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <span style="font-size:8px;color:#4a6580">Server logs</span>
    <button class="btn" onclick="document.getElementById('logBox').innerHTML=''" style="background:#080d18;border:1px solid #0d1a2e;color:#4a6580;font-size:8px">CLEAR</button>
  </div>
  <div class="logbox" id="logBox"></div>
</div>
</div>

<script>
function sw(id,btn){
  document.querySelectorAll('.tp').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.getElementById('tab-'+id).classList.add('on');
  if(btn) btn.classList.add('on');
}

function isMarketOpen(){
  const n=new Date();if(n.getDay()===0||n.getDay()===6)return false;
  const t=n.getHours()*60+n.getMinutes();return t>=555&&t<=930;
}

async function refresh(){
  try{
    const d=await(await fetch('/api/state')).json();
    // Badges
    const mo=isMarketOpen();
    document.getElementById('hdrBdg').innerHTML=`
      <span class="bdg" style="border-color:${d.token_ok?'#00ff9d':'#ff3060'};color:${d.token_ok?'#00ff9d':'#ff3060'}">${d.token_ok?'🔑 TOKEN OK':'🔴 NO TOKEN'}</span>
      <span class="bdg" style="border-color:${d.running?'#00ff9d':'#4a6580'};color:${d.running?'#00ff9d':'#4a6580'}"><span class="dot ${d.running?'dg':'dr'}"></span>${d.running?'LIVE':'IDLE'}</span>
      <span class="bdg" style="border-color:${mo?'#00ff9d':'#ff3060'};color:${mo?'#00ff9d':'#ff3060'}">${mo?'🟢 OPEN':'🔴 CLOSED'}</span>
      <span class="bdg" style="border-color:#ffd000;color:#ffd000">💰 ₹${Math.floor(d.funds||0).toLocaleString('en-IN')}</span>
      <span class="bdg" style="border-color:${d.sentiment==='BULLISH'?'#00ff9d':d.sentiment==='BEARISH'?'#ff3060':'#ffd000'};color:${d.sentiment==='BULLISH'?'#00ff9d':d.sentiment==='BEARISH'?'#ff3060':'#ffd000'}">${d.sentiment}</span>
    `;
    document.getElementById('tokStatus').textContent=`Token: ${d.token_status||'—'} | Auto-refresh: ${d.api_key_set?'✅ ON':'⚠️ Set API Key'}`;
    document.getElementById('btnStart').style.display=d.running?'none':'inline-block';
    document.getElementById('btnStop').style.display=d.running?'inline-block':'none';

    // Stats
    const s=d.stats; const wr=s.trades>0?((s.wins/s.trades)*100).toFixed(0):0;
    document.getElementById('statsGrid').innerHTML=[
      {l:'TODAY P&L',v:`₹${(s.today_pnl||0).toFixed(0)}`,c:s.today_pnl>=0?'#00ff9d':'#ff3060',ss:`${s.today_trades||0} trades`},
      {l:'TOTAL P&L',v:`₹${(s.total_pnl||0).toFixed(0)}`,c:s.total_pnl>=0?'#00ff9d':'#ff3060',ss:'All time'},
      {l:'WIN RATE',v:`${wr}%`,c:'#c084fc',ss:`W:${s.wins||0} L:${s.losses||0}`},
      {l:'OPEN POS',v:Object.keys(d.positions||{}).length,c:'#00d4ff',ss:`Max:${d.max_trades||6}`},
      {l:'BEST TRADE',v:`₹${(s.best_trade||0).toFixed(0)}`,c:'#00ff9d',ss:'Single'},
      {l:'WORST TRADE',v:`₹${(s.worst_trade||0).toFixed(0)}`,c:'#ff3060',ss:'Single'},
      {l:'STREAK',v:s.streak||0,c:(s.streak||0)>=0?'#00ff9d':'#ff3060',ss:`Best:${s.max_streak||0}`},
      {l:'DATA SOURCE',v:d.data_source?.includes('Dhan')?'🟢 LIVE':'🟡 DELAYED',c:d.data_source?.includes('Dhan')?'#00ff9d':'#ffd000',ss:d.last_price_update||'—'},
    ].map(x=>`<div class="stat"><div class="sl">${x.l}</div><div class="sv" style="color:${x.c}">${x.v}</div><div class="ss">${x.ss}</div></div>`).join('');

    // Scan table
    if(d.signals&&d.signals.length){
      document.getElementById('lastScan').textContent='Last: '+(d.last_scan||'--');
      document.getElementById('srcLbl').textContent=d.data_source||'--';
      document.getElementById('scanTbl').innerHTML=d.signals.map(s=>`<tr>
        <td style="font-weight:700">${s.sym} <span style="font-size:7px;color:#4a6580">${s.sector||''}</span></td>
        <td style="color:#ffd000">₹${s.price.toFixed(2)}</td>
        <td style="color:${s.chg>=0?'#00ff9d':'#ff3060'}">${s.chg>=0?'+':''}${s.chg.toFixed(2)}%</td>
        <td style="color:#c084fc">${(s.rsi||50).toFixed(0)}</td>
        <td style="font-size:8px;color:#fb923c">${s.pattern||'—'}</td>
        <td><span class="pill ${s.action==='BUY'?'pb':s.action==='SELL'?'ps':'ph'}">${s.action}</span></td>
        <td style="color:#00d4ff">${s.conf.toFixed(0)}%</td>
        <td style="font-size:8px;color:#c084fc">${s.used_strategy||'—'}</td>
      </tr>`).join('');
    }

    // Signals cards
    const buysel=(d.signals||[]).filter(s=>s.action!=='HOLD');
    document.getElementById('sigCards').innerHTML=buysel.length?buysel.map(s=>`
      <div class="card" style="border-color:${s.action==='BUY'?'#00ff9d20':'#ff306020'}">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px">
          <b style="font-size:13px">${s.sym}</b>
          <span class="pill ${s.action==='BUY'?'pb':'ps'}" style="font-size:10px">${s.action==='BUY'?'🟢 BUY':'🔴 SELL'}</span>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;font-size:9px;color:#4a6580;margin-bottom:8px">
          <span>₹${s.price.toFixed(2)}</span>
          <span style="color:${s.chg>=0?'#00ff9d':'#ff3060'}">${s.chg>=0?'+':''}${s.chg.toFixed(2)}%</span>
          <span>RSI:<b style="color:#c084fc">${(s.rsi||50).toFixed(0)}</b></span>
          <span>Conf:<b style="color:#00d4ff">${s.conf.toFixed(0)}%</b></span>
          <span>Pattern:<b style="color:#fb923c">${s.pattern||'—'}</b></span>
          <span>Strategy:<b style="color:#c084fc">${s.used_strategy||'—'}</b></span>
        </div>
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          ${(s.reasons||[]).map(r=>`<span style="padding:1px 5px;border-radius:3px;font-size:7px;background:#0d1117;color:#4a6580">${r}</span>`).join('')}
        </div>
      </div>`).join(''):'<div style="text-align:center;color:#4a6580;padding:30px;grid-column:1/-1">Koi strong signal nahi abhi</div>';

    // Positions
    const pos=d.positions||{};const prices=d.prices||{};
    document.getElementById('posContainer').innerHTML=Object.keys(pos).length?
      Object.values(pos).map(p=>{
        const cur=(prices[p.sym]||{}).price||p.entry;
        const pnl=p.side==='BUY'?(cur-p.entry)*p.qty:(p.entry-cur)*p.qty;
        const pct=((cur-p.entry)/p.entry*100*(p.side==='BUY'?1:-1));
        return `<div class="card" style="border-color:${pnl>=0?'#00ff9d20':'#ff306020'}">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <b style="font-size:13px">${p.sym}</b>
            <b style="color:${pnl>=0?'#00ff9d':'#ff3060'}">₹${pnl.toFixed(2)} (${pct.toFixed(2)}%)</b>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap;font-size:9px;color:#4a6580">
            <span>Side:<b class="${p.side==='BUY'?'buy':'sell'}">${p.side}</b></span>
            <span>Qty:<b>${p.qty}</b></span>
            <span>Entry:<b style="color:#ffd000">₹${p.entry.toFixed(2)}</b></span>
            <span>LTP:<b style="color:#00d4ff">₹${cur.toFixed(2)}</b></span>
            <span>SL:<b class="neg">₹${p.sl.toFixed(2)}</b></span>
            <span>Tgt:<b class="pos">₹${p.tgt.toFixed(2)}</b></span>
          </div>
          <div class="prog"><div class="pf" style="width:${Math.min(Math.abs(pct)*15,100)}%;background:${pnl>=0?'#00ff9d':'#ff3060'}"></div></div>
        </div>`;}).join(''):
      '<div style="text-align:center;color:#4a6580;padding:40px">No open positions</div>';

    // History
    if(d.trades&&d.trades.length){
      document.getElementById('histTbl').innerHTML=d.trades.slice(0,30).map(t=>`<tr>
        <td style="color:#4a6580">${t.time}</td>
        <td style="font-weight:700">${t.sym}</td>
        <td class="${t.side==='BUY'?'buy':'sell'}">${t.side}</td>
        <td>${t.qty}</td>
        <td style="color:#ffd000">₹${t.entry.toFixed(2)}</td>
        <td style="color:#00d4ff">₹${t.exit.toFixed(2)}</td>
        <td style="font-weight:700;color:${t.pnl>=0?'#00ff9d':'#ff3060'}">₹${t.pnl.toFixed(2)}</td>
        <td style="font-size:8px;color:#c084fc">${t.strategy||'—'}</td>
        <td style="font-size:8px;color:#4a6580">${t.reason}</td>
      </tr>`).join('');
    }

    // Logs
    if(d.logs&&d.logs.length){
      document.getElementById('logBox').innerHTML=d.logs.slice(0,60).map(l=>`
        <div class="l${l.level==='ERROR'?'e':l.level==='WARNING'?'w':l.level==='INFO'?'i':'i'}">[${l.time}] ${l.msg}</div>`).join('');
    }

    // AI
    if(d.ai_analysis){
      document.getElementById('aiCard').style.display='block';
      document.getElementById('aiTxt').textContent=d.ai_analysis;
    }
  }catch(e){}
}

async function botCmd(a){
  const b={strategy:document.getElementById('selStrat').value,capital:parseInt(document.getElementById('inpCap').value)||5000,max_trades:parseInt(document.getElementById('inpMax').value)||6};
  await fetch('/api/bot/'+a,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  refresh();
}
async function saveConfig(){await botCmd('config');alert('Saved!');}
async function doRefresh(){await fetch('/api/prices/refresh',{method:'POST'});refresh();}
async function doFunds(){await fetch('/api/funds',{method:'POST'});setTimeout(refresh,2000);}
async function doSq(){if(!confirm('Square off all?'))return;await fetch('/api/squareoff',{method:'POST'});refresh();}
async function manualRefresh(){await fetch('/api/token/refresh',{method:'POST'});setTimeout(refresh,3000);}
async function saveToken(){
  const c=document.getElementById('inpCid').value.trim();
  const t=document.getElementById('inpTok').value.trim();
  if(!c){alert('Client ID required!');return;}
  await fetch('/api/token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:c,token:t})});
  document.getElementById('tokStatus').textContent='Saved!';
  refresh();
}
refresh();setInterval(refresh,5000);
</script>
</body></html>"""

@app.route('/')
def index(): return render_template_string(DASHBOARD_HTML)

@app.route('/api/state')
def api_state():
    return jsonify({
        'running':    STATE['running'],
        'token_ok':   bool(CFG['token'] and CFG['client_id']),
        'token_status': STATE['token_status'],
        'api_key_set':  bool(CFG['api_key'] and CFG['api_secret']),
        'funds':      STATE['funds'],
        'stats':      STATE['stats'],
        'positions':  STATE['positions'],
        'trades':     list(STATE['trades'])[:30],
        'logs':       list(STATE['logs'])[:80],
        'signals':    STATE['signals'],
        'prices':     {k:{kk:vv for kk,vv in v.items() if kk not in ['closes','volume']} for k,v in STATE['prices'].items()},
        'last_scan':  STATE['last_scan'],
        'ai_analysis':STATE['ai_analysis'],
        'sentiment':  STATE['market_sentiment'],
        'max_trades': CFG['max_trades'],
        'max_loss':   CFG['max_loss'],
        'max_profit': CFG['max_profit'],
        'strategy':   CFG['strategy'],
        'error_count':STATE['error_count'],
        'data_source':STATE['data_source'],
        'last_price_update': STATE['last_price_update'],
    })

@app.route('/api/bot/<action>', methods=['POST'])
def api_bot(action):
    data=request.json or {}
    if action in ('start','config'):
        if data.get('strategy'):   CFG['strategy']   = data['strategy']
        if data.get('capital'):    CFG['capital']     = int(data['capital'])
        if data.get('max_trades'): CFG['max_trades']  = int(data['max_trades'])
    if action=='start':
        STATE['running']=True
        add_log(f'🤖 BOT STARTED | {CFG["strategy"]} | ₹{CFG["capital"]} | Max:{CFG["max_trades"]}','INFO')
        telegram(f'🤖 <b>Dhan Quantum v5.2 STARTED!</b>\nStrategy: {CFG["strategy"]}\nCapital: ₹{CFG["capital"]}\nAuto Token: {"✅" if CFG["api_key"] else "⚠️ Manual"}')
        threading.Thread(target=fetch_all_prices,daemon=True).start()
        threading.Thread(target=scan,daemon=True).start()
    elif action=='stop':
        STATE['running']=False
        add_log('⏹ Bot stopped','WARNING')
        telegram('⏹ Bot stopped.')
    return jsonify({'ok':True})

@app.route('/api/token', methods=['POST'])
def api_token():
    data=request.json or {}
    if data.get('token'):     CFG['token']     = data['token']
    if data.get('client_id'): CFG['client_id'] = data['client_id']
    STATE['token_status'] = 'manually_set'
    add_log(f'🔑 Token updated manually','INFO')
    threading.Thread(target=get_funds,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/token/refresh', methods=['POST'])
def api_token_refresh():
    threading.Thread(target=check_and_refresh_token,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/prices/refresh', methods=['POST'])
def api_prices():
    threading.Thread(target=fetch_all_prices,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/funds', methods=['POST'])
def api_funds():
    threading.Thread(target=get_funds,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/squareoff', methods=['POST'])
def api_sq():
    threading.Thread(target=squareoff_all,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/risk', methods=['POST'])
def api_risk():
    data=request.json or {}
    if data.get('max_loss'):   CFG['max_loss']   = int(data['max_loss'])
    if data.get('max_profit'): CFG['max_profit'] = int(data['max_profit'])
    if data.get('risk_pct'):   CFG['risk_pct']   = float(data['risk_pct'])
    if data.get('max_trades'): CFG['max_trades'] = int(data['max_trades'])
    return jsonify({'ok':True})

@app.route('/health')
def health():
    return jsonify({'status':'ok','version':'5.2-quantum','time':datetime.now().isoformat(),
                   'running':STATE['running'],'token_status':STATE['token_status']})

def run_scheduler():
    # Token refresh at 8:30 AM every day
    schedule.every().day.at('08:30').do(scheduled_token_refresh)
    schedule.every().day.at('09:00').do(daily_reset)
    schedule.every().day.at('09:05').do(lambda: threading.Thread(target=get_funds,daemon=True).start())
    schedule.every().day.at('09:10').do(lambda: threading.Thread(target=fetch_all_prices,daemon=True).start())
    schedule.every().day.at('15:15').do(squareoff_all)
    schedule.every(1).minutes.do(lambda: threading.Thread(target=scan,daemon=True).start() if STATE['running'] else None)
    schedule.every(1).minutes.do(lambda: threading.Thread(target=fetch_dhan_ltp,daemon=True).start() if market_open() and CFG['token'] else None)
    schedule.every(5).minutes.do(lambda: threading.Thread(target=fetch_all_prices,daemon=True).start())
    schedule.every(15).minutes.do(lambda: threading.Thread(target=get_ai_analysis,daemon=True).start())
    # Check token every 6 hours
    schedule.every(6).hours.do(lambda: threading.Thread(target=check_and_refresh_token,daemon=True).start())
    add_log('⏱️ Scheduler: Token@8:30 | Scan@1min | LTP@1min | Prices@5min | AI@15min','INFO')
    while True:
        try: schedule.run_pending()
        except Exception as e: add_log(f'Scheduler: {e}','WARNING')
        time.sleep(15)

if __name__ == '__main__':
    log.info('━'*55)
    log.info('  DHAN QUANTUM TRADER v5.2 — AUTO TOKEN REFRESH')
    log.info('  Real-time NSE | 8 Strategies | AI Analysis')
    log.info('  Built on Mobile 📱 — Made in India 🇮🇳')
    log.info('━'*55)

    if CFG['api_key'] and CFG['api_secret']:
        log.info(f'✅ API Key found — Auto token refresh ENABLED!')
        threading.Thread(target=check_and_refresh_token,daemon=True).start()
    elif CFG['token']:
        log.info(f'✅ Manual token found')
        STATE['token_status'] = 'manual'
    else:
        log.warning('⚠️ No token — Set DHAN_TOKEN or DHAN_API_KEY+DHAN_API_SECRET')

    if CFG['client_id']:
        threading.Thread(target=fetch_all_prices,daemon=True).start()

    add_log('🚀 Dhan Quantum Trader v5.2 STARTED!','INFO')
    add_log(f'🔑 Auto Token: {"✅ ENABLED" if CFG["api_key"] else "⚠️ Manual mode"}','INFO')
    add_log('📡 Data: Dhan LTP (real-time) + Yahoo (fallback)','INFO')

    threading.Thread(target=run_scheduler,daemon=True).start()
    PORT=int(os.environ.get('PORT',5000))
    log.info(f'🌐 Dashboard: http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0',port=PORT,debug=False,threaded=True)
