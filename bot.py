#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║       DHAN QUANTUM TRADER v5.1 — REAL-TIME EDITION          ║
║   Live Dhan LTP API + AI Strategy + 7 Trading Modes         ║
║   24/7 Server | No Browser | Mobile Built 📱 India 🇮🇳     ║
╚═══════════════════════════════════════════════════════════════╝
"""

import os, time, json, logging, threading, random
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
    'use_dhan_ltp': True,  # Use Dhan LTP API first, Yahoo as fallback
}

DHAN_API  = 'https://api.dhan.co'
SERVER    = 'https://alkubra-sync.onrender.com'
app       = Flask(__name__)
app.secret_key = 'dhan-quantum-2024'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WATCHLIST — TOP 20 NSE STOCKS
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
    {'sym':'POWERGRID',  'id':'532898',  'sector':'Power'},
    {'sym':'HINDALCO',   'id':'500440',  'sector':'Metal'},
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRATEGIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRATS = {
    'SCALP':       {'sl':0.30,'tgt':0.65,'rlo':30,'rhi':70,'conf':55,'desc':'1-5 min quick trades'},
    'MOMENTUM':    {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':58,'desc':'Trend following'},
    'SWING':       {'sl':1.50,'tgt':3.50,'rlo':30,'rhi':70,'conf':60,'desc':'2-5 day positions'},
    'BREAKOUT':    {'sl':0.60,'tgt':1.80,'rlo':45,'rhi':55,'conf':65,'desc':'Range breakouts'},
    'REVERSAL':    {'sl':0.70,'tgt':1.80,'rlo':25,'rhi':75,'conf':62,'desc':'Mean reversion'},
    'AGGRESSIVE':  {'sl':0.50,'tgt':1.20,'rlo':35,'rhi':65,'conf':55,'desc':'High frequency'},
    'CONSERVATIVE':{'sl':1.20,'tgt':3.00,'rlo':35,'rhi':65,'conf':68,'desc':'Low risk steady'},
    'AI_AUTO':     {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':60,'desc':'AI decides strategy'},
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATE = {
    'running': False,
    'positions': {},
    'trades': deque(maxlen=100),
    'logs': deque(maxlen=500),
    'signals': [],
    'prices': {},
    'candles': {},  # Store intraday candles per symbol
    'funds': 0.0,
    'last_scan': None,
    'last_price_update': None,
    'ai_analysis': '',
    'ai_strategy_override': None,
    'market_sentiment': 'NEUTRAL',
    'data_source': 'initializing',
    'error_count': 0,
    'stats': {
        'trades':0,'wins':0,'losses':0,
        'today_pnl':0.0,'total_pnl':0.0,
        'best_trade':0.0,'worst_trade':0.0,
        'streak':0,'max_streak':0,'today_trades':0,
    },
}

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
    n = datetime.now().time()
    return dtime(9,15) <= n <= dtime(15,0)

def squareoff_time():
    return datetime.now().time() >= dtime(15,15)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PRICE ENGINE — DHAN LTP (PRIMARY) + YAHOO (FALLBACK)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def fetch_dhan_ltp():
    """Fetch live LTP from Dhan API — real-time NSE data"""
    if not CFG['token'] or not CFG['client_id']:
        return False
    try:
        sec_ids = [w['id'] for w in WATCHLIST]
        payload = {"NSE_EQ": sec_ids}
        r = requests.post(f"{DHAN_API}/v2/marketfeed/ltp",
            json=payload, headers=dhan_headers(), timeout=10)
        data = r.json()
        # Dhan returns: {"data": {"NSE_EQ": {"500325": {"last_price": 2890.5, ...}}}}
        nse_data = (data.get('data') or data).get('NSE_EQ', {})
        if not nse_data:
            # Try alternative response format
            nse_data = data.get('NSE_EQ', {})
        updated = 0
        for stock in WATCHLIST:
            sec = nse_data.get(stock['id'], {})
            price = sec.get('last_price') or sec.get('ltp') or sec.get('lastPrice')
            if price and float(price) > 0:
                prev = STATE['prices'].get(stock['sym'], {}).get('price', float(price))
                chg  = ((float(price)-prev)/prev*100) if prev else 0
                if stock['sym'] not in STATE['prices']:
                    STATE['prices'][stock['sym']] = {'closes':[],'volume':[]}
                STATE['prices'][stock['sym']].update({
                    'price': float(price),
                    'prev':  prev,
                    'chg':   round(chg,3),
                    'updated': datetime.now().strftime('%H:%M:%S'),
                    'source': 'DHAN_LTP',
                })
                # Append to closes for TA
                STATE['prices'][stock['sym']]['closes'].append(float(price))
                if len(STATE['prices'][stock['sym']]['closes']) > 100:
                    STATE['prices'][stock['sym']]['closes'].pop(0)
                updated += 1
        if updated > 0:
            STATE['data_source'] = f'Dhan LTP ({updated}/{len(WATCHLIST)})'
            STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
            add_log(f'📡 Dhan LTP: {updated}/{len(WATCHLIST)} prices updated (REAL-TIME)', 'INFO')
            return True
        return False
    except Exception as e:
        add_log(f'Dhan LTP error: {e}', 'WARNING')
        return False

def fetch_dhan_candles():
    """Fetch intraday candle data from Dhan for better TA"""
    if not CFG['token'] or not CFG['client_id']: return
    today = datetime.now().strftime('%Y-%m-%d')
    updated = 0
    for stock in WATCHLIST[:10]:  # Top 10 first
        try:
            payload = {
                'securityId': str(stock['id']),
                'exchangeSegment': 'NSE_EQ',
                'instrument': 'EQUITY',
                'interval': '1',
                'fromDate': today,
                'toDate': today,
            }
            r = requests.post(f"{DHAN_API}/v2/charts/intraday",
                json=payload, headers=dhan_headers(), timeout=10)
            data = r.json()
            closes = data.get('close', [])
            volumes= data.get('volume', [])
            if closes and len(closes) > 5:
                STATE['prices'][stock['sym']]['closes'] = [float(c) for c in closes]
                STATE['prices'][stock['sym']]['volume'] = [float(v) for v in volumes]
                updated += 1
        except: pass
        time.sleep(0.1)
    if updated: add_log(f'📊 Dhan Candles: {updated} symbols updated', 'INFO')

def fetch_yahoo_fallback():
    """Yahoo Finance fallback — when Dhan LTP not available"""
    add_log('📡 Yahoo Finance fallback...', 'INFO')
    updated = 0
    for stock in WATCHLIST:
        try:
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{stock["sym"]}.NS?interval=1m&range=1d'
            r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=8)
            data = r.json()
            result = data['chart']['result'][0]
            price  = result['meta']['regularMarketPrice']
            prev   = result['meta']['chartPreviousClose']
            closes = [x for x in result['indicators']['quote'][0].get('close',[]) if x]
            volume = [x for x in result['indicators']['quote'][0].get('volume',[]) if x]
            chg    = ((price-prev)/prev*100) if prev else 0
            STATE['prices'][stock['sym']] = {
                'price': float(price), 'prev': float(prev),
                'chg': round(float(chg),3),
                'closes': [float(c) for c in closes[-80:]],
                'volume': [float(v) for v in volume[-80:]],
                'updated': datetime.now().strftime('%H:%M:%S'),
                'source': 'Yahoo(delayed)',
            }
            updated += 1
        except: pass
        time.sleep(0.2)
    STATE['data_source'] = f'Yahoo Finance ({updated}/{len(WATCHLIST)}) — 15min delayed'
    STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
    add_log(f'✅ Yahoo: {updated}/{len(WATCHLIST)} prices (15min delayed)', 'INFO')

def fetch_all_prices():
    """Smart price fetch — Dhan LTP first, Yahoo fallback"""
    if market_open() and CFG['use_dhan_ltp']:
        success = fetch_dhan_ltp()
        if success and market_open():
            fetch_dhan_candles()  # Get candle data for better TA
        if not success:
            fetch_yahoo_fallback()
    else:
        fetch_yahoo_fallback()
    update_market_sentiment()

def update_market_sentiment():
    prices = STATE['prices']
    if not prices: return
    bull = sum(1 for p in prices.values() if p.get('chg',0) > 0.1)
    bear = sum(1 for p in prices.values() if p.get('chg',0) < -0.1)
    total = len(prices)
    if bull > total*0.65:   STATE['market_sentiment'] = 'BULLISH'
    elif bear > total*0.65: STATE['market_sentiment'] = 'BEARISH'
    else:                   STATE['market_sentiment'] = 'NEUTRAL'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TECHNICAL ANALYSIS ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def rsi(p, n=14):
    if len(p)<n+1: return 50.0
    a = np.array(p[-n*3:], dtype=float)
    d = np.diff(a); g=np.where(d>0,d,0); l=np.where(d<0,-d,0)
    ag=np.mean(g[:n]); al=np.mean(l[:n])
    for i in range(n,len(d)):
        ag=(ag*(n-1)+g[i])/n; al=(al*(n-1)+l[i])/n
    return round(100.0 if al==0 else 100-100/(1+ag/al), 2)

def ema(p, n):
    if len(p)<n: return float(p[-1])
    a=np.array(p,dtype=float); k=2/(n+1)
    e=float(np.mean(a[:n]))
    for x in a[n:]: e=float(x)*k+e*(1-k)
    return round(e,2)

def bb(p, n=20):
    if len(p)<n: v=float(p[-1]); return round(v*1.02,2),round(v,2),round(v*0.98,2)
    sl=np.array(p[-n:],dtype=float); m=float(np.mean(sl)); s=float(np.std(sl))
    return round(m+2*s,2),round(m,2),round(m-2*s,2)

def macd(p):
    if len(p)<26: return 0,0,0
    m=ema(p,12)-ema(p,26); sig=round(m*0.9,4)
    return round(m,4),sig,round(m-sig,4)

def vwap(p, v=None):
    if not p: return 0
    pa=np.array(p[-20:],dtype=float)
    if v and len(v)>=len(pa):
        va=np.array(v[-len(pa):],dtype=float); va=np.where(va==0,1,va)
        return round(float(np.sum(pa*va)/np.sum(va)),2)
    return round(float(np.mean(pa)),2)

def atr(p, n=14):
    if len(p)<n+1: return round(float(p[-1])*0.01,2)
    a=np.array(p,dtype=float)
    tr=[abs(a[i]-a[i-1]) for i in range(1,len(a))]
    return round(float(np.mean(tr[-n:])),2)

def stoch(p, n=14):
    if len(p)<n: return 50,50
    a=p[-n:]; lo=min(a); hi=max(a)
    if hi==lo: return 50,50
    k=((p[-1]-lo)/(hi-lo))*100
    return round(k,1),round(k*0.9,1)

def williams_r(p, n=14):
    if len(p)<n: return -50
    a=p[-n:]; hi=max(a); lo=min(a)
    if hi==lo: return -50
    return round(((hi-p[-1])/(hi-lo))*-100, 1)

def momentum(p):
    if len(p)<10: return 0
    m5 =(p[-1]-p[-5])/p[-5]*100  if len(p)>=5  else 0
    m10=(p[-1]-p[-10])/p[-10]*100 if len(p)>=10 else 0
    return round((m5+m10)/2, 2)

def detect_pattern(p):
    if len(p)<5: return 'None'
    c=p[-5:]
    if c[-1]>c[-2] and c[-2]<c[-3] and c[-3]>c[-4]: return 'MORNING_STAR ⭐'
    if c[-1]<c[-2] and c[-2]>c[-3] and c[-3]<c[-4]: return 'EVENING_STAR 🌟'
    if all(c[i]>c[i-1] for i in range(1,5)): return 'STRONG_UPTREND 📈'
    if all(c[i]<c[i-1] for i in range(1,5)): return 'STRONG_DOWNTREND 📉'
    if c[-1]>c[-2] and c[-2]<c[-3] and c[-4]>c[-3]: return 'BULLISH_REVERSAL 🔄'
    if c[-1]<c[-2] and c[-2]>c[-3] and c[-4]<c[-3]: return 'BEARISH_REVERSAL 🔄'
    if abs(c[-1]-c[-2])/c[-2]<0.002: return 'DOJI — Indecision'
    if c[-1]>c[-2]*1.01: return 'BULLISH_CANDLE 🟢'
    if c[-1]<c[-2]*0.99: return 'BEARISH_CANDLE 🔴'
    return 'CONSOLIDATION'

def generate_signal(sym, prices, volumes=None, strat_name=None):
    if strat_name is None: strat_name = CFG['strategy']
    # AI_AUTO: dynamically pick strategy based on market conditions
    if strat_name == 'AI_AUTO':
        strat_name = pick_ai_strategy(prices)
    strat = STRATS.get(strat_name, STRATS['MOMENTUM'])
    if len(prices)<15: return 'HOLD',0,{},[],strat_name

    cur  = prices[-1]
    r    = rsi(prices)
    e9   = ema(prices,9); e21=ema(prices,min(21,len(prices)))
    e50  = ema(prices,min(50,len(prices))); e200=ema(prices,min(200,len(prices)))
    bbu,bbm,bbl = bb(prices)
    mc,ms,mh    = macd(prices)
    vw   = vwap(prices,volumes)
    at   = atr(prices)
    sk,sd= stoch(prices)
    wr   = williams_r(prices)
    mom  = momentum(prices)
    pat  = detect_pattern(prices)
    sup  = min(prices[-20:]) if len(prices)>=20 else cur*0.98
    res  = max(prices[-20:]) if len(prices)>=20 else cur*1.02

    bull=0; bear=0; reasons=[]

    # RSI
    if r<strat['rlo']:        bull+=28; reasons.append(f'RSI Oversold({r:.0f})')
    elif r<45:                bull+=10; reasons.append(f'RSI Weak({r:.0f})')
    if r>strat['rhi']:        bear+=28; reasons.append(f'RSI Overbought({r:.0f})')
    elif r>55:                bear+=10; reasons.append(f'RSI Strong({r:.0f})')

    # EMA Crossover
    if e9>e21:                bull+=22; reasons.append('EMA9>21 ↑')
    else:                     bear+=22; reasons.append('EMA9<21 ↓')
    if cur>e50:               bull+=15; reasons.append('Above EMA50')
    else:                     bear+=15; reasons.append('Below EMA50')
    if len(prices)>=200:
        if cur>e200:          bull+=10; reasons.append('Above EMA200 🐂')
        else:                 bear+=10; reasons.append('Below EMA200 🐻')

    # Bollinger Bands
    if cur<=bbl:              bull+=22; reasons.append('BB Lower Touch 🎯')
    elif cur<bbm:             bull+=8
    if cur>=bbu:              bear+=22; reasons.append('BB Upper Touch 🎯')
    elif cur>bbm:             bear+=8

    # MACD
    if mc>0 and mh>0:         bull+=18; reasons.append('MACD Bull Cross ↗')
    elif mc<0 and mh<0:       bear+=18; reasons.append('MACD Bear Cross ↘')
    elif mc>0:                bull+=8
    elif mc<0:                bear+=8

    # VWAP
    if cur>vw*1.002:          bull+=12; reasons.append('Above VWAP')
    elif cur<vw*0.998:        bear+=12; reasons.append('Below VWAP')

    # Stochastic
    if sk<25 and sd<25:       bull+=15; reasons.append('Stoch Oversold')
    if sk>75 and sd>75:       bear+=15; reasons.append('Stoch Overbought')

    # Williams %R
    if wr<-80:                bull+=10; reasons.append('Williams Oversold')
    if wr>-20:                bear+=10; reasons.append('Williams Overbought')

    # Momentum
    if mom>1.5:               bull+=12; reasons.append(f'Momentum+{mom:.1f}%')
    elif mom<-1.5:            bear+=12; reasons.append(f'Momentum{mom:.1f}%')

    # S/R Levels
    if cur<=sup*1.008:        bull+=12; reasons.append('Near Support')
    if cur>=res*0.992:        bear+=12; reasons.append('Near Resistance')

    # Candle pattern bonus
    if 'MORNING_STAR' in pat or 'UPTREND' in pat or 'BULLISH_REVERSAL' in pat or 'BULLISH_CANDLE' in pat:
        bull+=18; reasons.append(f'Pattern:{pat}')
    if 'EVENING_STAR' in pat or 'DOWNTREND' in pat or 'BEARISH_REVERSAL' in pat or 'BEARISH_CANDLE' in pat:
        bear+=18; reasons.append(f'Pattern:{pat}')

    # Market sentiment
    sent = STATE['market_sentiment']
    if sent=='BULLISH': bull+=8
    elif sent=='BEARISH': bear+=8

    total = bull+bear or 1
    conf  = round(max(bull,bear)/total*100, 1)

    indicators = {
        'rsi':r,'ema9':e9,'ema21':e21,'ema50':e50,
        'bbu':bbu,'bbm':bbm,'bbl':bbl,
        'macd':mc,'macd_hist':mh,'macd_signal':ms,
        'vwap':vw,'atr':at,'stoch':sk,
        'williams_r':wr,'momentum':mom,
        'pattern':pat,'support':round(sup,2),'resistance':round(res,2),
    }

    if bull>bear and conf>strat['conf']: return 'BUY', conf, indicators, reasons, strat_name
    if bear>bull and conf>strat['conf']: return 'SELL',conf, indicators, reasons, strat_name
    return 'HOLD', conf, indicators, reasons, strat_name

def pick_ai_strategy(prices):
    """AI Auto: Pick best strategy based on current market conditions"""
    if len(prices)<20: return 'MOMENTUM'
    r = rsi(prices[-20:]) if len(prices)>=20 else 50
    mc,ms,mh = macd(prices)
    mom = momentum(prices)
    at  = atr(prices)
    avg_price = np.mean(prices[-20:])
    volatility = at/avg_price*100 if avg_price else 1

    # High volatility → Scalp or Breakout
    if volatility > 1.5:
        return 'BREAKOUT' if mh>0 else 'SCALP'
    # Extreme RSI → Reversal
    if r<30 or r>70:
        return 'REVERSAL'
    # Strong momentum → Momentum
    if abs(mom)>2:
        return 'MOMENTUM'
    # Low volatility → Conservative
    if volatility < 0.5:
        return 'CONSERVATIVE'
    return 'MOMENTUM'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AI ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_ai_analysis():
    if not CFG['openrouter']: return
    try:
        sigs = [s for s in STATE['signals'] if s['action']!='HOLD'][:5]
        sig_text = ', '.join([f"{s['sym']}:{s['action']}({s['conf']:.0f}%)" for s in sigs])
        s = STATE['stats']
        wr = round(s['wins']/s['trades']*100,0) if s['trades'] else 0
        context = f"""NSE Trading Bot — Real-time Analysis Request:
