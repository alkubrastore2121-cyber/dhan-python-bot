#!/usr/bin/env python3
import subprocess
"""
Dhan Quantum Trader v7.0
"""
import os, time, json, logging, threading, random
import requests, schedule, numpy as np
from datetime import datetime, time as dtime, timedelta
from collections import deque
from flask import Flask, jsonify, request, render_template_string

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('DhanQ7')

CFG = {
    'client_id':  os.environ.get('DHAN_CLIENT_ID', ''),
    'token':      os.environ.get('DHAN_TOKEN', ''),
    'capital':    int(os.environ.get('CAPITAL', '5000')),
    'max_trades': int(os.environ.get('MAX_TRADES', '6')),
    'strategy':   os.environ.get('STRATEGY', 'MOMENTUM'),
    'max_loss':   int(os.environ.get('MAX_LOSS', '2000')),
    'max_profit': int(os.environ.get('MAX_PROFIT', '5000')),
    'tg_token':   os.environ.get('TELEGRAM_TOKEN', ''),
    'tg_chat':    os.environ.get('TELEGRAM_CHAT', ''),
    'openrouter': os.environ.get('OPENROUTER_KEY', ''),
    'risk_pct':   float(os.environ.get('RISK_PCT', '1.5')),
    'trailing_sl': True,
    'trailing_pct': float(os.environ.get('TRAILING_PCT', '4.0')),  # 4% trail default
    'min_profit_lock': float(os.environ.get('MIN_PROFIT_LOCK', '1.5')),  # 1.5% min profit before trailing activates
    'use_fixed_target': False,  # False = trailing only, True = fixed target
    'token_set_at': None,
}

DHAN_API = 'https://api.dhan.co/v2'
app = Flask(__name__)

WATCHLIST = [
    {'sym':'RELIANCE','id':'500325','sector':'Energy'},
    {'sym':'TCS','id':'532540','sector':'IT'},
    {'sym':'HDFCBANK','id':'500180','sector':'Banking'},
    {'sym':'INFY','id':'500209','sector':'IT'},
    {'sym':'ICICIBANK','id':'532174','sector':'Banking'},
    {'sym':'SBIN','id':'500112','sector':'Banking'},
    {'sym':'AXISBANK','id':'532215','sector':'Banking'},
    {'sym':'WIPRO','id':'507685','sector':'IT'},
    {'sym':'TATAMOTORS','id':'500570','sector':'Auto'},
    {'sym':'BAJFINANCE','id':'500034','sector':'NBFC'},
    {'sym':'ADANIENT','id':'512599','sector':'Infra'},
    {'sym':'KOTAKBANK','id':'500247','sector':'Banking'},
    {'sym':'MARUTI','id':'532500','sector':'Auto'},
    {'sym':'BHARTIARTL','id':'532454','sector':'Telecom'},
    {'sym':'SUNPHARMA','id':'524715','sector':'Pharma'},
    {'sym':'TATASTEEL','id':'500470','sector':'Metal'},
    {'sym':'NTPC','id':'532555','sector':'Power'},
    {'sym':'HINDALCO','id':'500440','sector':'Metal'},
    {'sym':'POWERGRID','id':'532898','sector':'Power'},
    {'sym':'LTIM','id':'540005','sector':'IT'},
]

