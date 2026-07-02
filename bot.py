#!/usr/bin/env python3
"""Dhan Quantum Trader v8.0 - Clean & Bug Free"""
import subprocess, os, time, json, logging, threading, random
import requests, schedule, numpy as np
from datetime import datetime, time as dtime, timedelta
from collections import deque
from flask import Flask, jsonify, request, render_template_string

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('DhanQ8')

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
    'risk_pct':   float(os.environ.get('RISK_PCT', '1.5')),
    'trailing_pct': float(os.environ.get('TRAILING_PCT', '4.0')),
    'min_profit_lock': float(os.environ.get('MIN_PROFIT_LOCK', '1.5')),
    'use_fixed_target': False,
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
    'market_sentiment':'NEUTRAL','data_source':'waiting',
    'token_status':'not_set','error_count':0,
    'stats':{'trades':0,'wins':0,'losses':0,'today_pnl':0.0,'total_pnl':0.0,
             'best_trade':0.0,'worst_trade':0.0,'streak':0,'max_streak':0,'today_trades':0},
}

ANGEL_TOKENS = {
    'RELIANCE':'2885','TCS':'11536','HDFCBANK':'1333','INFY':'1594',
    'ICICIBANK':'4963','SBIN':'3045','BHARTIARTL':'10604','KOTAKBANK':'1922',
    'AXISBANK':'5900','WIPRO':'3787','MARUTI':'10999','SUNPHARMA':'3351',
    'BAJFINANCE':'317','TATAMOTORS':'3456','ADANIENT':'25','TATASTEEL':'3499',
    'NTPC':'11630','HINDALCO':'1363','POWERGRID':'14977','LTIM':'17818',
}
ANGEL_OBJ = [None]