Active Signals: {sig_text or 'None currently'}
Strategy: {CFG['strategy']}
Market Sentiment: {STATE['market_sentiment']}
Data Source: {STATE['data_source']}
Today P&L: ₹{s['today_pnl']:.0f} | Win Rate: {wr}%
Open Positions: {len(STATE['positions'])}
Today Trades: {s['today_trades']}"""

        r = requests.post('https://openrouter.ai/api/v1/chat/completions',
            headers={'Authorization':f'Bearer {CFG["openrouter"]}','Content-Type':'application/json','HTTP-Referer':'https://dhan-quantum.onrender.com'},
            json={'model':'anthropic/claude-3-haiku','messages':[
                {'role':'system','content':'Tu expert NSE intraday trader hai. Concise 3-4 line analysis de Hindi/Hinglish mein.'},
                {'role':'user','content':context}],'max_tokens':250},
            timeout=15)
        data = r.json()
        analysis = data['choices'][0]['message']['content']
        STATE['ai_analysis'] = analysis
        add_log(f'🤖 AI Analysis updated', 'INFO')
    except Exception as e:
        add_log(f'AI error: {e}', 'WARNING')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DHAN ORDER PLACEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def place_order(sym, sec_id, side, qty, otype='MARKET', price=0.0, trigger=0.0):
    if not CFG['token'] or not CFG['client_id']:
        add_log('❌ No credentials!', 'ERROR'); return None
    payload = {
        'dhanClientId':    CFG['client_id'],
        'transactionType': side,
        'exchangeSegment': 'NSE_EQ',
        'productType':     'INTRADAY',
        'orderType':       otype,
        'validity':        'DAY',
        'tradingSymbol':   sym,
        'securityId':      str(sec_id),
        'quantity':        int(qty),
        'price':           round(float(price),2),
        'triggerPrice':    round(float(trigger),2),
        'disclosedQuantity':0,'afterMarketOrder':False,
        'amoTime':'OPEN','boProfitValue':0,'boStopLossValue':0,
    }
    for attempt in range(3):
        try:
            # Random human-like delay
            time.sleep(random.uniform(2,8))
            r = requests.post(f'{DHAN_API}/orders', json=payload,
                            headers=dhan_headers(), timeout=10)
            try: data = r.json()
            except: data = {'raw':r.text[:200]}
            oid = data.get('orderId') or (data.get('data') or {}).get('orderId')
            if oid:
                add_log(f'✅ ORDER: {side} {sym} x{qty} @ ₹{price:.0f} | #{oid}', 'INFO')
                STATE['error_count'] = 0
                return oid
            else:
                add_log(f'⚠️ {sym}: {str(data)[:150]}', 'WARNING')
                return None
        except requests.Timeout:
            add_log(f'⏱️ Timeout {sym} attempt {attempt+1}', 'WARNING')
            time.sleep(3)
        except Exception as e:
            add_log(f'❌ Order error {sym}: {e}', 'ERROR')
            STATE['error_count'] += 1
            return None
    return None

def place_sl(sym, sec_id, side, qty, sl_price):
    lmt = sl_price*0.994 if side=='SELL' else sl_price*1.006
    return place_order(sym, sec_id, side, qty, 'SL', round(lmt,2), round(sl_price,2))

def get_funds():
    try:
        r = requests.get(f'{DHAN_API}/fundlimit', headers=dhan_headers(), timeout=10)
        data = r.json()
        bal = float(data.get('availableBalance', 0))
        STATE['funds'] = bal
        add_log(f'💰 Available: ₹{bal:,.0f}', 'INFO')
        return bal
    except Exception as e:
        add_log(f'Funds error: {e}', 'WARNING')
        return STATE['funds']

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POSITION SIZING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def calc_qty(price, at, sl_pct):
    risk = CFG['capital'] * CFG['risk_pct'] / 100
    sl_amt = price * sl_pct / 100
    if sl_amt <= 0: sl_amt = at or price*0.01
    qty = max(1, min(int(risk/sl_amt), int(CFG['capital']/price)))
    return qty

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TRAILING SL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def update_trailing(sym, cur):
    if not CFG['trailing_sl'] or sym not in STATE['positions']: return
    pos = STATE['positions'][sym]
    strat = STRATS.get(pos.get('strategy',CFG['strategy']), STRATS['MOMENTUM'])
    if pos['side']=='BUY':
        new_sl = cur*(1-strat['sl']/100)
        if new_sl > pos['sl']:
            old = pos['sl']; pos['sl'] = round(new_sl,2)
            if new_sl-old > 1: add_log(f'🔺 Trailing SL {sym}: ₹{old:.0f}→₹{new_sl:.0f}','INFO')
    else:
        new_sl = cur*(1+strat['sl']/100)
        if new_sl < pos['sl']:
            old = pos['sl']; pos['sl'] = round(new_sl,2)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLOSE POSITION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def close_pos(sym, reason, exit_price=None):
    if sym not in STATE['positions']: return
    pos = STATE['positions'][sym]
    if exit_price is None:
        exit_price = STATE['prices'].get(sym,{}).get('price', pos['entry'])
    pnl = round((exit_price-pos['entry'])*pos['qty'] if pos['side']=='BUY'
                else (pos['entry']-exit_price)*pos['qty'], 2)
    s = STATE['stats']
    s['today_pnl']=round(s['today_pnl']+pnl,2)
    s['total_pnl']=round(s['total_pnl']+pnl,2)
    s['trades']+=1; s['today_trades']+=1
    if pnl>0:
        s['wins']+=1; s['streak']=max(0,s.get('streak',0))+1
        s['max_streak']=max(s.get('max_streak',0),s['streak'])
        s['best_trade']=max(s.get('best_trade',0),pnl)
    else:
        s['losses']+=1; s['streak']=min(0,s.get('streak',0))-1
        s['worst_trade']=min(s.get('worst_trade',0),pnl)

    emoji='✅' if pnl>0 else '❌'
    rr = pos.get('rr','—')
    add_log(f'{emoji} CLOSED {sym} | {reason} | ₹{pos["entry"]:.2f}→₹{exit_price:.2f} | PnL:₹{pnl:+.2f} | RR:{rr}','INFO')
    telegram(f'{emoji} <b>{sym} CLOSED</b>\n{reason}\nEntry:₹{pos["entry"]:.2f} → Exit:₹{exit_price:.2f}\nPnL: <b>₹{pnl:+.2f}</b>')
    STATE['trades'].appendleft({
        'sym':sym,'side':pos['side'],'qty':pos['qty'],
        'entry':pos['entry'],'exit':exit_price,'pnl':pnl,
        'reason':reason,'time':datetime.now().strftime('%H:%M'),
        'strategy':pos.get('strategy',CFG['strategy']),'conf':pos.get('conf',0),'rr':rr,
    })
    exit_side = 'SELL' if pos['side']=='BUY' else 'BUY'
    time.sleep(1)
    place_order(sym, pos['secId'], exit_side, pos['qty'])
    del STATE['positions'][sym]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN SCAN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def scan():
    if not STATE['running']: return
    if not market_open():
        if not STATE['positions']:
            add_log('🔴 Market closed — Standby', 'INFO')
        return

    s = STATE['stats']
    if s['today_pnl'] <= -CFG['max_loss']:
        add_log(f'🚨 MAX LOSS ₹{CFG["max_loss"]} — STOPPED!','WARNING')
        telegram(f'🚨 <b>MAX LOSS HIT!</b> Bot stopped.\nLoss: ₹{abs(s["today_pnl"]):.0f}', urgent=True)
        STATE['running']=False; return
    if s['today_pnl'] >= CFG['max_profit']:
        add_log(f'🎯 TARGET ₹{CFG["max_profit"]} — STOPPED!','INFO')
        telegram(f'🎯 <b>PROFIT TARGET!</b> ₹{s["today_pnl"]:.0f}')
        STATE['running']=False; return

    # Refresh prices before scan
    if market_open() and CFG['use_dhan_ltp']:
        fetch_dhan_ltp()

    add_log(f'🔍 Scan | {CFG["strategy"]} | {STATE["data_source"]} | Pos:{len(STATE["positions"])}/{CFG["max_trades"]} | PnL:₹{s["today_pnl"]:+.0f}','INFO')

    # Check open positions
    for sym in list(STATE['positions'].keys()):
        pos = STATE['positions'][sym]
        cur = STATE['prices'].get(sym,{}).get('price', pos['entry'])
        if cur<=0: continue
        update_trailing(sym, cur)
        if pos['side']=='BUY':
            if cur<=pos['sl']:   close_pos(sym,'🛑 Stop Loss Hit',cur)
            elif cur>=pos['tgt']:close_pos(sym,'🎯 Target Hit',cur)
        else:
            if cur>=pos['sl']:   close_pos(sym,'🛑 Stop Loss Hit',cur)
            elif cur<=pos['tgt']:close_pos(sym,'🎯 Target Hit',cur)

    if not trading_time():
        add_log('⏰ New trades paused (after 3PM)','INFO'); return

    # Scan for new signals
    signals = []
    for stock in WATCHLIST:
        sym = stock['sym']
        pd  = STATE['prices'].get(sym,{})
        closes = pd.get('closes',[])
        volumes= pd.get('volume',[])
        price  = pd.get('price',0)
        if not closes or price<=0: continue

        action,conf,indicators,reasons,used_strat = generate_signal(sym,closes,volumes)
        signals.append({
            'sym':sym,'price':price,'chg':pd.get('chg',0),
            'action':action,'conf':conf,'reasons':reasons[:5],
            'rsi':indicators.get('rsi',50),'macd':indicators.get('macd',0),
            'vwap':indicators.get('vwap',price),'pattern':indicators.get('pattern','—'),
            'sector':stock.get('sector',''),'indicators':indicators,
            'used_strategy':used_strat,'source':pd.get('source','—'),
        })

        if (action!='HOLD' and sym not in STATE['positions']
                and len(STATE['positions'])<CFG['max_trades'] and conf>STRATS.get(used_strat,STRATS['MOMENTUM'])['conf']):
            strat = STRATS.get(used_strat, STRATS['MOMENTUM'])
            at  = indicators.get('atr', price*0.01)
            qty = calc_qty(price, at, strat['sl'])
            sl  = round(price*(1-strat['sl']/100) if action=='BUY' else price*(1+strat['sl']/100),2)
            tgt = round(price*(1+strat['tgt']/100) if action=='BUY' else price*(1-strat['tgt']/100),2)
            rr  = round(abs(tgt-price)/abs(price-sl),2) if price!=sl else 0

            add_log(f'🚀 {action} {sym} x{qty} @ ₹{price:.2f} | SL:₹{sl} Tgt:₹{tgt} RR:{rr} [{conf:.0f}%] ({used_strat})','INFO')
            telegram(f'🚀 <b>{action} {sym}</b> x{qty} @ ₹{price:.2f}\nSL:₹{sl} | Tgt:₹{tgt} | RR:{rr}\nConf:{conf:.0f}% | {used_strat}\n{", ".join(reasons[:3])}')

            oid = place_order(sym, stock['id'], action, qty)
            if oid:
                STATE['positions'][sym] = {
                    'sym':sym,'secId':stock['id'],'side':action,
                    'qty':qty,'entry':price,'sl':sl,'tgt':tgt,
                    'conf':conf,'oid':oid,'rr':rr,'strategy':used_strat,
                    'indicators':indicators,'time':datetime.now().strftime('%H:%M'),
                }
                time.sleep(2)
                sl_side = 'SELL' if action=='BUY' else 'BUY'
                threading.Thread(target=place_sl, args=(sym,stock['id'],sl_side,qty,sl), daemon=True).start()

    STATE['signals'] = sorted(signals, key=lambda x:x['conf'], reverse=True)
    STATE['last_scan'] = datetime.now().strftime('%H:%M:%S')

def squareoff_all():
    if not STATE['positions']: return
    add_log('⏰ 3:15PM Auto Square Off!','WARNING')
    telegram('⏰ <b>Auto Square Off 3:15PM</b>')
    for sym in list(STATE['positions'].keys()):
        close_pos(sym,'⏰ Auto Square Off 3:15PM')

def daily_reset():
    s = STATE['stats']
    s['today_pnl']=0.0; s['today_trades']=0
    s['wins']=0; s['losses']=0; s['trades']=0
    STATE['error_count']=0
    add_log('🔄 New trading day — Reset!','INFO')
    threading.Thread(target=get_funds, daemon=True).start()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLASK DASHBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DASHBOARD = open('dashboard.html').read() if os.path.exists('dashboard.html') else '''
<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dhan Quantum Trader v5.1</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:monospace;background:#030609;color:#d0e4f7;min-height:100vh;padding:20px}.hdr{color:#00d4ff;font-size:20px;font-weight:800;margin-bottom:20px}
.card{background:#080d18;border:1px solid #0d1a2e;border-radius:8px;padding:14px;margin-bottom:12px}
.green{color:#00ff9d}.red{color:#ff3060}.yellow{color:#ffd000}.btn{padding:8px 16px;border:none;border-radius:5px;cursor:pointer;font-weight:700;margin:4px}
.bg{background:#006622;color:#fff}.br{background:#660011;color:#fff}</style></head>
<body>
<div class="hdr">⚡ DHAN QUANTUM TRADER v5.1</div>
<div class="card">
  <div id="status">Loading...</div>
  <br>
  <button class="btn bg" onclick="start()">▶ START</button>
  <button class="btn br" onclick="stop()">⏹ STOP</button>
  <br><br>
  <label>Client ID: <input id="cid" placeholder="Client ID" style="background:#0d1a2e;color:#d0e4f7;border:1px solid #0d1a2e;padding:5px;border-radius:4px"></label><br><br>
  <label>Token: <input id="tok" type="password" placeholder="Access Token" style="background:#0d1a2e;color:#d0e4f7;border:1px solid #0d1a2e;padding:5px;border-radius:4px;width:300px"></label><br><br>
  <button class="btn" onclick="saveToken()" style="background:#003388;color:#fff">SAVE TOKEN</button>
</div>
<div class="card" id="statsDiv"></div>
<div class="card"><div id="logs" style="font-size:10px;max-height:300px;overflow-y:auto"></div></div>
<script>
async function refresh(){
  const d=await(await fetch('/api/state')).json();
  document.getElementById('status').innerHTML=`Running: <span class="${d.running?'green':'red'}">${d.running?'YES':'NO'}</span> | Funds: <span class="yellow">₹${Math.floor(d.funds||0).toLocaleString('en-IN')}</span> | Source: ${d.data_source||'—'}`;
  const s=d.stats;document.getElementById('statsDiv').innerHTML=`Today P&L: <span class="${s.today_pnl>=0?'green':'red'}">₹${s.today_pnl.toFixed(0)}</span> | Trades: ${s.trades} | W:${s.wins} L:${s.losses} | Positions: ${Object.keys(d.positions||{}).length}`;
  document.getElementById('logs').innerHTML=(d.logs||[]).slice(0,30).map(l=>`<div style="color:${l.level==='ERROR'?'#ff3060':l.level==='WARNING'?'#ffd000':'#4a6580'}">[${l.time}] ${l.msg}</div>`).join('');
}
async function start(){await fetch('/api/bot/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});refresh();}
async function stop(){await fetch('/api/bot/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});refresh();}
async function saveToken(){const c=document.getElementById('cid').value;const t=document.getElementById('tok').value;await fetch('/api/token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:c,token:t})});refresh();}
refresh();setInterval(refresh,5000);
</script></body></html>'''

@app.route('/')
def index(): return render_template_string(DASHBOARD)

@app.route('/api/state')
def api_state():
    return jsonify({
        'running':    STATE['running'],
        'token_ok':   bool(CFG['token'] and CFG['client_id']),
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
    data = request.json or {}
    if action in ('start','config'):
        if data.get('strategy'):   CFG['strategy']   = data['strategy']
        if data.get('capital'):    CFG['capital']     = int(data['capital'])
        if data.get('max_trades'): CFG['max_trades']  = int(data['max_trades'])
    if action=='start':
        STATE['running']=True
        add_log(f'🤖 BOT STARTED | {CFG["strategy"]} | ₹{CFG["capital"]} | Max:{CFG["max_trades"]}','INFO')
        telegram(f'🤖 <b>Dhan Quantum v5.1 STARTED!</b>\nStrategy: {CFG["strategy"]}\nCapital: ₹{CFG["capital"]}')
        threading.Thread(target=fetch_all_prices, daemon=True).start()
        threading.Thread(target=scan, daemon=True).start()
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
    add_log(f'🔑 Token updated','INFO')
    threading.Thread(target=get_funds, daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/risk', methods=['POST'])
def api_risk():
    data=request.json or {}
    if data.get('max_loss'):   CFG['max_loss']   = int(data['max_loss'])
    if data.get('max_profit'): CFG['max_profit'] = int(data['max_profit'])
    if data.get('risk_pct'):   CFG['risk_pct']   = float(data['risk_pct'])
    if data.get('max_trades'): CFG['max_trades'] = int(data['max_trades'])
    if 'trailing_sl' in data:  CFG['trailing_sl']= bool(data['trailing_sl'])
    return jsonify({'ok':True})

@app.route('/api/prices/refresh', methods=['POST'])
def api_prices():
    threading.Thread(target=fetch_all_prices, daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/funds', methods=['POST'])
def api_funds():
    threading.Thread(target=get_funds, daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/squareoff', methods=['POST'])
def api_sq():
    threading.Thread(target=squareoff_all, daemon=True).start()
    return jsonify({'ok':True})

@app.route('/health')
def health():
    return jsonify({'status':'ok','version':'5.1-quantum','time':datetime.now().isoformat(),'running':STATE['running'],'data_source':STATE['data_source']})

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEDULER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def run_scheduler():
    schedule.every(1).minutes.do(lambda: threading.Thread(target=scan, daemon=True).start() if STATE['running'] else None)
    schedule.every(1).minutes.do(lambda: threading.Thread(target=fetch_dhan_ltp, daemon=True).start() if market_open() and CFG['token'] else None)
    schedule.every(5).minutes.do(lambda: threading.Thread(target=fetch_all_prices, daemon=True).start())
    schedule.every(15).minutes.do(lambda: threading.Thread(target=get_ai_analysis, daemon=True).start())
    schedule.every().day.at('09:00').do(daily_reset)
    schedule.every().day.at('09:10').do(lambda: threading.Thread(target=get_funds, daemon=True).start())
    schedule.every().day.at('09:14').do(lambda: threading.Thread(target=fetch_all_prices, daemon=True).start())
    schedule.every().day.at('15:15').do(squareoff_all)
    add_log('⏱️ Scheduler: Scan 1min | LTP 1min | Prices 5min | AI 15min','INFO')
    while True:
        try: schedule.run_pending()
        except Exception as e: add_log(f'Scheduler: {e}','WARNING')
        time.sleep(15)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == '__main__':
    log.info('━'*55)
    log.info('  DHAN QUANTUM TRADER v5.1 — REAL-TIME EDITION')
    log.info('  Dhan LTP API + AI Strategy + 8 Trading Modes')
    log.info('  Built on Mobile 📱 — Made in India 🇮🇳')
    log.info('━'*55)

    if CFG['client_id'] and CFG['token']:
        log.info(f'Client: {CFG["client_id"][:6]}*** | Strategy: {CFG["strategy"]}')
        threading.Thread(target=get_funds, daemon=True).start()
        threading.Thread(target=fetch_all_prices, daemon=True).start()
    else:
        log.warning('⚠️  Set env vars in Render:')
        log.warning('   DHAN_CLIENT_ID, DHAN_TOKEN')
        log.warning('   Optional: TELEGRAM_TOKEN, TELEGRAM_CHAT, OPENROUTER_KEY')

    add_log('🚀 Dhan Quantum Trader v5.1 LIVE!','INFO')
    add_log('📡 Data: Dhan LTP API (Real-time) + Yahoo (Fallback)','INFO')
    add_log('🤖 Strategies: SCALP|MOMENTUM|SWING|BREAKOUT|REVERSAL|AGGRESSIVE|CONSERVATIVE|AI_AUTO','INFO')

    threading.Thread(target=run_scheduler, daemon=True).start()
    PORT = int(os.environ.get('PORT', 5000))
    log.info(f'🌐 Dashboard: http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