STRATS = {
    'MOMENTUM':     {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':58},
    'SCALE':        {'sl':0.30,'tgt':0.65,'rlo':30,'rhi':70,'conf':55},
    'SWING':        {'sl':1.50,'tgt':3.00,'rlo':30,'rhi':70,'conf':60},
    'BREAKOUT':     {'sl':0.60,'tgt':1.80,'rlo':45,'rhi':55,'conf':65},
    'REVERSAL':     {'sl':0.70,'tgt':1.80,'rlo':25,'rhi':75,'conf':62},
    'AGGRESSIVE':   {'sl':0.50,'tgt':1.20,'rlo':35,'rhi':65,'conf':55},
    'CONSERVATIVE': {'sl':1.20,'tgt':3.00,'rlo':35,'rhi':65,'conf':68},
    'AI_AUTO':      {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':58},
}

STATE = {
    'running':False,'positions':{},'trades':deque(maxlen=100),
    'logs':deque(maxlen=500),'signals':[],'prices':{},
    'funds':0.0,'last_scan':None,'last_price_update':None,
    'ai_analysis':'','market_sentiment':'NEUTRAL',
    'data_source':'waiting','token_status':'not_set','error_count':0,
    'stats':{'trades':0,'wins':0,'losses':0,'today_pnl':0.0,'total_pnl':0.0,
             'best_trade':0.0,'worst_trade':0.0,'streak':0,'max_streak':0,'today_trades':0},
}

ANGEL_TOKENS = {
    'RELIANCE':'2885','TCS':'11536','HDFCBANK':'1333','INFY':'1594',
    'ICICIBANK':'4963','HINDUNILVR':'1394','SBIN':'3045','BHARTIARTL':'10604',
    'ITC':'1660','KOTAKBANK':'1922','AXISBANK':'5900','LT':'11483',
    'WIPRO':'3787','MARUTI':'10999','SUNPHARMA':'3351','TITAN':'3506',
    'BAJFINANCE':'317','ASIANPAINT':'236','NESTLEIND':'17963','ULTRACEMCO':'2663',
    'TATAMOTORS':'3456','ADANIENT':'25','TATASTEEL':'3499','NTPC':'11630',
    'HINDALCO':'1363','POWERGRID':'14977','LTIM':'17818',
}

ANGEL_OBJ = [None]

def add_log(msg, level='INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    STATE['logs'].appendleft({'time':ts,'msg':msg,'level':level})
    if level == 'ERROR': log.error(msg)
    elif level == 'WARNING': log.warning(msg)
    else: log.info(msg)

def telegram(msg, urgent=False):
    if not CFG['tg_token'] or not CFG['tg_chat']: return
    try:
        requests.post(f'https://api.telegram.org/bot{CFG["tg_token"]}/sendMessage',
            json={'chat_id':CFG['tg_chat'],'text':msg,'parse_mode':'HTML'}, timeout=5)
    except: pass

def dhan_headers():
    return {'Content-Type':'application/json','access-token':CFG['token'],'client-id':CFG['client_id']}

def market_open():
    now = datetime.now()
    if now.weekday() >= 5: return False
    t = now.time()
    return dtime(9,15) <= t <= dtime(15,30)

def trading_time():
    now = datetime.now()
    if now.weekday() >= 5: return False
    t = now.time()
    return dtime(9,20) <= t <= dtime(15,15)

def token_expires_in_str():
    if not CFG['token_set_at']: return 'Not set'
    exp = CFG['token_set_at'] + timedelta(hours=24)
    rem = exp - datetime.now()
    if rem.total_seconds() <= 0: return 'EXPIRED'
    h,m = divmod(int(rem.total_seconds())//60, 60)
    return f'{h}h {m}m'

def check_token():
    if not CFG['token'] or not CFG['client_id']:
        STATE['token_status'] = 'missing'; return False
    if CFG['token_set_at']:
        if datetime.now() - CFG['token_set_at'] > timedelta(hours=23,minutes=30):
            STATE['token_status'] = 'expired'; return False
    try:
        r = requests.get(f'{DHAN_API}/fundlimit', headers=dhan_headers(), timeout=5)
        if r.status_code == 401:
            STATE['token_status'] = 'expired'; return False
        STATE['token_status'] = 'active'; return True
    except:
        STATE['token_status'] = 'error'; return False

def angel_login():
    try:
        import pyotp
        from SmartApi import SmartConnect
        totp = pyotp.TOTP('EKC5HV6KSDXLMRM3TOJVY5L6AY').now()
        obj = SmartConnect(api_key='qbbPC3Ye')
        obj.generateSession('AABU276235', '2121', totp)
        ANGEL_OBJ[0] = obj
        add_log('Angel One login OK')
        return True
    except Exception as e:
        add_log(f'Angel login error: {e}')
        return False

def fetch_dhan_ltp():
    # Angel One primary (free real-time data)
    try:
        if ANGEL_OBJ[0] is None:
            angel_login()
        if ANGEL_OBJ[0] is not None:
            upd = 0
            for w in WATCHLIST:
                try:
                    angel_id = ANGEL_TOKENS.get(w['sym'], w['id'])
                    resp = ANGEL_OBJ[0].ltpData('NSE', w['sym'], angel_id)
                    if resp and resp.get('status') and resp.get('data'):
                        p = float(resp['data'].get('ltp', 0))
                        if p > 0:
                            prev = STATE['prices'].get(w['sym'],{}).get('price', float(p))
                            if w['sym'] not in STATE['prices']:
                                STATE['prices'][w['sym']] = {'closes':[],'volume':[]}
                            STATE['prices'][w['sym']].update({
                                'price':float(p),'prev':prev,
                                'chg':round(((float(p)-prev)/prev*100) if prev else 0,3),
                                'updated':datetime.now().strftime('%H:%M:%S'),
                                'source':'Angel OK'
                            })
                            STATE['prices'][w['sym']]['closes'].append(float(p))
                            if len(STATE['prices'][w['sym']]['closes']) > 100:
                                STATE['prices'][w['sym']]['closes'].pop(0)
                            upd += 1
                except Exception:
                    pass
            if upd > 0:
                bull = sum(1 for p in STATE['prices'].values() if p.get('chg',0)>0.1)
                bear = sum(1 for p in STATE['prices'].values() if p.get('chg',0)<-0.1)
                t = len(STATE['prices'])
                STATE['market_sentiment'] = 'BULLISH' if bull>t*0.65 else 'BEARISH' if bear>t*0.65 else 'NEUTRAL'
                STATE['data_source'] = f'Angel LIVE({upd}/{len(WATCHLIST)}) {datetime.now().strftime("%H:%M:%S")}'
                STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
                return True
    except Exception as ae:
        add_log(f'Angel One failed: {ae}, trying Dhan...','WARNING')
        ANGEL_OBJ[0] = None

    # Fallback: Dhan API
    if not CFG['token'] or not CFG['client_id']:
        STATE['data_source'] = 'No token'; return False
    try:
        r = requests.post(f'{DHAN_API}/marketfeed/ltp',
            json={'NSE_EQ':[w['id'] for w in WATCHLIST]},
            headers=dhan_headers(), timeout=10)
        if r.status_code == 401:
            STATE['token_status'] = 'expired'
            STATE['data_source'] = 'Token expired'
            add_log('Token expired!','WARNING'); return False
        d = r.json()
        nse = d.get('data',d).get('NSE_EQ',{})
        upd = 0
        for w in WATCHLIST:
            sec = nse.get(w['id'],{})
            p = sec.get('last_price') or sec.get('ltp') or sec.get('lastPrice')
            if p and float(p) > 0:
                prev = STATE['prices'].get(w['sym'],{}).get('price',float(p))
                if w['sym'] not in STATE['prices']:
                    STATE['prices'][w['sym']] = {'closes':[],'volume':[]}
                STATE['prices'][w['sym']].update({
                    'price':float(p),'prev':prev,
                    'chg':round(((float(p)-prev)/prev*100) if prev else 0,3),
                    'updated':datetime.now().strftime('%H:%M:%S'),
                    'source':'Dhan FB'
                })
                STATE['prices'][w['sym']]['closes'].append(float(p))
                if len(STATE['prices'][w['sym']]['closes']) > 100:
                    STATE['prices'][w['sym']]['closes'].pop(0)
                upd += 1
        if upd > 0:
            bull = sum(1 for p in STATE['prices'].values() if p.get('chg',0)>0.1)
            bear = sum(1 for p in STATE['prices'].values() if p.get('chg',0)<-0.1)
            t = len(STATE['prices'])
            STATE['market_sentiment'] = 'BULLISH' if bull>t*0.65 else 'BEARISH' if bear>t*0.65 else 'NEUTRAL'
            STATE['data_source'] = f'Dhan FB({upd}/{len(WATCHLIST)}) {datetime.now().strftime("%H:%M:%S")}'
            STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
            return True
        return False
    except Exception as e:
        STATE['data_source'] = f'Error: {str(e)[:40]}'; return False

def rsi(p, n=14):
    if len(p) < n+1: return 50.0
    a = np.array(p[-n*3:], dtype=float); d = np.diff(a)
    g = np.where(d>0,d,0); l = np.where(d<0,-d,0)
    ag = np.mean(g[:n]); al = np.mean(l[:n])
    for i in range(n, len(d)):
        ag = (ag*(n-1)+g[i])/n; al = (al*(n-1)+l[i])/n
    return round(100.0 if al==0 else 100-100/(1+ag/al), 2)

def ema(p, n):
    if len(p) < n: return float(p[-1])
    a = np.array(p, dtype=float); k = 2/(n+1)
    e = float(np.mean(a[:n]))
    for x in a[n:]: e = float(x)*k + e*(1-k)
    return round(e, 2)

def bb(p, n=20):
    if len(p) < n: v=float(p[-1]); return round(v*1.02,2),round(v,2),round(v*0.98,2)
    sl = np.array(p[-n:], dtype=float); m = float(np.mean(sl)); s = float(np.std(sl))
    return round(m+2*s,2), round(m,2), round(m-2*s,2)

def macd_calc(p):
    if len(p) < 26: return 0,0,0
    m = ema(p,12)-ema(p,26); return round(m,4), round(m*0.9,4), round(m*0.1,4)

def stoch(p, n=14):
    if len(p) < n: return 50,50
    a = np.array(p[-n:], dtype=float); lo=min(a); hi=max(a)
    if hi==lo: return 50,50
    k=((p[-1]-lo)/(hi-lo))*100; return round(k,1), round(k*0.9,1)

def detect_pattern(p):
    if len(p) < 5: return 'NEUTRAL'
    c = p[-5:]
    if c[-1]>c[-2] and c[-2]<c[-3]: return 'MORNING_STAR'
    if c[-1]<c[-2] and c[-2]>c[-3]: return 'EVENING_STAR'
    if all(c[i]>c[i-1] for i in range(1,5)): return 'UPTREND'
    if all(c[i]<c[i-1] for i in range(1,5)): return 'DOWNTREND'
    return 'NEUTRAL'

def supertrend(closes, highs, lows, n=10, mult=3):
    if len(closes) < n+1: return 'NEUTRAL', closes[-1]
    atr_list = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        atr_list.append(tr)
    if len(atr_list) < n: return 'NEUTRAL', closes[-1]
    atr = np.mean(atr_list[-n:])
    hl2 = (highs[-1] + lows[-1]) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    cur = closes[-1]
    prev = closes[-2]
    if cur > upper: return 'BUY', lower
    if cur < lower: return 'SELL', upper
    if prev > upper and cur <= upper: return 'SELL', upper
    if prev < lower and cur >= lower: return 'BUY', lower
    return 'NEUTRAL', (upper+lower)/2

def darvas_box(closes, n=10):
    if len(closes) < n+1: return 'NEUTRAL', 0, 0
    recent = closes[-n:]
    box_high = max(recent[:-1])
    box_low = min(recent[:-1])
    cur = closes[-1]
    if cur > box_high * 1.002:
        return 'BUY', box_high, box_low
    if cur < box_low * 0.998:
        return 'SELL', box_high, box_low
    return 'NEUTRAL', box_high, box_low

def generate_signal(prices, strat_name=None):
    if strat_name is None: strat_name = CFG['strategy']
    if strat_name == 'AI_AUTO':
        r = rsi(prices); mc,ms,mh = macd_calc(prices)
        mom = (prices[-1]-prices[-5])/prices[-5]*100 if len(prices)>=5 else 0
        at = np.mean([abs(prices[i]-prices[i-1]) for i in range(1,min(15,len(prices)))])
        vol = at/prices[-1]*100 if prices[-1] else 1
        if vol>1.5: strat_name='BREAKOUT' if mh>0 else 'SCALP'
        elif r<30 or r>70: strat_name='REVERSAL'
        elif abs(mom)>2: strat_name='MOMENTUM'
        else: strat_name='CONSERVATIVE'
    strat = STRATS.get(strat_name, STRATS['MOMENTUM'])
    if len(prices) < 15: return 'HOLD',0,{},[],strat_name
    cur=prices[-1]; r=rsi(prices); e9=ema(prices,9); e21=ema(prices,min(21,len(prices)))
    e50=ema(prices,min(50,len(prices))); bbu,bbm,bbl=bb(prices)
    mc,ms,mh=macd_calc(prices); sk,sd=stoch(prices)
    vw=np.mean(prices[-20:]) if len(prices)>=20 else cur
    at=np.mean([abs(prices[i]-prices[i-1]) for i in range(1,min(15,len(prices)))])
    mom=(prices[-1]-prices[-5])/prices[-5]*100 if len(prices)>=5 else 0
    pat=detect_pattern(prices)
    sup=min(prices[-20:]) if len(prices)>=20 else cur*0.98
    res=max(prices[-20:]) if len(prices)>=20 else cur*1.02
    bull=0; bear=0; reasons=[]
    if r<strat['rlo']: bull+=28; reasons.append(f'RSI Oversold({r:.0f})')
    elif r<45: bull+=10
    if r>strat['rhi']: bear+=28; reasons.append(f'RSI Overbought({r:.0f})')
    elif r>55: bear+=10
    if e9>e21: bull+=22; reasons.append('EMA9>21')
    else: bear+=22; reasons.append('EMA9<21')
    if cur>e50: bull+=15; reasons.append('Above EMA50')
    else: bear+=15; reasons.append('Below EMA50')
    if cur<bbl: bull+=22; reasons.append('BB Lower')
    if cur>bbu: bear+=22; reasons.append('BB Upper')
    if mc>0 and mh>0: bull+=18; reasons.append('MACD Bull')
    elif mc<0 and mh<0: bear+=18; reasons.append('MACD Bear')
    if cur>vw*1.002: bull+=12; reasons.append('Above VWAP')
    elif cur<vw*0.998: bear+=12; reasons.append('Below VWAP')
    if sk<25: bull+=15; reasons.append('Stoch Oversold')
    if sk>75: bear+=15; reasons.append('Stoch Overbought')
    if mom>1.5: bull+=12; reasons.append(f'Mom({mom:.1f}%)')
    elif mom<-1.5: bear+=12; reasons.append(f'Mom({mom:.1f}%)')
    if 'MORNING_STAR' in pat or 'UPTREND' in pat: bull+=18; reasons.append(pat)
    if 'EVENING_STAR' in pat or 'DOWNTREND' in pat: bear+=18; reasons.append(pat)
    # Supertrend
    highs = [p*1.005 for p in prices]
    lows = [p*0.995 for p in prices]
    st_dir, st_level = supertrend(prices, highs, lows)
    if st_dir == 'BUY': bull+=20; reasons.append('Supertrend BUY')
    elif st_dir == 'SELL': bear+=20; reasons.append('Supertrend SELL')
    # Darvas Box
    db_dir, db_high, db_low = darvas_box(prices)
    if db_dir == 'BUY': bull+=18; reasons.append(f'Darvas BO>{db_high:.0f}')
    elif db_dir == 'SELL': bear+=18; reasons.append(f'Darvas BD<{db_low:.0f}')
    sent=STATE['market_sentiment']
    if sent=='BULLISH': bull+=8
    elif sent=='BEARISH': bear+=8
    total=bull+bear or 1; conf=round(max(bull,bear)/total*100,1)
    inds={'rsi':r,'ema9':e9,'ema21':e21,'bbu':bbu,'bbl':bbl,
          'macd':mc,'macd_hist':mh,'vwap':round(vw,2),'atr':round(at,2),
          'stoch':sk,'momentum':round(mom,2),'pattern':pat,
          'support':round(sup,2),'resistance':round(res,2)}
    if bull>bear and conf>strat['conf']: return 'BUY',conf,inds,reasons[:4],strat_name
    if bear>bull and conf>strat['conf']: return 'SELL',conf,inds,reasons[:4],strat_name
    return 'HOLD',conf,inds,reasons[:4],strat_name

def place_order(sym, sec_id, side, qty, otype='MARKET', price=0.0, trigger=0.0):
    if not CFG['token'] or not CFG['client_id']:
        add_log('Token nahi! Order place nahi ho sakta.','ERROR'); return None
    # BUY=long entry, SELL=long exit, SHORT=short entry, COVER=short exit
    dhan_side = 'BUY' if side in ('BUY','COVER') else 'SELL'
    payload = {
        'dhanClientId': CFG['client_id'],
        'transactionType': dhan_side,
        'exchangeSegment': 'NSE_EQ',
        'productType': 'INTRADAY',
        'orderType': otype,
        'validity': 'DAY',
        'tradingSymbol': sym,
        'securityId': str(sec_id),
        'quantity': int(qty),
        'price': round(float(price),2),
        'disclosedQuantity': 0,
        'afterMarketOrder': False,
        'triggerPrice': round(float(trigger),2),
        'amoTime': 'OPEN',
        'boProfitValue': 0,
        'boStopLossValue': 0
    }
    for attempt in range(3):
        try:
            time.sleep(random.uniform(1,3))
            r = requests.post(f'{DHAN_API}/orders', json=payload, headers=dhan_headers(), timeout=10)
            data = r.json() if r.content else {}
            oid = data.get('orderId') or (data.get('data') or {}).get('orderId')
            if oid:
                add_log(f'{side} {sym} x{qty} | Order #{oid}')
                STATE['error_count'] = 0; return oid
            if r.status_code == 401:
                STATE['token_status'] = 'expired'
                add_log('Token expired during order!','WARNING'); return None
            add_log(f'Order failed {sym}: {str(data)[:120]}','WARNING'); return None
        except Exception as e:
            add_log(f'Order error {sym}: {e}','ERROR')
            STATE['error_count'] += 1
            time.sleep(3)
    return None

def calc_qty(price, at, sl_pct):
    risk = CFG['capital'] * CFG['risk_pct'] / 100
    sl_amt = price * sl_pct / 100
    if sl_amt <= 0: sl_amt = at or price*0.01
    return max(1, min(int(risk/sl_amt), int(CFG['capital']/price)))

def update_trailing(sym, cur):
    if sym not in STATE['positions']: return
    pos = STATE['positions'][sym]
    trail_pct = CFG['trailing_pct'] / 100
    min_profit = CFG['min_profit_lock'] / 100

    if pos['side'] == 'BUY':
        # Track highest price seen
        if cur > pos.get('peak', pos['entry']):
            pos['peak'] = cur
        peak = pos.get('peak', pos['entry'])
        profit_pct = (peak - pos['entry']) / pos['entry']
        # Activate trailing only after min profit reached
        if profit_pct >= min_profit:
            new_sl = round(peak * (1 - trail_pct), 2)
            if new_sl > pos['sl']:
                pos['sl'] = new_sl
                add_log(f"Trail UP {sym}: Peak={peak:.2f} SL={new_sl:.2f} (+{profit_pct*100:.1f}%)")
    else:  # SHORT
        # Track lowest price seen
        if cur < pos.get('peak', pos['entry']):
            pos['peak'] = cur
        peak = pos.get('peak', pos['entry'])
        profit_pct = (pos['entry'] - peak) / pos['entry']
        # Activate trailing only after min profit reached
        if profit_pct >= min_profit:
            new_sl = round(peak * (1 + trail_pct), 2)
            if new_sl < pos['sl']:
                pos['sl'] = new_sl
                add_log(f"Trail DN {sym}: Peak={peak:.2f} SL={new_sl:.2f} (+{profit_pct*100:.1f}%)")

def close_pos(sym, reason, exit_price=None):
    if sym not in STATE['positions']: return
    pos = STATE['positions'][sym]
    if exit_price is None:
        exit_price = STATE['prices'].get(sym,{}).get('price', pos['entry'])
    if pos['side'] == 'BUY':
        exit_side = 'SELL'
        pnl = round((exit_price-pos['entry'])*pos['qty'],2)
    else:  # SHORT position — profit when price falls
        exit_side = 'COVER'
        pnl = round((pos['entry']-exit_price)*pos['qty'],2)
    s = STATE['stats']
    s['today_pnl'] = round(s['today_pnl']+pnl,2)
    s['total_pnl'] = round(s['total_pnl']+pnl,2)
    s['trades']+=1; s['today_trades']+=1
    if pnl>0:
        s['wins']+=1; s['streak']=max(0,s.get('streak',0))+1
        s['max_streak']=max(s.get('max_streak',0),s['streak'])
        s['best_trade']=max(s.get('best_trade',0),pnl)
    else:
        s['losses']+=1; s['streak']=min(0,s.get('streak',0))-1
        s['worst_trade']=min(s.get('worst_trade',0),pnl)
    emoji = 'WIN' if pnl>0 else 'LOSS'
    add_log(f'{emoji} CLOSED {sym} | {reason} | Entry:{pos["entry"]:.2f}->Exit:{exit_price:.2f} | PnL:{pnl:+.2f}')
    telegram(f'{emoji} <b>{sym} CLOSED</b>\n{reason}\nEntry:{pos["entry"]:.2f} Exit:{exit_price:.2f}\nPnL:<b>{pnl:+.2f}</b>\nToday:{s["today_pnl"]:+.2f}')
    STATE['trades'].appendleft({
        'sym':sym,'side':pos['side'],'qty':pos['qty'],
        'entry':pos['entry'],'exit':exit_price,'pnl':pnl,
        'reason':reason,'time':datetime.now().strftime('%H:%M'),
        'strategy':pos.get('strategy',CFG['strategy'])
    })
    time.sleep(1)
    place_order(sym, pos['secId'], exit_side, pos['qty'])
    del STATE['positions'][sym]

def get_funds():
    try:
        r = requests.get(f'{DHAN_API}/fundlimit', headers=dhan_headers(), timeout=10)
        d = r.json(); bal = float(d.get('availabelBalance',0))
        STATE['funds'] = bal; add_log(f'Available: Rs{bal:.0f}'); return bal
    except Exception as e:
        add_log(f'Funds error: {e}','WARNING'); return STATE['funds']

def scan():
    if not STATE['running']: return
    if not market_open():
        add_log('Market closed - Standby'); return
    s = STATE['stats']

    # Daily limits check
    if s['today_pnl'] <= -abs(CFG['max_loss']):
        add_log('Max loss hit! Bot stopped.','WARNING')
        STATE['running'] = False; return
    if s['today_pnl'] >= CFG['max_profit']:
        add_log('Max profit hit! Bot stopped.')
        STATE['running'] = False; return

    fetch_dhan_ltp()

    # Monitor open positions for SL/Target
    for sym in list(STATE['positions'].keys()):
        pos = STATE['positions'].get(sym)
        if not pos: continue
        cur = STATE['prices'].get(sym,{}).get('price', pos['entry'])
        update_trailing(sym, cur)
        strat = STRATS.get(pos.get('strategy',CFG['strategy']), STRATS['MOMENTUM'])
        if pos['side'] == 'BUY':
            if cur <= pos['sl']:
                profit_pct = (cur - pos['entry']) / pos['entry'] * 100
                reason = f'Trail SL Hit (+{profit_pct:.1f}%)' if profit_pct > 0 else f'SL Hit ({profit_pct:.1f}%)'
                close_pos(sym, reason, cur)
            elif CFG['use_fixed_target']:
                tgt = pos['entry'] * (1 + strat['tgt']/100)
                if cur >= tgt:
                    close_pos(sym, f'Target Hit (+{strat["tgt"]}%)', cur)
        else:  # SHORT
            if cur >= pos['sl']:
                profit_pct = (pos['entry'] - cur) / pos['entry'] * 100
                reason = f'Trail SL Hit (+{profit_pct:.1f}%)' if profit_pct > 0 else f'SL Hit ({profit_pct:.1f}%)'
                close_pos(sym, reason, cur)
            elif CFG['use_fixed_target']:
                tgt = pos['entry'] * (1 - strat['tgt']/100)
                if cur <= tgt:
                    close_pos(sym, f'Target Hit (+{strat["tgt"]}%)', cur)

    if not trading_time(): return
    if len(STATE['positions']) >= CFG['max_trades']: return

    # Scan for new entry signals
    signals = []
    for w in WATCHLIST:
        sym = w['sym']
        if sym in STATE['positions']: continue
        pd = STATE['prices'].get(sym,{})
        closes = pd.get('closes',[])
        if len(closes) < 15: continue
        result = generate_signal(closes)
        sig_dir = result[0]; conf = result[1]; inds = result[2]
        reasons = result[3]; strat_nm = result[4]
        if sig_dir in ('BUY','SELL') and conf > 55:
            cur = pd.get('price',0)
            if cur <= 0: continue
            strat = STRATS.get(strat_nm, STRATS['MOMENTUM'])
            at = inds.get('atr', cur*0.01)
            qty = calc_qty(cur, at, strat['sl'])
            signals.append({
                'sym':sym,'sec_id':w['id'],'dir':sig_dir,'conf':conf,
                'price':cur,'qty':qty,'reasons':reasons,'strat':strat_nm,
                'inds':inds,'sector':w.get('sector','')
            })

    signals.sort(key=lambda x: x['conf'], reverse=True)
    STATE['signals'] = signals[:10]
    STATE['last_scan'] = datetime.now().strftime('%H:%M:%S')

    # Execute top signals
    for sig in signals[:3]:
        if len(STATE['positions']) >= CFG['max_trades']: break
        sym = sig['sym']
        cur = sig['price']
        strat = STRATS.get(sig['strat'], STRATS['MOMENTUM'])
        if sig['dir'] == 'BUY':
            sl = round(cur*(1-strat['sl']/100),2)
            side = 'BUY'
        else:  # SELL signal = SHORT entry
            sl = round(cur*(1+strat['sl']/100),2)
            side = 'SHORT'
        qty = sig['qty']
        oid = place_order(sym, sig['sec_id'], side, qty)
        if oid:
            STATE['positions'][sym] = {
                'sym':sym,'secId':sig['sec_id'],'side':side,
                'entry':cur,'qty':qty,'sl':sl,
                'strategy':sig['strat'],'oid':oid,
                'time':datetime.now().strftime('%H:%M')
            }
            add_log(f'{side} {sym} @ {cur} | SL:{sl} | Conf:{sig["conf"]}%')
            telegram(f'<b>{side} {sym}</b> @ {cur}\nSL:{sl} | Conf:{sig["conf"]}%\n{", ".join(sig["reasons"][:3])}')

# ========== FLASK ROUTES ==========

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhan Quantum v7.0</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:'Courier New',monospace;font-size:13px}
.hdr{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:12px 16px;border-bottom:1px solid #00d4ff33;display:flex;justify-content:space-between;align-items:center}
.logo{color:#00d4ff;font-size:16px;font-weight:bold}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:6px}
.dot-green{background:#00ff88;box-shadow:0 0 8px #00ff88}
.dot-red{background:#ff4444;box-shadow:0 0 8px #ff4444}
.tabs{display:flex;background:#111;border-bottom:1px solid #333;overflow-x:auto}
.tab{padding:10px 16px;cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent;color:#888}
.tab.active{color:#00d4ff;border-bottom-color:#00d4ff}
.panel{display:none;padding:12px}
.panel.active{display:block}
.card{background:#111827;border:1px solid #1f2937;border-radius:8px;padding:12px;margin-bottom:10px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.stat-val{font-size:20px;font-weight:bold;color:#00d4ff}
.stat-lbl{color:#666;font-size:11px;margin-top:2px}
.pnl-pos{color:#00ff88}
.pnl-neg{color:#ff4444}
.btn{padding:10px 20px;border:none;border-radius:6px;cursor:pointer;font-weight:bold;font-size:13px;margin:4px}
.btn-green{background:#00aa55;color:#fff}
.btn-red{background:#aa2222;color:#fff}
.btn-blue{background:#0066cc;color:#fff}
.btn:disabled{opacity:0.5;cursor:not-allowed}
.price-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #1f2937}
.price-up{color:#00ff88}
.price-dn{color:#ff4444}
.price-neu{color:#888}
.sig-card{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px;margin-bottom:8px}
.sig-buy{border-left:3px solid #00ff88}
.sig-sell{border-left:3px solid #ff4444}
.pos-card{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:10px;margin-bottom:8px}
.pos-long{border-left:3px solid #00d4ff}
.pos-short{border-left:3px solid #ff8800}
.log-entry{padding:4px 0;border-bottom:1px solid #1a1a2a;font-size:12px}
.log-warn{color:#ffaa00}
.log-err{color:#ff4444}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold}
.badge-bull{background:#00aa5533;color:#00ff88;border:1px solid #00aa55}
.badge-bear{background:#aa222233;color:#ff4444;border:1px solid #aa2222}
.badge-neu{background:#33333333;color:#888;border:1px solid #444}
.inp{background:#1f2937;border:1px solid #374151;border-radius:6px;color:#e0e0e0;padding:8px 12px;width:100%;margin:4px 0;font-size:13px}
.refresh-bar{background:#111;padding:6px 16px;display:flex;justify-content:space-between;font-size:11px;color:#555}
</style>
</head>
<body>
<div class="hdr">
  <div class="logo">DHAN QUANTUM v7.0</div>
  <div id="hdr-status">Loading...</div>
</div>
<div class="tabs">
  <div class="tab active" onclick="showTab('dashboard',this)">Dashboard</div>
  <div class="tab" onclick="showTab('market',this)">Market</div>
  <div class="tab" onclick="showTab('signals',this)">Signals</div>
  <div class="tab" onclick="showTab('positions',this)">Positions</div>
  <div class="tab" onclick="showTab('trades',this)">Trades</div>
  <div class="tab" onclick="showTab('logs',this)">Logs</div>
  <div class="tab" onclick="showTab('settings',this)">Settings</div>
</div>
<div class="refresh-bar">
  <span id="last-update">--</span>
  <span id="data-src" style="color:#00d4ff">--</span>
</div>

<div id="tab-dashboard" class="panel active">
  <div class="card">
    <div class="grid2">
      <div><div class="stat-val" id="d-pnl">--</div><div class="stat-lbl">Today P&L</div></div>
      <div><div class="stat-val" id="d-funds">--</div><div class="stat-lbl">Available</div></div>
    </div>
  </div>
  <div class="card">
    <div class="grid3">
      <div><div class="stat-val" id="d-trades">--</div><div class="stat-lbl">Trades</div></div>
      <div><div class="stat-val" id="d-wins">--</div><div class="stat-lbl">W/L</div></div>
      <div><div class="stat-val" id="d-pos">--</div><div class="stat-lbl">Positions</div></div>
    </div>
  </div>
  <div class="card" style="text-align:center">
    <div id="d-sentiment">--</div>
    <div style="margin-top:6px;color:#555;font-size:11px">Sentiment | <span id="d-token-exp" style="color:#ffaa00">--</span></div>
  </div>
  <div style="text-align:center;margin:12px 0">
    <button class="btn btn-green" onclick="botCtrl('start')">START BOT</button>
    <button class="btn btn-red" onclick="botCtrl('stop')">STOP BOT</button>
  </div>
</div>

<div id="tab-market" class="panel">
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">LIVE PRICES</div>
    <div id="market-list">Loading...</div>
  </div>
</div>

<div id="tab-signals" class="panel">
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">LIVE SIGNALS</div>
    <div id="signals-list">No signals yet</div>
  </div>
</div>

<div id="tab-positions" class="panel">
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">OPEN POSITIONS</div>
    <div id="pos-list">No open positions</div>
  </div>
</div>

<div id="tab-trades" class="panel">
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">TRADE HISTORY</div>
    <div id="trades-list">No trades yet</div>
  </div>
</div>

<div id="tab-logs" class="panel">
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">BOT LOGS</div>
    <div id="logs-list">No logs</div>
  </div>
</div>

<div id="tab-settings" class="panel">
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">DHAN TOKEN</div>
    <textarea id="cfg-token" class="inp" rows="3" placeholder="Paste Dhan Access Token here"></textarea>
    <button class="btn btn-blue" onclick="saveToken()">Save Token</button>
    <div id="token-status" style="margin-top:6px;color:#888;font-size:12px"></div>
  </div>
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">CONFIG</div>
    <label style="color:#888;font-size:11px">Capital (Rs)</label>
    <input class="inp" id="cfg-capital" type="number" placeholder="5000">
    <label style="color:#888;font-size:11px">Max Trades</label>
    <input class="inp" id="cfg-maxtrades" type="number" placeholder="6">
    <label style="color:#888;font-size:11px">Strategy</label>
    <select class="inp" id="cfg-strategy">
      <option>MOMENTUM</option><option>SCALE</option><option>SWING</option>
      <option>BREAKOUT</option><option>REVERSAL</option><option>AGGRESSIVE</option>
      <option>CONSERVATIVE</option><option>AI_AUTO</option>
    </select>
    <button class="btn btn-blue" onclick="saveConfig()" style="margin-top:8px">Save Config</button>
  </div>
  <div class="card">
    <div style="color:#00d4ff;font-size:12px;font-weight:bold;margin-bottom:8px">TRAILING SL CONFIG</div>
    <label style="color:#888;font-size:11px">Trailing % (price peak se kitna girne pe becho)</label>
    <input class="inp" id="cfg-trail" type="number" step="0.5" placeholder="4.0">
    <label style="color:#888;font-size:11px">Min Profit % (trailing activate hone ke liye)</label>
    <input class="inp" id="cfg-minprofit" type="number" step="0.5" placeholder="1.5">
    <label style="color:#888;font-size:11px">Fixed Target use karo?</label>
    <select class="inp" id="cfg-fixtgt">
      <option value="false">No — Sirf Trailing (Recommended)</option>
      <option value="true">Yes — Fixed Target bhi</option>
    </select>
    <button class="btn btn-blue" onclick="saveTrailing()" style="margin-top:8px">Save Trailing Config</button>
  </div>
  <div class="card">
    <div style="color:#ff4444;font-size:12px;font-weight:bold;margin-bottom:8px">EMERGENCY</div>
    <button class="btn btn-red" onclick="closeAll()">CLOSE ALL POSITIONS</button>
  </div>
</div>

<script>
let currentTab='dashboard';
function showTab(tabName,el){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(tab=>tab.classList.remove('active'));
  document.getElementById('tab-'+tabName).classList.add('active');
  el.classList.add('active');
  currentTab=tabName;
}
async function fetchState(){
  try{
    const r=await fetch('/api/state');
    if(!r.ok){document.getElementById('hdr-status').textContent='API Error: '+r.status; return;}
    const d=await r.json();
    updateUI(d);
  }catch(e){
    document.getElementById('hdr-status').textContent='Err: '+e.message;
    console.error('fetchState error:',e);
  }
}
function updateUI(d){
  const s=d.stats||{};
  document.getElementById('last-update').textContent='Updated: '+new Date().toLocaleTimeString();
  document.getElementById('data-src').textContent=d.data_source||'--';
  const pnl=s.today_pnl||0;
  document.getElementById('d-pnl').textContent='Rs'+(pnl>=0?'+':'')+pnl.toFixed(2);
  document.getElementById('d-pnl').className='stat-val '+(pnl>=0?'pnl-pos':'pnl-neg');
  document.getElementById('d-funds').textContent='Rs'+(d.funds||0).toFixed(0);
  document.getElementById('d-trades').textContent=s.today_trades||0;
  document.getElementById('d-wins').textContent=(s.wins||0)+'W/'+(s.losses||0)+'L';
  document.getElementById('d-pos').textContent=Object.keys(d.positions||{}).length;
  const sent=d.market_sentiment||'NEUTRAL';
  document.getElementById('d-sentiment').innerHTML='<span class="badge badge-'+(sent=='BULLISH'?'bull':sent=='BEARISH'?'bear':'neu')+'">'+sent+'</span>';
  document.getElementById('d-token-exp').textContent='Token: '+d.token_expires;
  document.getElementById('hdr-status').innerHTML='<span class="status-dot '+(d.running?'dot-green':'dot-red')+'"></span>'+(d.running?'RUNNING':'STOPPED');

  if(currentTab=='market'){
    let html='';
    const prices=d.prices||{};
    if(Object.keys(prices).length===0){
      html='<div style="color:#555;padding:20px;text-align:center">No price data.<br><small>Source: '+d.data_source+'</small></div>';
    } else {
      for(const[sym,p] of Object.entries(prices)){
        const chg=p.chg||0;
        const cls=chg>0?'price-up':chg<0?'price-dn':'price-neu';
        const arr=chg>0?'UP':chg<0?'DN':'--';
        html+='<div class="price-row"><span style="color:#ccc;width:90px;display:inline-block">'+sym+'</span><span style="color:#00d4ff">'+((p.price||0).toFixed(2))+'</span> <span class="'+cls+'">'+arr+' '+Math.abs(chg).toFixed(2)+'%</span><span style="color:#444;font-size:10px;float:right">'+( p.source||'')+'</span></div>';
      }
    }
    document.getElementById('market-list').innerHTML=html;
  }

  if(currentTab=='signals'){
    const sigs=d.signals||[];
    let html='';
    sigs.forEach(function(sig){
      html+='<div class="sig-card '+(sig.dir=='BUY'?'sig-buy':'sig-sell')+'">'
        +'<div style="display:flex;justify-content:space-between"><span style="color:#fff;font-weight:bold">'+sig.sym+'</span>'
        +'<span style="color:'+(sig.dir=='BUY'?'#00ff88':'#ff4444')+'">'+sig.dir+' '+sig.conf.toFixed(0)+'%</span></div>'
        +'<div style="color:#888;font-size:11px;margin-top:4px">Rs'+sig.price+' | Qty:'+sig.qty+' | '+sig.strat+'</div>'
        +'<div style="color:#555;font-size:11px;margin-top:2px">'+((sig.reasons||[]).join(' | '))+'</div></div>';
    });
    document.getElementById('signals-list').innerHTML=html||'<div style="color:#555;padding:20px;text-align:center">No signals. Bot scanning...</div>';
  }

  if(currentTab=='positions'){
    const pos=d.positions||{};
    let html='';
    Object.values(pos).forEach(function(p){
      const prices=d.prices||{};
      const cur=(prices[p.sym]||{}).price||p.entry;
      const pnl=p.side=='BUY'?(cur-p.entry)*p.qty:(p.entry-cur)*p.qty;
      html+='<div class="pos-card '+(p.side=='SHORT'?'pos-short':'pos-long')+'">'
        +'<div style="display:flex;justify-content:space-between">'
        +'<span style="font-weight:bold">'+p.sym+' <span style="color:'+(p.side=='SHORT'?'#ff8800':'#00d4ff')+';font-size:11px">'+p.side+'</span></span>'
        +'<span class="'+(pnl>=0?'pnl-pos':'pnl-neg')+'">'+(pnl>=0?'+':'')+pnl.toFixed(2)+'</span></div>'
        +'<div style="color:#888;font-size:11px">Entry:'+p.entry+' SL:'+p.sl+' Qty:'+p.qty+'</div>'
        +'<button class="btn btn-red" style="padding:4px 10px;font-size:11px;margin-top:4px" onclick="closePos(\''+p.sym+'\')">Close</button>'
        +'</div>';
    });
    document.getElementById('pos-list').innerHTML=html||'<div style="color:#555;padding:20px;text-align:center">No open positions</div>';
  }

  if(currentTab=='trades'){
    const tr=d.trades||[];
    let html='';
    tr.forEach(function(t){
      html+='<div style="padding:8px 0;border-bottom:1px solid #1f2937;font-size:12px">'
        +'<span style="color:#888">'+t.time+'</span> '
        +'<span style="color:#fff;margin:0 8px">'+t.sym+'</span>'
        +'<span style="color:'+(t.side=='SHORT'?'#ff8800':'#00d4ff')+'">'+(t.side||'--')+'</span>'
        +'<span class="'+(t.pnl>=0?'pnl-pos':'pnl-neg')+'" style="float:right">'+(t.pnl>=0?'+':'')+((t.pnl||0).toFixed(2))+'</span>'
        +'</div>';
    });
    document.getElementById('trades-list').innerHTML=html||'<div style="color:#555;padding:20px;text-align:center">No trades yet</div>';
  }

  if(currentTab=='logs'){
    const logs=d.logs||[];
    let html='';
    logs.slice(0,60).forEach(function(l){
      const cls=l.level=='WARNING'?'log-warn':l.level=='ERROR'?'log-err':'';
      html+='<div class="log-entry '+cls+'"><span style="color:#555">'+l.time+'</span> '+l.msg+'</div>';
    });
    document.getElementById('logs-list').innerHTML=html||'No logs';
  }
}
async function botCtrl(action){
  await fetch('/api/bot/'+action,{method:'POST'});
  setTimeout(fetchState,500);
}
async function saveToken(){
  const token=document.getElementById('cfg-token').value.trim();
  if(!token)return;
  const r=await fetch('/api/token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token})});
  const d=await r.json();
  document.getElementById('token-status').textContent=d.message||'Saved';
  setTimeout(fetchState,1000);
}
async function saveConfig(){
  const data={
    capital:parseInt(document.getElementById('cfg-capital').value)||5000,
    max_trades:parseInt(document.getElementById('cfg-maxtrades').value)||6,
    strategy:document.getElementById('cfg-strategy').value
  };
  await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
}
async function closePos(sym){
  if(!confirm('Close '+sym+'?'))return;
  await fetch('/api/close/'+sym,{method:'POST'});
  setTimeout(fetchState,500);
}
async function closeAll(){
  if(!confirm('Close ALL positions?'))return;
  await fetch('/api/closeall',{method:'POST'});
  setTimeout(fetchState,500);
}
async function saveTrailing(){
  const data={
    trailing_pct:parseFloat(document.getElementById('cfg-trail').value)||4.0,
    min_profit_lock:parseFloat(document.getElementById('cfg-minprofit').value)||1.5,
    use_fixed_target:document.getElementById('cfg-fixtgt').value==='true'
  };
  const r=await fetch('/api/trailing',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const d=await r.json();
  alert('Trailing config saved! Trail:'+data.trailing_pct+'% MinProfit:'+data.min_profit_lock+'%');
}
fetchState();
setInterval(fetchState,5000);
</script>
</body>
</html>"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/state')
def api_state():
    return jsonify({
        'running': STATE['running'],
        'positions': STATE['positions'],
        'trades': list(STATE['trades'])[:30],
        'signals': STATE['signals'][:10],
        'prices': STATE['prices'],
        'funds': STATE['funds'],
        'data_source': STATE['data_source'],
        'market_sentiment': STATE['market_sentiment'],
        'last_price_update': STATE['last_price_update'],
        'last_scan': STATE['last_scan'],
        'token_status': STATE['token_status'],
        'token_expires': token_expires_in_str(),
        'logs': list(STATE['logs'])[:60],
        'stats': STATE['stats'],
        'market_open': market_open(),
    })

@app.route('/api/bot/start', methods=['POST'])
def api_start():
    STATE['running'] = True
    add_log('Bot STARTED')
    return jsonify({'status':'started'})

@app.route('/api/bot/stop', methods=['POST'])
def api_stop():
    STATE['running'] = False
    add_log('Bot STOPPED')
    return jsonify({'status':'stopped'})

@app.route('/api/token', methods=['POST'])
def api_token():
    data = request.get_json()
    token = data.get('token','').strip()
    if not token:
        return jsonify({'message':'No token provided'})
    CFG['token'] = token
    CFG['token_set_at'] = datetime.now()
    STATE['token_status'] = 'active'
    try:
        env_file = '/etc/dhanbot.env'
        with open(env_file, 'r') as f:
            lines = f.readlines()
        with open(env_file, 'w') as f:
            for line in lines:
                if line.startswith('DHAN_TOKEN='):
                    f.write(f'DHAN_TOKEN={token}\n')
                else:
                    f.write(line)
        subprocess.run(['sudo','systemctl','restart','dhanbot'], check=False)
    except Exception as e:
        add_log(f'Token save error: {e}','WARNING')
    add_log('Token updated!')
    return jsonify({'message':'Token saved & bot restarting...'})

@app.route('/api/config', methods=['POST'])
def api_config():
    data = request.get_json()
    if 'capital' in data: CFG['capital'] = int(data['capital'])
    if 'max_trades' in data: CFG['max_trades'] = int(data['max_trades'])
    if 'strategy' in data: CFG['strategy'] = data['strategy']
    return jsonify({'status':'ok'})

@app.route('/api/trailing', methods=['POST'])
def api_trailing():
    data = request.get_json()
    if 'trailing_pct' in data: CFG['trailing_pct'] = float(data['trailing_pct'])
    if 'min_profit_lock' in data: CFG['min_profit_lock'] = float(data['min_profit_lock'])
    if 'use_fixed_target' in data: CFG['use_fixed_target'] = bool(data['use_fixed_target'])
    add_log(f"Trailing updated: {CFG['trailing_pct']}% trail, {CFG['min_profit_lock']}% min profit")
    return jsonify({'status':'ok'})

@app.route('/api/close/<sym>', methods=['POST'])
def api_close(sym):
    close_pos(sym, 'Manual Close')
    return jsonify({'status':'closed'})

@app.route('/api/closeall', methods=['POST'])
def api_closeall():
    for sym in list(STATE['positions'].keys()):
        close_pos(sym, 'Emergency Close All')
    return jsonify({'status':'all closed'})

def bot_thread():
    add_log('Dhan Quantum v7.0 started')
    angel_login()
    schedule.every(30).seconds.do(scan)
    schedule.every(5).minutes.do(get_funds)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    t = threading.Thread(target=bot_thread, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5000, debug=False)