def add_log(msg, level='INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    STATE['logs'].appendleft({'time':ts,'msg':str(msg),'level':level})
    getattr(log, level.lower() if level in ('INFO','WARNING','ERROR') else 'info')(msg)

def telegram(msg):
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
    return dtime(9,15) <= now.time() <= dtime(15,30)

def trading_time():
    now = datetime.now()
    if now.weekday() >= 5: return False
    return dtime(9,20) <= now.time() <= dtime(15,15)

def token_expires_in_str():
    if not CFG['token_set_at']: return 'Not set'
    rem = CFG['token_set_at'] + timedelta(hours=24) - datetime.now()
    if rem.total_seconds() <= 0: return 'EXPIRED'
    h,m = divmod(int(rem.total_seconds())//60, 60)
    return f'{h}h {m}m'

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
        add_log(f'Angel login error: {e}', 'WARNING')
        return False

def fetch_ltp():
    try:
        if ANGEL_OBJ[0] is None:
            angel_login()
        if ANGEL_OBJ[0] is not None:
            upd = 0
            for w in WATCHLIST:
                try:
                    aid = ANGEL_TOKENS.get(w['sym'], w['id'])
                    resp = ANGEL_OBJ[0].ltpData('NSE', w['sym'], aid)
                    if resp and resp.get('status') and resp.get('data'):
                        p = float(resp['data'].get('ltp', 0))
                        if p > 0:
                            _update_price(w['sym'], p, 'Angel')
                            upd += 1
                except: pass
            if upd > 0:
                _update_sentiment()
                STATE['data_source'] = f'Angel LIVE({upd}/{len(WATCHLIST)}) {datetime.now().strftime("%H:%M:%S")}'
                STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
                return True
    except Exception as ae:
        add_log(f'Angel failed: {ae}', 'WARNING')
        ANGEL_OBJ[0] = None

    if not CFG['token'] or not CFG['client_id']:
        STATE['data_source'] = 'No token set'; return False
    try:
        r = requests.post(f'{DHAN_API}/marketfeed/ltp',
            json={'NSE_EQ':[w['id'] for w in WATCHLIST]},
            headers=dhan_headers(), timeout=10)
        if r.status_code == 401:
            STATE['token_status'] = 'expired'
            STATE['data_source'] = 'Token expired'
            return False
        nse = r.json().get('data',{}).get('NSE_EQ',{})
        upd = 0
        for w in WATCHLIST:
            sec = nse.get(w['id'],{})
            p = sec.get('last_price') or sec.get('ltp') or sec.get('lastPrice')
            if p and float(p) > 0:
                _update_price(w['sym'], float(p), 'Dhan')
                upd += 1
        if upd > 0:
            _update_sentiment()
            STATE['data_source'] = f'Dhan FB({upd}/{len(WATCHLIST)}) {datetime.now().strftime("%H:%M:%S")}'
            STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
            return True
        return False
    except Exception as e:
        STATE['data_source'] = f'Error: {str(e)[:40]}'; return False

def _update_price(sym, p, src):
    prev = STATE['prices'].get(sym,{}).get('price', p)
    if sym not in STATE['prices']:
        STATE['prices'][sym] = {'closes':[],'volume':[]}
    STATE['prices'][sym].update({
        'price':float(p),'prev':float(prev),
        'chg':round(((float(p)-float(prev))/float(prev)*100) if prev else 0,3),
        'updated':datetime.now().strftime('%H:%M:%S'),'source':src
    })
    STATE['prices'][sym]['closes'].append(float(p))
    if len(STATE['prices'][sym]['closes']) > 100:
        STATE['prices'][sym]['closes'].pop(0)

def _update_sentiment():
    vals = list(STATE['prices'].values())
    t = len(vals)
    if t == 0: return
    bull = sum(1 for p in vals if p.get('chg',0)>0.1)
    bear = sum(1 for p in vals if p.get('chg',0)<-0.1)
    STATE['market_sentiment'] = 'BULLISH' if bull>t*0.65 else 'BEARISH' if bear>t*0.65 else 'NEUTRAL'

def rsi(p, n=14):
    if len(p) < n+1: return 50.0
    a = np.array(p[-n*3:], dtype=float); d = np.diff(a)
    g = np.where(d>0,d,0); l = np.where(d<0,-d,0)
    ag = float(np.mean(g[:n])); al = float(np.mean(l[:n]))
    for i in range(n, len(d)):
        ag = (ag*(n-1)+float(g[i]))/n; al = (al*(n-1)+float(l[i]))/n
    return round(100.0 if al==0 else 100-100/(1+ag/al), 2)

def ema(p, n):
    if len(p) < n: return float(p[-1])
    a = np.array(p, dtype=float); k = 2/(n+1)
    e = float(np.mean(a[:n]))
    for x in a[n:]: e = float(x)*k + e*(1-k)
    return round(e, 2)

def bb(p, n=20):
    if len(p) < n: v=float(p[-1]); return round(v*1.02,2),round(v,2),round(v*0.98,2)
    sl = np.array(p[-n:], dtype=float); m=float(np.mean(sl)); s=float(np.std(sl))
    return round(m+2*s,2), round(m,2), round(m-2*s,2)

def macd_calc(p):
    if len(p) < 26: return 0.0,0.0,0.0
    m = ema(p,12)-ema(p,26); return round(m,4), round(m*0.9,4), round(m*0.1,4)

def stoch(p, n=14):
    if len(p) < n: return 50.0,50.0
    a = np.array(p[-n:], dtype=float); lo=float(min(a)); hi=float(max(a))
    if hi==lo: return 50.0,50.0
    k=((float(p[-1])-lo)/(hi-lo))*100; return round(k,1), round(k*0.9,1)

def detect_pattern(p):
    if len(p) < 5: return 'NEUTRAL'
    c = p[-5:]
    if c[-1]>c[-2] and c[-2]<c[-3]: return 'MORNING_STAR'
    if c[-1]<c[-2] and c[-2]>c[-3]: return 'EVENING_STAR'
    if all(c[i]>c[i-1] for i in range(1,5)): return 'UPTREND'
    if all(c[i]<c[i-1] for i in range(1,5)): return 'DOWNTREND'
    return 'NEUTRAL'

def supertrend(closes, n=10, mult=3):
    if len(closes) < n+2: return 'NEUTRAL'
    atr = float(np.mean([abs(closes[i]-closes[i-1]) for i in range(max(1,len(closes)-n), len(closes))]))
    hl2 = float(closes[-1])
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr
    if closes[-1] > upper: return 'BUY'
    if closes[-1] < lower: return 'SELL'
    return 'NEUTRAL'

def darvas_box(closes, n=10):
    if len(closes) < n+1: return 'NEUTRAL'
    box_high = float(max(closes[-n:-1]))
    box_low = float(min(closes[-n:-1]))
    cur = float(closes[-1])
    if cur > box_high * 1.002: return 'BUY'
    if cur < box_low * 0.998: return 'SELL'
    return 'NEUTRAL'

def generate_signal(prices, strat_name=None):
    if strat_name is None: strat_name = CFG['strategy']
    if strat_name == 'AI_AUTO':
        r = rsi(prices); mc,ms,mh = macd_calc(prices)
        mom = (prices[-1]-prices[-5])/prices[-5]*100 if len(prices)>=5 else 0
        if abs(mom)>1.5: strat_name='BREAKOUT' if mh>0 else 'REVERSAL'
        elif r<30 or r>70: strat_name='REVERSAL'
        else: strat_name='MOMENTUM'
    strat = STRATS.get(strat_name, STRATS['MOMENTUM'])
    if len(prices) < 15: return 'HOLD',0,{},[],strat_name
    cur=float(prices[-1]); r=rsi(prices)
    e9=ema(prices,9); e21=ema(prices,min(21,len(prices)))
    e50=ema(prices,min(50,len(prices)))
    bbu,bbm,bbl=bb(prices)
    mc,ms,mh=macd_calc(prices)
    sk,sd=stoch(prices)
    vw=float(np.mean(prices[-20:])) if len(prices)>=20 else cur
    at=float(np.mean([abs(float(prices[i])-float(prices[i-1])) for i in range(1,min(15,len(prices)))]))
    mom=float((prices[-1]-prices[-5])/prices[-5]*100) if len(prices)>=5 else 0.0
    pat=detect_pattern(prices)
    sup=float(min(prices[-20:])) if len(prices)>=20 else cur*0.98
    res=float(max(prices[-20:])) if len(prices)>=20 else cur*1.02
    bull=0; bear=0; reasons=[]
    if r<strat['rlo']: bull+=28; reasons.append(f'RSI Oversold({r:.0f})')
    elif r<45: bull+=10
    if r>strat['rhi']: bear+=28; reasons.append(f'RSI Overbought({r:.0f})')
    elif r>55: bear+=10
    if e9>e21: bull+=22; reasons.append('EMA9>21')
    else: bear+=22; reasons.append('EMA9<21')
    if cur>e50: bull+=15; reasons.append('Above EMA50')
    else: bear+=15
    if cur<bbl: bull+=22; reasons.append('BB Lower')
    if cur>bbu: bear+=22; reasons.append('BB Upper')
    if mc>0 and mh>0: bull+=18; reasons.append('MACD Bull')
    elif mc<0 and mh<0: bear+=18; reasons.append('MACD Bear')
    if cur>vw*1.002: bull+=12; reasons.append('Above VWAP')
    elif cur<vw*0.998: bear+=12; reasons.append('Below VWAP')
    if sk<25: bull+=15; reasons.append('Stoch Oversold')
    if sk>75: bear+=15; reasons.append('Stoch Overbought')
    if mom>1.5: bull+=12; reasons.append(f'Mom+{mom:.1f}%')
    elif mom<-1.5: bear+=12; reasons.append(f'Mom{mom:.1f}%')
    if 'MORNING_STAR' in pat or 'UPTREND' in pat: bull+=18; reasons.append(pat)
    if 'EVENING_STAR' in pat or 'DOWNTREND' in pat: bear+=18; reasons.append(pat)
    st = supertrend(prices)
    if st=='BUY': bull+=20; reasons.append('Supertrend BUY')
    elif st=='SELL': bear+=20; reasons.append('Supertrend SELL')
    db = darvas_box(prices)
    if db=='BUY': bull+=18; reasons.append('Darvas Breakout')
    elif db=='SELL': bear+=18; reasons.append('Darvas Breakdown')
    sent=STATE['market_sentiment']
    if sent=='BULLISH': bull+=8
    elif sent=='BEARISH': bear+=8
    total=bull+bear or 1
    conf=round(float(max(bull,bear))/total*100,1)
    inds={
        'rsi':float(r),'ema9':float(e9),'ema21':float(e21),
        'bbu':float(bbu),'bbl':float(bbl),'macd':float(mc),
        'macd_hist':float(mh),'vwap':round(float(vw),2),
        'atr':round(float(at),2),'stoch':float(sk),
        'momentum':round(float(mom),2),'pattern':pat,
        'support':round(float(sup),2),'resistance':round(float(res),2)
    }
    if bull>bear and conf>strat['conf']: return 'BUY',conf,inds,reasons[:4],strat_name
    if bear>bull and conf>strat['conf']: return 'SELL',conf,inds,reasons[:4],strat_name
    return 'HOLD',conf,inds,reasons[:4],strat_name

def place_order(sym, sec_id, side, qty, otype='MARKET', price=0.0, trigger=0.0):
    if not CFG['token'] or not CFG['client_id']:
        add_log('No token! Cannot place order.','ERROR'); return None
    dhan_side = 'BUY' if side in ('BUY','COVER') else 'SELL'
    payload = {
        'dhanClientId':CFG['client_id'],'transactionType':dhan_side,
        'exchangeSegment':'NSE_EQ','productType':'INTRADAY',
        'orderType':otype,'validity':'DAY','tradingSymbol':sym,
        'securityId':str(sec_id),'quantity':int(qty),
        'price':round(float(price),2),'disclosedQuantity':0,
        'afterMarketOrder':False,'triggerPrice':round(float(trigger),2),
        'amoTime':'OPEN','boProfitValue':0,'boStopLossValue':0
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
                add_log('Token expired!','WARNING'); return None
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
    trail = CFG['trailing_pct'] / 100
    min_p = CFG['min_profit_lock'] / 100
    if pos['side'] == 'BUY':
        if cur > pos.get('peak', pos['entry']): pos['peak'] = cur
        peak = pos.get('peak', pos['entry'])
        if (peak - pos['entry']) / pos['entry'] >= min_p:
            new_sl = round(peak * (1 - trail), 2)
            if new_sl > pos['sl']:
                pos['sl'] = new_sl
                add_log(f"Trail {sym}: SL={new_sl:.2f}")
    else:
        if cur < pos.get('peak', pos['entry']): pos['peak'] = cur
        peak = pos.get('peak', pos['entry'])
        if (pos['entry'] - peak) / pos['entry'] >= min_p:
            new_sl = round(peak * (1 + trail), 2)
            if new_sl < pos['sl']:
                pos['sl'] = new_sl
                add_log(f"Trail {sym}: SL={new_sl:.2f}")

def close_pos(sym, reason, exit_price=None):
    if sym not in STATE['positions']: return
    pos = STATE['positions'][sym]
    if exit_price is None:
        exit_price = STATE['prices'].get(sym,{}).get('price', pos['entry'])
    exit_price = float(exit_price)
    pnl = round((exit_price-pos['entry'])*pos['qty'],2) if pos['side']=='BUY' else round((pos['entry']-exit_price)*pos['qty'],2)
    exit_side = 'SELL' if pos['side']=='BUY' else 'COVER'
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
    result = 'WIN' if pnl>0 else 'LOSS'
    add_log(f'{result} {sym} | {reason} | PnL:{pnl:+.2f}')
    telegram(f'<b>{result} {sym}</b>\n{reason}\nEntry:{pos["entry"]:.2f} Exit:{exit_price:.2f}\nPnL:<b>{pnl:+.2f}</b>\nToday:{s["today_pnl"]:+.2f}')
    STATE['trades'].appendleft({'sym':sym,'side':pos['side'],'qty':pos['qty'],'entry':pos['entry'],'exit':exit_price,'pnl':pnl,'reason':reason,'time':datetime.now().strftime('%H:%M'),'strategy':pos.get('strategy',CFG['strategy'])})
    time.sleep(1)
    place_order(sym, pos['secId'], exit_side, pos['qty'])
    del STATE['positions'][sym]

def get_funds():
    try:
        r = requests.get(f'{DHAN_API}/fundlimit', headers=dhan_headers(), timeout=10)
        bal = float(r.json().get('availabelBalance',0))
        STATE['funds'] = bal; add_log(f'Funds: Rs{bal:.0f}'); return bal
    except Exception as e:
        add_log(f'Funds error: {e}','WARNING'); return STATE['funds']

def scan():
    if not STATE['running']: return
    if not market_open():
        add_log('Market closed - Standby'); return
    s = STATE['stats']
    if s['today_pnl'] <= -abs(CFG['max_loss']):
        add_log('Max loss hit! Stopping.','WARNING'); STATE['running']=False; return
    if s['today_pnl'] >= CFG['max_profit']:
        add_log('Max profit hit! Stopping.'); STATE['running']=False; return
    fetch_ltp()
    for sym in list(STATE['positions'].keys()):
        pos = STATE['positions'].get(sym)
        if not pos: continue
        cur = float(STATE['prices'].get(sym,{}).get('price', pos['entry']))
        update_trailing(sym, cur)
        if pos['side']=='BUY':
            if cur <= pos['sl']:
                close_pos(sym, f'SL Hit', cur)
            elif CFG['use_fixed_target']:
                strat = STRATS.get(pos.get('strategy',CFG['strategy']), STRATS['MOMENTUM'])
                if cur >= pos['entry']*(1+strat['tgt']/100):
                    close_pos(sym, 'Target Hit', cur)
        else:
            if cur >= pos['sl']:
                close_pos(sym, f'SL Hit (Short)', cur)
            elif CFG['use_fixed_target']:
                strat = STRATS.get(pos.get('strategy',CFG['strategy']), STRATS['MOMENTUM'])
                if cur <= pos['entry']*(1-strat['tgt']/100):
                    close_pos(sym, 'Target Hit (Short)', cur)
    if not trading_time(): return
    if len(STATE['positions']) >= CFG['max_trades']: return
    signals = []
    for w in WATCHLIST:
        sym = w['sym']
        if sym in STATE['positions']: continue
        closes = STATE['prices'].get(sym,{}).get('closes',[])
        if len(closes) < 15: continue
        sig,conf,inds,reasons,strat_nm = generate_signal(closes)
        if sig in ('BUY','SELL') and conf>55:
            cur = float(STATE['prices'][sym].get('price',0))
            if cur<=0: continue
            strat = STRATS.get(strat_nm,STRATS['MOMENTUM'])
            at = inds.get('atr',cur*0.01)
            qty = calc_qty(cur, at, strat['sl'])
            signals.append({'sym':sym,'sec_id':w['id'],'dir':sig,'conf':conf,'price':cur,'qty':qty,'reasons':reasons,'strat':strat_nm,'sector':w.get('sector','')})
    signals.sort(key=lambda x: x['conf'], reverse=True)
    STATE['signals'] = signals[:10]
    STATE['last_scan'] = datetime.now().strftime('%H:%M:%S')
    for sig in signals[:3]:
        if len(STATE['positions']) >= CFG['max_trades']: break
        sym = sig['sym']
        cur = sig['price']
        strat = STRATS.get(sig['strat'],STRATS['MOMENTUM'])
        if sig['dir']=='BUY':
            sl = round(cur*(1-strat['sl']/100),2); side='BUY'
        else:
            sl = round(cur*(1+strat['sl']/100),2); side='SHORT'
        oid = place_order(sym, sig['sec_id'], side, sig['qty'])
        if oid:
            STATE['positions'][sym] = {'sym':sym,'secId':sig['sec_id'],'side':side,'entry':cur,'qty':sig['qty'],'sl':sl,'strategy':sig['strat'],'oid':oid,'time':datetime.now().strftime('%H:%M')}
            add_log(f'{side} {sym} @ {cur} SL:{sl} Conf:{sig["conf"]}%')
            telegram(f'<b>{side} {sym}</b> @ {cur}\nSL:{sl} Conf:{sig["conf"]}%\n{", ".join(sig["reasons"][:3])}')

# ===== FLASK ROUTES =====

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/state')
def api_state():
    def safe(v):
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, (np.floating,)): return float(v)
        return v
    prices_safe = {}
    for sym, pd in STATE['prices'].items():
        prices_safe[sym] = {k: safe(v) for k,v in pd.items() if k != 'closes'}
    return jsonify({
        'running': STATE['running'],
        'positions': STATE['positions'],
        'trades': list(STATE['trades'])[:30],
        'signals': STATE['signals'][:10],
        'prices': prices_safe,
        'funds': float(STATE['funds']),
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
    STATE['running']=True; add_log('Bot STARTED')
    return jsonify({'status':'started'})

@app.route('/api/bot/stop', methods=['POST'])
def api_stop():
    STATE['running']=False; add_log('Bot STOPPED')
    return jsonify({'status':'stopped'})

@app.route('/api/token', methods=['POST'])
def api_token():
    data = request.get_json() or {}
    token = data.get('token','').strip()
    if not token: return jsonify({'message':'No token'})
    CFG['token'] = token
    CFG['token_set_at'] = datetime.now()
    STATE['token_status'] = 'active'
    try:
        env_file = '/etc/dhanbot.env'
        lines = open(env_file).readlines()
        with open(env_file,'w') as f:
            for line in lines:
                f.write(f'DHAN_TOKEN={token}\n' if line.startswith('DHAN_TOKEN=') else line)
        subprocess.run(['sudo','systemctl','restart','dhanbot'], check=False)
    except Exception as e:
        add_log(f'Token save error: {e}','WARNING')
    add_log('Token updated!')
    return jsonify({'message':'Token saved!'})

@app.route('/api/config', methods=['POST'])
def api_config():
    data = request.get_json() or {}
    if 'capital' in data: CFG['capital']=int(data['capital'])
    if 'max_trades' in data: CFG['max_trades']=int(data['max_trades'])
    if 'strategy' in data: CFG['strategy']=data['strategy']
    if 'trailing_pct' in data: CFG['trailing_pct']=float(data['trailing_pct'])
    if 'min_profit_lock' in data: CFG['min_profit_lock']=float(data['min_profit_lock'])
    if 'use_fixed_target' in data: CFG['use_fixed_target']=bool(data['use_fixed_target'])
    add_log('Config updated')
    return jsonify({'status':'ok'})

@app.route('/api/close/<sym>', methods=['POST'])
def api_close(sym):
    close_pos(sym,'Manual Close'); return jsonify({'status':'ok'})

@app.route('/api/closeall', methods=['POST'])
def api_closeall():
    for sym in list(STATE['positions'].keys()): close_pos(sym,'Emergency Close')
    return jsonify({'status':'ok'})

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhan Quantum v8.0</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#050510;color:#c8d6e5;font-family:system-ui,sans-serif;font-size:13px;min-height:100vh}
.hdr{background:linear-gradient(90deg,#0a0a2e,#0d1b4b);padding:10px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1a3a6b;position:sticky;top:0;z-index:100}
.logo{color:#4fc3f7;font-size:15px;font-weight:700;letter-spacing:1px}
.status{display:flex;align-items:center;gap:6px;font-size:12px}
.dot{width:8px;height:8px;border-radius:50%}
.dot-on{background:#00e676;box-shadow:0 0 6px #00e676}
.dot-off{background:#ff5252;box-shadow:0 0 6px #ff5252}
.nav{display:flex;background:#080820;border-bottom:1px solid #1a2a4a;overflow-x:auto;-webkit-overflow-scrolling:touch}
.nav-btn{padding:10px 14px;color:#546e7a;border:none;background:none;cursor:pointer;white-space:nowrap;font-size:12px;font-weight:600;border-bottom:2px solid transparent;transition:all 0.2s}
.nav-btn.on{color:#4fc3f7;border-bottom-color:#4fc3f7;background:#0a1a3a}
.panel{display:none;padding:12px;animation:fadeIn 0.2s}
.panel.on{display:block}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.card{background:#0a1628;border:1px solid #1a2d4f;border-radius:10px;padding:12px;margin-bottom:10px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}
.stat-box{background:#060f1e;border:1px solid #1a2d4f;border-radius:8px;padding:10px;text-align:center}
.stat-num{font-size:22px;font-weight:700;color:#4fc3f7}
.stat-lbl{font-size:10px;color:#546e7a;margin-top:2px;text-transform:uppercase}
.pos{color:#00e676}.neg{color:#ff5252}
.btn{display:inline-block;padding:10px 20px;border:none;border-radius:8px;cursor:pointer;font-weight:700;font-size:13px;margin:4px;transition:opacity 0.2s}
.btn:active{opacity:0.7}
.btn-g{background:linear-gradient(135deg,#00897b,#00e676);color:#000}
.btn-r{background:linear-gradient(135deg,#c62828,#ff5252);color:#fff}
.btn-b{background:linear-gradient(135deg,#1565c0,#42a5f5);color:#fff}
.inp{background:#060f1e;border:1px solid #1a3a6b;border-radius:6px;color:#c8d6e5;padding:8px 10px;width:100%;margin:4px 0;font-size:13px}
.inp:focus{outline:none;border-color:#4fc3f7}
select.inp option{background:#0a1628}
.tag{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}
.tag-bull{background:#00e67620;color:#00e676;border:1px solid #00e67640}
.tag-bear{background:#ff525220;color:#ff5252;border:1px solid #ff525240}
.tag-neu{background:#54687a20;color:#78909c;border:1px solid #54687a40}
.tag-buy{background:#00e67620;color:#00e676}
.tag-sell{background:#ff525220;color:#ff5252}
.prow{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #0d1e35}
.prow:last-child{border:none}
.sym{font-weight:700;color:#e0e0e0;width:85px;display:inline-block}
.price{color:#4fc3f7;font-weight:600}
.up{color:#00e676}.dn{color:#ff5252}.neu{color:#78909c}
.src{color:#37474f;font-size:10px}
.sig-row{background:#060f1e;border-radius:8px;padding:10px;margin-bottom:6px;border-left:3px solid #1a2d4f}
.sig-b{border-left-color:#00e676}
.sig-s{border-left-color:#ff5252}
.pos-row{background:#060f1e;border-radius:8px;padding:10px;margin-bottom:6px}
.log-row{padding:4px 0;border-bottom:1px solid #0d1e35;font-size:11px;font-family:monospace}
.log-w{color:#ffa726}.log-e{color:#ff5252}.log-i{color:#78909c}
.rbar{background:#080820;padding:5px 14px;display:flex;justify-content:space-between;font-size:10px;color:#37474f;border-bottom:1px solid #0d1e35}
.sect{font-size:10px;color:#37474f;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-weight:700}
.ctr{text-align:center}
</style>
</head>
<body>
<div class="hdr">
  <div class="logo">DHAN QUANTUM v8</div>
  <div class="status">
    <div class="dot dot-off" id="dot"></div>
    <span id="run-lbl">STOPPED</span>
  </div>
</div>
<div class="nav" id="nav">
  <button class="nav-btn on" onclick="ST('dash',this)">Dashboard</button>
  <button class="nav-btn" onclick="ST('mkt',this)">Market</button>
  <button class="nav-btn" onclick="ST('sig',this)">Signals</button>
  <button class="nav-btn" onclick="ST('pos',this)">Positions</button>
  <button class="nav-btn" onclick="ST('trd',this)">Trades</button>
  <button class="nav-btn" onclick="ST('log',this)">Logs</button>
  <button class="nav-btn" onclick="ST('cfg',this)">Settings</button>
</div>
<div class="rbar">
  <span id="upd-time">--</span>
  <span id="src-lbl" style="color:#4fc3f7">--</span>
</div>

<div id="p-dash" class="panel on">
  <div class="g2" style="margin-bottom:10px">
    <div class="stat-box"><div class="stat-num" id="s-pnl">--</div><div class="stat-lbl">Today P&L</div></div>
    <div class="stat-box"><div class="stat-num" id="s-funds">--</div><div class="stat-lbl">Available</div></div>
  </div>
  <div class="g3" style="margin-bottom:10px">
    <div class="stat-box"><div class="stat-num" id="s-trd">0</div><div class="stat-lbl">Trades</div></div>
    <div class="stat-box"><div class="stat-num" id="s-wl">0/0</div><div class="stat-lbl">W / L</div></div>
    <div class="stat-box"><div class="stat-num" id="s-pos">0</div><div class="stat-lbl">Open</div></div>
  </div>
  <div class="card ctr">
    <div id="s-sent">--</div>
    <div style="color:#37474f;font-size:11px;margin-top:4px">Sentiment | <span id="s-tkn" style="color:#ffa726">--</span></div>
  </div>
  <div class="ctr" style="margin:12px 0">
    <button class="btn btn-g" onclick="BC('start')">START BOT</button>
    <button class="btn btn-r" onclick="BC('stop')">STOP BOT</button>
  </div>
  <div id="dash-pos"></div>
</div>

<div id="p-mkt" class="panel">
  <div class="card">
    <div class="sect">Live Prices</div>
    <div id="mkt-list"><div style="color:#37474f;padding:20px;text-align:center">Loading...</div></div>
  </div>
</div>

<div id="p-sig" class="panel">
  <div class="card">
    <div class="sect">Live Signals</div>
    <div id="sig-list"><div style="color:#37474f;padding:20px;text-align:center">Scanning...</div></div>
  </div>
</div>

<div id="p-pos" class="panel">
  <div class="card">
    <div class="sect">Open Positions</div>
    <div id="pos-list"><div style="color:#37474f;padding:20px;text-align:center">No positions</div></div>
  </div>
</div>

<div id="p-trd" class="panel">
  <div class="card">
    <div class="sect">Trade History</div>
    <div id="trd-list"><div style="color:#37474f;padding:20px;text-align:center">No trades yet</div></div>
  </div>
</div>

<div id="p-log" class="panel">
  <div class="card">
    <div class="sect">Bot Logs</div>
    <div id="log-list"><div style="color:#37474f;padding:20px;text-align:center">No logs</div></div>
  </div>
</div>

<div id="p-cfg" class="panel">
  <div class="card">
    <div class="sect">Dhan Token</div>
    <textarea id="i-tkn" class="inp" rows="3" placeholder="Paste Dhan Access Token"></textarea>
    <button class="btn btn-b" onclick="saveToken()">Save Token</button>
    <div id="tkn-msg" style="color:#78909c;font-size:11px;margin-top:4px"></div>
  </div>
  <div class="card">
    <div class="sect">Bot Config</div>
    <label style="color:#546e7a;font-size:11px">Capital (Rs)</label>
    <input class="inp" id="i-cap" type="number" placeholder="5000">
    <label style="color:#546e7a;font-size:11px">Max Trades</label>
    <input class="inp" id="i-mt" type="number" placeholder="6">
    <label style="color:#546e7a;font-size:11px">Strategy</label>
    <select class="inp" id="i-strat">
      <option>MOMENTUM</option><option>SCALE</option><option>SWING</option>
      <option>BREAKOUT</option><option>REVERSAL</option><option>AGGRESSIVE</option>
      <option>CONSERVATIVE</option><option>AI_AUTO</option>
    </select>
    <label style="color:#546e7a;font-size:11px">Trailing % (peak se kitna girne pe sell)</label>
    <input class="inp" id="i-trail" type="number" step="0.5" placeholder="4.0">
    <label style="color:#546e7a;font-size:11px">Min Profit % (trailing activate hone ke liye)</label>
    <input class="inp" id="i-minp" type="number" step="0.5" placeholder="1.5">
    <button class="btn btn-b" onclick="saveConfig()" style="margin-top:8px;width:100%">Save Config</button>
  </div>
  <div class="card">
    <div class="sect" style="color:#ff5252">Emergency</div>
    <button class="btn btn-r" onclick="closeAll()" style="width:100%">CLOSE ALL POSITIONS</button>
  </div>
</div>

<script>
var cur = 'dash';
function ST(tab, el) {
  document.querySelectorAll('.panel').forEach(function(p){ p.classList.remove('on'); });
  document.querySelectorAll('.nav-btn').forEach(function(b){ b.classList.remove('on'); });
  document.getElementById('p-'+tab).classList.add('on');
  el.classList.add('on');
  cur = tab;
  loadData();
}
function loadData() {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/state', true);
  xhr.onload = function() {
    if (xhr.status === 200) {
      try { render(JSON.parse(xhr.responseText)); } catch(e) {}
    }
  };
  xhr.send();
}
function render(d) {
  var s = d.stats || {};
  document.getElementById('upd-time').textContent = new Date().toLocaleTimeString();
  document.getElementById('src-lbl').textContent = d.data_source || '--';
  var dot = document.getElementById('dot');
  var lbl = document.getElementById('run-lbl');
  if (d.running) { dot.className='dot dot-on'; lbl.textContent='RUNNING'; }
  else { dot.className='dot dot-off'; lbl.textContent='STOPPED'; }
  var pnl = s.today_pnl || 0;
  var pe = document.getElementById('s-pnl');
  pe.textContent = 'Rs' + (pnl>=0?'+':'') + pnl.toFixed(2);
  pe.className = 'stat-num ' + (pnl>=0?'pos':'neg');
  document.getElementById('s-funds').textContent = 'Rs' + (d.funds||0).toFixed(0);
  document.getElementById('s-trd').textContent = s.today_trades || 0;
  document.getElementById('s-wl').textContent = (s.wins||0) + '/' + (s.losses||0);
  var posKeys = Object.keys(d.positions||{});
  document.getElementById('s-pos').textContent = posKeys.length;
  var sent = d.market_sentiment || 'NEUTRAL';
  var sc = sent=='BULLISH'?'bull':sent=='BEARISH'?'bear':'neu';
  document.getElementById('s-sent').innerHTML = '<span class="tag tag-'+sc+'">'+sent+'</span>';
  document.getElementById('s-tkn').textContent = 'Token: ' + (d.token_expires||'--');

  if (cur === 'mkt') {
    var prices = d.prices || {};
    var ks = Object.keys(prices);
    if (ks.length === 0) {
      document.getElementById('mkt-list').innerHTML = '<div style="color:#37474f;padding:20px;text-align:center">No data yet<br><small>'+d.data_source+'</small></div>';
    } else {
      var h = '';
      ks.forEach(function(sym) {
        var p = prices[sym];
        var chg = p.chg || 0;
        var cc = chg>0?'up':chg<0?'dn':'neu';
        var ar = chg>0?'▲':chg<0?'▼':'—';
        h += '<div class="prow"><span class="sym">'+sym+'</span><span class="price">'+(p.price||0).toFixed(2)+'</span><span class="'+cc+'">'+ar+' '+Math.abs(chg).toFixed(2)+'%</span><span class="src">'+( p.source||'')+'</span></div>';
      });
      document.getElementById('mkt-list').innerHTML = h;
    }
  }

  if (cur === 'sig') {
    var sigs = d.signals || [];
    if (sigs.length === 0) {
      document.getElementById('sig-list').innerHTML = '<div style="color:#37474f;padding:20px;text-align:center">No signals yet</div>';
    } else {
      var h = '';
      sigs.forEach(function(sg) {
        h += '<div class="sig-row '+(sg.dir=='BUY'?'sig-b':'sig-s')+'">';
        h += '<div style="display:flex;justify-content:space-between"><b>'+sg.sym+'</b><span class="tag '+(sg.dir=='BUY'?'tag-buy':'tag-sell')+'">'+sg.dir+' '+sg.conf.toFixed(0)+'%</span></div>';
        h += '<div style="color:#546e7a;font-size:11px;margin-top:4px">Rs'+sg.price+' | Qty:'+sg.qty+' | '+sg.strat+'</div>';
        h += '<div style="color:#37474f;font-size:11px;margin-top:2px">'+((sg.reasons||[]).join(' · '))+'</div>';
        h += '</div>';
      });
      document.getElementById('sig-list').innerHTML = h;
    }
  }

  if (cur === 'pos') {
    var pos = d.positions || {};
    var pks = Object.keys(pos);
    if (pks.length === 0) {
      document.getElementById('pos-list').innerHTML = '<div style="color:#37474f;padding:20px;text-align:center">No open positions</div>';
    } else {
      var h = '';
      pks.forEach(function(sym) {
        var p = pos[sym];
        var cp = (d.prices[sym]||{}).price || p.entry;
        var pnl = p.side=='BUY'?(cp-p.entry)*p.qty:(p.entry-cp)*p.qty;
        var sc = p.side=='SHORT'?'#ffa726':'#4fc3f7';
        h += '<div class="pos-row">';
        h += '<div style="display:flex;justify-content:space-between"><b>'+sym+'</b><span class="'+(pnl>=0?'pos':'neg')+'">'+(pnl>=0?'+':'')+pnl.toFixed(2)+'</span></div>';
        h += '<div style="color:#546e7a;font-size:11px">Side:<span style="color:'+sc+'">'+p.side+'</span> Entry:'+p.entry+' SL:'+p.sl+' Qty:'+p.qty+'</div>';
        h += '<button class="btn btn-r" style="padding:3px 10px;font-size:11px;margin-top:4px" onclick="CP(\''+sym+'\')">Close</button>';
        h += '</div>';
      });
      document.getElementById('pos-list').innerHTML = h;
    }
  }

  if (cur === 'trd') {
    var trs = d.trades || [];
    if (trs.length === 0) {
      document.getElementById('trd-list').innerHTML = '<div style="color:#37474f;padding:20px;text-align:center">No trades yet</div>';
    } else {
      var h = '';
      trs.forEach(function(t) {
        h += '<div class="prow"><span style="color:#37474f">'+t.time+'</span> <b style="margin:0 6px">'+t.sym+'</b><span style="color:'+(t.side=='SHORT'?'#ffa726':'#4fc3f7')+'">'+t.side+'</span><span class="'+(t.pnl>=0?'pos':'neg')+'" style="margin-left:auto">'+(t.pnl>=0?'+':'')+((t.pnl||0).toFixed(2))+'</span></div>';
      });
      document.getElementById('trd-list').innerHTML = h;
    }
  }

  if (cur === 'log') {
    var logs = d.logs || [];
    if (logs.length === 0) {
      document.getElementById('log-list').innerHTML = '<div style="color:#37474f;padding:20px;text-align:center">No logs</div>';
    } else {
      var h = '';
      logs.slice(0,80).forEach(function(l) {
        var lc = l.level=='WARNING'?'log-w':l.level=='ERROR'?'log-e':'log-i';
        h += '<div class="log-row '+lc+'"><span style="color:#263238">'+l.time+'</span> '+l.msg+'</div>';
      });
      document.getElementById('log-list').innerHTML = h;
    }
  }
}
function post(url, data, cb) {
  var xhr = new XMLHttpRequest();
  xhr.open('POST', url, true);
  xhr.setRequestHeader('Content-Type','application/json');
  xhr.onload = function() { if(cb) cb(JSON.parse(xhr.responseText||'{}')); };
  xhr.send(data ? JSON.stringify(data) : null);
}
function BC(action) { post('/api/bot/'+action, null, function(){ setTimeout(loadData,500); }); }
function CP(sym) { if(confirm('Close '+sym+'?')) post('/api/close/'+sym, null, function(){ setTimeout(loadData,500); }); }
function closeAll() { if(confirm('Close ALL?')) post('/api/closeall', null, function(){ setTimeout(loadData,500); }); }
function saveToken() {
  var tkn = document.getElementById('i-tkn').value.trim();
  if (!tkn) return;
  post('/api/token', {token:tkn}, function(d){
    document.getElementById('tkn-msg').textContent = d.message || 'Saved!';
    setTimeout(loadData,1000);
  });
}
function saveConfig() {
  post('/api/config', {
    capital: parseInt(document.getElementById('i-cap').value)||5000,
    max_trades: parseInt(document.getElementById('i-mt').value)||6,
    strategy: document.getElementById('i-strat').value,
    trailing_pct: parseFloat(document.getElementById('i-trail').value)||4.0,
    min_profit_lock: parseFloat(document.getElementById('i-minp').value)||1.5
  }, function(){ alert('Config saved!'); });
}
loadData();
setInterval(loadData, 5000);
</script>
</body>
</html>"""

def bot_thread():
    add_log('Dhan Quantum v8.0 started')
    angel_login()
    schedule.every(30).seconds.do(scan)
    schedule.every(5).minutes.do(get_funds)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    threading.Thread(target=bot_thread, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
