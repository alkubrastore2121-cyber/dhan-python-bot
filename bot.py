#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║    DHAN QUANTUM TRADER v6.0 — BLOOMBERG TERMINAL EDITION   ║
║    World-Class NSE Algo Bot | Auto Token | AI Powered      ║
║    Built on Mobile 📱 India 🇮🇳 — Zero Manual Work        ║
╚══════════════════════════════════════════════════════════════╝
"""
import os,time,json,logging,threading,random,hashlib,hmac,base64,struct
import requests,schedule,numpy as np
from datetime import datetime,time as dtime
from collections import deque
from flask import Flask,jsonify,request,render_template_string

logging.basicConfig(level=logging.INFO,format='%(asctime)s [%(levelname)s] %(message)s',datefmt='%H:%M:%S')
log=logging.getLogger('DhanQ')

CFG={
    'client_id': os.environ.get('DHAN_CLIENT_ID',''),
    'token':     os.environ.get('DHAN_TOKEN',''),
    'api_key':   os.environ.get('DHAN_API_KEY',''),
    'api_secret':os.environ.get('DHAN_API_SECRET',''),
    'capital':   int(os.environ.get('CAPITAL','5000')),
    'max_trades':int(os.environ.get('MAX_TRADES','6')),
    'strategy':  os.environ.get('STRATEGY','MOMENTUM'),
    'max_loss':  int(os.environ.get('MAX_LOSS','2000')),
    'max_profit':int(os.environ.get('MAX_PROFIT','5000')),
    'tg_token':  os.environ.get('TELEGRAM_TOKEN',''),
    'tg_chat':   os.environ.get('TELEGRAM_CHAT',''),
    'openrouter':os.environ.get('OPENROUTER_KEY',''),
    'risk_pct':  float(os.environ.get('RISK_PCT','1.5')),
    'trailing_sl':True,
}
DHAN_API='https://api.dhan.co'
app=Flask(__name__)
app.secret_key='dhan-quantum-v6'

WATCHLIST=[
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
    {'sym':'LTIM','id':'540005','sector':'IT'},
    {'sym':'BHARTIARTL','id':'532454','sector':'Telecom'},
    {'sym':'SUNPHARMA','id':'524715','sector':'Pharma'},
    {'sym':'TATASTEEL','id':'500470','sector':'Metal'},
    {'sym':'NTPC','id':'532555','sector':'Power'},
    {'sym':'HINDALCO','id':'500440','sector':'Metal'},
    {'sym':'POWERGRID','id':'532898','sector':'Power'},
]
STRATS={
    'SCALP':      {'sl':0.30,'tgt':0.65,'rlo':30,'rhi':70,'conf':55},
    'MOMENTUM':   {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':58},
    'SWING':      {'sl':1.50,'tgt':3.50,'rlo':30,'rhi':70,'conf':60},
    'BREAKOUT':   {'sl':0.60,'tgt':1.80,'rlo':45,'rhi':55,'conf':65},
    'REVERSAL':   {'sl':0.70,'tgt':1.80,'rlo':25,'rhi':75,'conf':62},
    'AGGRESSIVE': {'sl':0.50,'tgt':1.20,'rlo':35,'rhi':65,'conf':55},
    'CONSERVATIVE':{'sl':1.20,'tgt':3.00,'rlo':35,'rhi':65,'conf':68},
    'AI_AUTO':    {'sl':0.80,'tgt':2.00,'rlo':38,'rhi':62,'conf':58},
}
STATE={
    'running':False,'positions':{},'trades':deque(maxlen=100),
    'logs':deque(maxlen=500),'signals':[],'prices':{},
    'funds':0.0,'last_scan':None,'last_price_update':None,
    'ai_analysis':'','market_sentiment':'NEUTRAL',
    'data_source':'initializing','token_status':'unknown',
    'error_count':0,'pnl_history':[],
    'stats':{'trades':0,'wins':0,'losses':0,'today_pnl':0.0,
             'total_pnl':0.0,'best_trade':0.0,'worst_trade':0.0,
             'streak':0,'max_streak':0,'today_trades':0},
}

def add_log(msg,level='INFO'):
    now=datetime.now().strftime('%H:%M:%S')
    STATE['logs'].appendleft({'time':now,'msg':msg,'level':level})
    getattr(log,level.lower(),log.info)(msg)

def telegram(msg,urgent=False):
    if not CFG['tg_token'] or not CFG['tg_chat']:return
    try:
        requests.post(f"https://api.telegram.org/bot{CFG['tg_token']}/sendMessage",
            json={'chat_id':CFG['tg_chat'],'text':('🚨 ' if urgent else '')+msg,'parse_mode':'HTML'},timeout=5)
    except:pass

def dhan_headers():
    return {'Content-Type':'application/json','access-token':CFG['token'],'client_id':CFG['client_id']}

def market_open():
    n=datetime.now()
    if n.weekday()>=5:return False
    return dtime(9,15)<=n.time()<=dtime(15,30)

def trading_time():
    return dtime(9,15)<=datetime.now().time()<=dtime(15,0)

# AUTO TOKEN REFRESH
def refresh_token():
    if not CFG['api_key'] or not CFG['api_secret']:return False
    add_log('🔄 Auto-refreshing token...','INFO')
    for url in ['https://api.dhan.co/v2/token','https://dhanhq.co/api/v2/generateToken']:
        try:
            r=requests.post(url,json={'clientId':CFG['client_id'],'apiKey':CFG['api_key'],'apiSecret':CFG['api_secret']},
                headers={'Content-Type':'application/json'},timeout=15)
            d=r.json()
            tok=d.get('accessToken') or d.get('access_token') or (d.get('data') or {}).get('accessToken')
            if tok:
                CFG['token']=tok; STATE['token_status']='auto_refreshed'
                add_log('✅ Token auto-refreshed!','INFO')
                telegram('🔑 <b>Token auto-refreshed!</b>')
                return True
        except:pass
    add_log('⚠️ Auto-refresh failed — manual token needed','WARNING')
    if CFG['tg_token']:telegram('⚠️ Token refresh failed! Update manually:\nhttps://dhan-python-bot.onrender.com',urgent=True)
    return False

def check_token():
    if not CFG['token']:return refresh_token()
    try:
        r=requests.get(f'{DHAN_API}/fundlimit',headers=dhan_headers(),timeout=10)
        if r.status_code==200:
            d=r.json()
            if d.get('availableBalance') is not None:
                STATE['token_status']='valid'
                STATE['funds']=float(d.get('availableBalance',0))
                return True
        return refresh_token()
    except:return refresh_token()

# PRICE ENGINE
def fetch_dhan_ltp():
    if not CFG['token'] or not CFG['client_id']:return False
    try:
        r=requests.post(f"{DHAN_API}/v2/marketfeed/ltp",
            json={"NSE_EQ":[w['id'] for w in WATCHLIST]},headers=dhan_headers(),timeout=10)
        d=r.json()
        nse=(d.get('data') or d).get('NSE_EQ',{}) or d.get('NSE_EQ',{})
        upd=0
        for w in WATCHLIST:
            sec=nse.get(w['id'],{})
            p=sec.get('last_price') or sec.get('ltp') or sec.get('lastPrice')
            if p and float(p)>0:
                prev=STATE['prices'].get(w['sym'],{}).get('price',float(p))
                if w['sym'] not in STATE['prices']:STATE['prices'][w['sym']]={'closes':[],'volume':[]}
                STATE['prices'][w['sym']].update({'price':float(p),'prev':prev,'chg':round(((float(p)-prev)/prev*100) if prev else 0,3),'updated':datetime.now().strftime('%H:%M:%S'),'source':'DHAN_RT'})
                STATE['prices'][w['sym']]['closes'].append(float(p))
                if len(STATE['prices'][w['sym']]['closes'])>100:STATE['prices'][w['sym']]['closes'].pop(0)
                upd+=1
        if upd>0:
            STATE['data_source']=f'Dhan LTP Real-Time ✅ ({upd}/{len(WATCHLIST)})'
            STATE['last_price_update']=datetime.now().strftime('%H:%M:%S')
            add_log(f'📡 Dhan LTP: {upd}/{len(WATCHLIST)} real-time','INFO')
            return True
    except Exception as e:add_log(f'LTP: {e}','WARNING')
    return False

def fetch_yahoo():
    upd=0
    for w in WATCHLIST:
        try:
            r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{w["sym"]}.NS?interval=1m&range=1d',
                headers={'User-Agent':'Mozilla/5.0'},timeout=8)
            d=r.json()['chart']['result'][0]
            p=d['meta']['regularMarketPrice']; prev=d['meta']['chartPreviousClose']
            closes=[x for x in d['indicators']['quote'][0].get('close',[]) if x]
            volume=[x for x in d['indicators']['quote'][0].get('volume',[]) if x]
            STATE['prices'][w['sym']]={'price':float(p),'prev':float(prev),'chg':round(((p-prev)/prev*100) if prev else 0,3),'closes':[float(c) for c in closes[-80:]],'volume':[float(v) for v in volume[-80:]],'updated':datetime.now().strftime('%H:%M:%S'),'source':'Yahoo'}
            upd+=1
        except:pass
        time.sleep(0.2)
    STATE['data_source']=f'Yahoo Finance ({upd}/{len(WATCHLIST)}) 15min delay'
    add_log(f'📡 Yahoo: {upd}/{len(WATCHLIST)}','INFO')

def fetch_all_prices():
    if market_open() and CFG['token']:
        if not fetch_dhan_ltp():fetch_yahoo()
    else:fetch_yahoo()
    prices=STATE['prices']
    if prices:
        bull=sum(1 for p in prices.values() if p.get('chg',0)>0.1)
        bear=sum(1 for p in prices.values() if p.get('chg',0)<-0.1)
        t=len(prices)
        STATE['market_sentiment']='BULLISH' if bull>t*0.65 else 'BEARISH' if bear>t*0.65 else 'NEUTRAL'

# TECHNICAL ANALYSIS
def rsi(p,n=14):
    if len(p)<n+1:return 50.0
    a=np.array(p[-n*3:],dtype=float);d=np.diff(a)
    g=np.where(d>0,d,0);l=np.where(d<0,-d,0)
    ag=np.mean(g[:n]);al=np.mean(l[:n])
    for i in range(n,len(d)):ag=(ag*(n-1)+g[i])/n;al=(al*(n-1)+l[i])/n
    return round(100.0 if al==0 else 100-100/(1+ag/al),2)

def ema(p,n):
    if len(p)<n:return float(p[-1])
    a=np.array(p,dtype=float);k=2/(n+1);e=float(np.mean(a[:n]))
    for x in a[n:]:e=float(x)*k+e*(1-k)
    return round(e,2)

def bb(p,n=20):
    if len(p)<n:v=float(p[-1]);return round(v*1.02,2),round(v,2),round(v*0.98,2)
    sl=np.array(p[-n:],dtype=float);m=float(np.mean(sl));s=float(np.std(sl))
    return round(m+2*s,2),round(m,2),round(m-2*s,2)

def macd(p):
    if len(p)<26:return 0,0,0
    m=ema(p,12)-ema(p,26);return round(m,4),round(m*0.9,4),round(m*0.1,4)

def stoch(p,n=14):
    if len(p)<n:return 50,50
    a=p[-n:];lo=min(a);hi=max(a)
    if hi==lo:return 50,50
    k=((p[-1]-lo)/(hi-lo))*100;return round(k,1),round(k*0.9,1)

def detect_pattern(p):
    if len(p)<5:return 'NONE'
    c=p[-5:]
    if c[-1]>c[-2] and c[-2]<c[-3]:return 'MORNING_STAR'
    if c[-1]<c[-2] and c[-2]>c[-3]:return 'EVENING_STAR'
    if all(c[i]>c[i-1] for i in range(1,5)):return 'UPTREND'
    if all(c[i]<c[i-1] for i in range(1,5)):return 'DOWNTREND'
    return 'NEUTRAL'

def pick_strategy(prices):
    if len(prices)<20:return 'MOMENTUM'
    r=rsi(prices);mc,ms,mh=macd(prices)
    mom=(prices[-1]-prices[-5])/prices[-5]*100 if len(prices)>=5 else 0
    at=np.mean([abs(prices[i]-prices[i-1]) for i in range(1,min(15,len(prices)))])
    vol=at/prices[-1]*100 if prices[-1] else 1
    if vol>1.5:return 'BREAKOUT' if mh>0 else 'SCALP'
    if r<30 or r>70:return 'REVERSAL'
    if abs(mom)>2:return 'MOMENTUM'
    if vol<0.5:return 'CONSERVATIVE'
    return 'MOMENTUM'

def generate_signal(prices,strat_name=None):
    if strat_name is None:strat_name=CFG['strategy']
    if strat_name=='AI_AUTO':strat_name=pick_strategy(prices)
    strat=STRATS.get(strat_name,STRATS['MOMENTUM'])
    if len(prices)<15:return 'HOLD',0,{},[],strat_name
    cur=prices[-1];r=rsi(prices)
    e9=ema(prices,9);e21=ema(prices,min(21,len(prices)));e50=ema(prices,min(50,len(prices)))
    bbu,bbm,bbl=bb(prices);mc,ms,mh=macd(prices);sk,sd=stoch(prices)
    vw=np.mean(prices[-20:]) if len(prices)>=20 else cur
    at=np.mean([abs(prices[i]-prices[i-1]) for i in range(1,min(15,len(prices)))])
    mom=(prices[-1]-prices[-5])/prices[-5]*100 if len(prices)>=5 else 0
    pat=detect_pattern(prices)
    sup=min(prices[-20:]) if len(prices)>=20 else cur*0.98
    res=max(prices[-20:]) if len(prices)>=20 else cur*1.02
    bull=0;bear=0;reasons=[]
    if r<strat['rlo']:bull+=28;reasons.append(f'RSI Oversold({r:.0f})')
    elif r<45:bull+=10
    if r>strat['rhi']:bear+=28;reasons.append(f'RSI Overbought({r:.0f})')
    elif r>55:bear+=10
    if e9>e21:bull+=22;reasons.append('EMA9>21↑')
    else:bear+=22;reasons.append('EMA9<21↓')
    if cur>e50:bull+=15;reasons.append('Above EMA50')
    else:bear+=15;reasons.append('Below EMA50')
    if cur<=bbl:bull+=22;reasons.append('BB Lower🎯')
    if cur>=bbu:bear+=22;reasons.append('BB Upper🎯')
    if mc>0 and mh>0:bull+=18;reasons.append('MACD Bull↗')
    elif mc<0 and mh<0:bear+=18;reasons.append('MACD Bear↘')
    if cur>vw*1.002:bull+=12;reasons.append('Above VWAP')
    elif cur<vw*0.998:bear+=12;reasons.append('Below VWAP')
    if sk<25:bull+=15;reasons.append('Stoch Oversold')
    if sk>75:bear+=15;reasons.append('Stoch Overbought')
    if mom>1.5:bull+=12;reasons.append(f'Mom+{mom:.1f}%')
    elif mom<-1.5:bear+=12;reasons.append(f'Mom{mom:.1f}%')
    if cur<=sup*1.008:bull+=12;reasons.append('Near Support')
    if cur>=res*0.992:bear+=12;reasons.append('Near Resistance')
    if 'MORNING_STAR' in pat or 'UPTREND' in pat:bull+=18;reasons.append(pat)
    if 'EVENING_STAR' in pat or 'DOWNTREND' in pat:bear+=18;reasons.append(pat)
    sent=STATE['market_sentiment']
    if sent=='BULLISH':bull+=8
    elif sent=='BEARISH':bear+=8
    total=bull+bear or 1;conf=round(max(bull,bear)/total*100,1)
    inds={'rsi':r,'ema9':e9,'ema21':e21,'bbu':bbu,'bbm':bbm,'bbl':bbl,'macd':mc,'macd_hist':mh,'vwap':round(vw,2),'atr':round(at,2),'stoch':sk,'momentum':round(mom,2),'pattern':pat,'support':round(sup,2),'resistance':round(res,2)}
    if bull>bear and conf>strat['conf']:return 'BUY',conf,inds,reasons,strat_name
    if bear>bull and conf>strat['conf']:return 'SELL',conf,inds,reasons,strat_name
    return 'HOLD',conf,inds,reasons,strat_name

def place_order(sym,sec_id,side,qty,otype='MARKET',price=0.0,trigger=0.0):
    if not CFG['token'] or not CFG['client_id']:add_log('❌ No token!','ERROR');return None
    payload={'dhanClientId':CFG['client_id'],'transactionType':side,'exchangeSegment':'NSE_EQ','productType':'INTRADAY','orderType':otype,'validity':'DAY','tradingSymbol':sym,'securityId':str(sec_id),'quantity':int(qty),'price':round(float(price),2),'triggerPrice':round(float(trigger),2),'disclosedQuantity':0,'afterMarketOrder':False,'amoTime':'OPEN','boProfitValue':0,'boStopLossValue':0}
    for attempt in range(3):
        try:
            time.sleep(random.uniform(2,6))
            r=requests.post(f'{DHAN_API}/orders',json=payload,headers=dhan_headers(),timeout=10)
            try:data=r.json()
            except:data={'raw':r.text[:200]}
            oid=data.get('orderId') or (data.get('data') or {}).get('orderId')
            if oid:add_log(f'✅ {side} {sym} x{qty} | #{oid}','INFO');STATE['error_count']=0;return oid
            if r.status_code==401:check_token()
            add_log(f'⚠️ {sym}: {str(data)[:120]}','WARNING');return None
        except requests.Timeout:time.sleep(3)
        except Exception as e:add_log(f'❌ {sym}: {e}','ERROR');STATE['error_count']+=1;return None
    return None

def place_sl(sym,sec_id,side,qty,sl_price):
    lmt=sl_price*0.994 if side=='SELL' else sl_price*1.006
    return place_order(sym,sec_id,side,qty,'SL',round(lmt,2),round(sl_price,2))

def get_funds():
    try:
        r=requests.get(f'{DHAN_API}/fundlimit',headers=dhan_headers(),timeout=10)
        d=r.json();bal=float(d.get('availableBalance',0))
        STATE['funds']=bal;add_log(f'💰 ₹{bal:,.0f}','INFO');return bal
    except Exception as e:add_log(f'Funds: {e}','WARNING');return STATE['funds']

def calc_qty(price,at,sl_pct):
    risk=CFG['capital']*CFG['risk_pct']/100
    sl_amt=price*sl_pct/100
    if sl_amt<=0:sl_amt=at or price*0.01
    return max(1,min(int(risk/sl_amt),int(CFG['capital']/price)))

def update_trailing(sym,cur):
    if not CFG['trailing_sl'] or sym not in STATE['positions']:return
    pos=STATE['positions'][sym]
    strat=STRATS.get(pos.get('strategy',CFG['strategy']),STRATS['MOMENTUM'])
    if pos['side']=='BUY':
        new_sl=cur*(1-strat['sl']/100)
        if new_sl>pos['sl']:pos['sl']=round(new_sl,2)
    else:
        new_sl=cur*(1+strat['sl']/100)
        if new_sl<pos['sl']:pos['sl']=round(new_sl,2)

def close_pos(sym,reason,exit_price=None):
    if sym not in STATE['positions']:return
    pos=STATE['positions'][sym]
    if exit_price is None:exit_price=STATE['prices'].get(sym,{}).get('price',pos['entry'])
    pnl=round((exit_price-pos['entry'])*pos['qty'] if pos['side']=='BUY' else (pos['entry']-exit_price)*pos['qty'],2)
    s=STATE['stats']
    s['today_pnl']=round(s['today_pnl']+pnl,2);s['total_pnl']=round(s['total_pnl']+pnl,2)
    s['trades']+=1;s['today_trades']+=1
    if pnl>0:s['wins']+=1;s['streak']=max(0,s.get('streak',0))+1;s['max_streak']=max(s.get('max_streak',0),s['streak']);s['best_trade']=max(s.get('best_trade',0),pnl)
    else:s['losses']+=1;s['streak']=min(0,s.get('streak',0))-1;s['worst_trade']=min(s.get('worst_trade',0),pnl)
    emoji='✅' if pnl>0 else '❌'
    add_log(f'{emoji} CLOSED {sym} | {reason} | ₹{pos["entry"]:.2f}→₹{exit_price:.2f} | PnL:₹{pnl:+.2f}','INFO')
    telegram(f'{emoji} <b>{sym} CLOSED</b>\n{reason}\nPnL: <b>₹{pnl:+.2f}</b>')
    STATE['trades'].appendleft({'sym':sym,'side':pos['side'],'qty':pos['qty'],'entry':pos['entry'],'exit':exit_price,'pnl':pnl,'reason':reason,'time':datetime.now().strftime('%H:%M'),'strategy':pos.get('strategy',CFG['strategy'])})
    exit_side='SELL' if pos['side']=='BUY' else 'BUY'
    time.sleep(1);place_order(sym,pos['secId'],exit_side,pos['qty'])
    del STATE['positions'][sym]

def scan():
    if not STATE['running']:return
    if not market_open():
        if not STATE['positions']:add_log('🔴 Market closed — Standby','INFO')
        return
    s=STATE['stats']
    if s['today_pnl']<=-CFG['max_loss']:
        add_log(f'🚨 MAX LOSS ₹{CFG["max_loss"]}!','WARNING');telegram(f'🚨 Max Loss! ₹{abs(s["today_pnl"]):.0f}',urgent=True);STATE['running']=False;return
    if s['today_pnl']>=CFG['max_profit']:
        add_log(f'🎯 TARGET ₹{CFG["max_profit"]}!','INFO');telegram(f'🎯 Target Hit! ₹{s["today_pnl"]:.0f}');STATE['running']=False;return
    if market_open() and CFG['token']:fetch_dhan_ltp()
    add_log(f'🔍 Scan | {CFG["strategy"]} | Pos:{len(STATE["positions"])}/{CFG["max_trades"]} | PnL:₹{s["today_pnl"]:+.0f}','INFO')
    for sym in list(STATE['positions'].keys()):
        pos=STATE['positions'][sym];cur=STATE['prices'].get(sym,{}).get('price',pos['entry'])
        if cur<=0:continue
        update_trailing(sym,cur)
        if pos['side']=='BUY':
            if cur<=pos['sl']:close_pos(sym,'🛑 SL Hit',cur)
            elif cur>=pos['tgt']:close_pos(sym,'🎯 Target Hit',cur)
        else:
            if cur>=pos['sl']:close_pos(sym,'🛑 SL Hit',cur)
            elif cur<=pos['tgt']:close_pos(sym,'🎯 Target Hit',cur)
    if not trading_time():add_log('⏰ New trades paused','INFO');return
    signals=[]
    for w in WATCHLIST:
        sym=w['sym'];pd=STATE['prices'].get(sym,{})
        closes=pd.get('closes',[]);price=pd.get('price',0)
        if not closes or price<=0:continue
        action,conf,inds,reasons,used=generate_signal(closes)
        signals.append({'sym':sym,'price':price,'chg':pd.get('chg',0),'action':action,'conf':conf,'reasons':reasons[:4],'rsi':inds.get('rsi',50),'macd':inds.get('macd',0),'pattern':inds.get('pattern','—'),'sector':w.get('sector',''),'indicators':inds,'used_strategy':used,'source':pd.get('source','—')})
        if action!='HOLD' and sym not in STATE['positions'] and len(STATE['positions'])<CFG['max_trades'] and conf>STRATS.get(used,STRATS['MOMENTUM'])['conf']:
            strat=STRATS.get(used,STRATS['MOMENTUM']);at=inds.get('atr',price*0.01)
            qty=calc_qty(price,at,strat['sl'])
            sl=round(price*(1-strat['sl']/100) if action=='BUY' else price*(1+strat['sl']/100),2)
            tgt=round(price*(1+strat['tgt']/100) if action=='BUY' else price*(1-strat['tgt']/100),2)
            rr=round(abs(tgt-price)/abs(price-sl),2) if price!=sl else 0
            add_log(f'🚀 {action} {sym} x{qty} @ ₹{price:.2f} SL:{sl} Tgt:{tgt} RR:{rr} [{conf:.0f}%]','INFO')
            telegram(f'🚀 <b>{action} {sym}</b> x{qty} @ ₹{price:.2f}\nSL:₹{sl} Tgt:₹{tgt} RR:{rr} Conf:{conf:.0f}%')
            oid=place_order(sym,w['id'],action,qty)
            if oid:
                STATE['positions'][sym]={'sym':sym,'secId':w['id'],'side':action,'qty':qty,'entry':price,'sl':sl,'tgt':tgt,'conf':conf,'oid':oid,'rr':rr,'strategy':used,'time':datetime.now().strftime('%H:%M')}
                time.sleep(2);sl_side='SELL' if action=='BUY' else 'BUY'
                threading.Thread(target=place_sl,args=(sym,w['id'],sl_side,qty,sl),daemon=True).start()
    STATE['signals']=sorted(signals,key=lambda x:x['conf'],reverse=True)
    STATE['last_scan']=datetime.now().strftime('%H:%M:%S')

def squareoff_all():
    if not STATE['positions']:return
    add_log('⏰ 3:15PM Square Off!','WARNING');telegram('⏰ <b>Auto Square Off 3:15PM</b>')
    for sym in list(STATE['positions'].keys()):close_pos(sym,'⏰ Auto Square Off')

def daily_reset():
    s=STATE['stats'];s['today_pnl']=0.0;s['today_trades']=0;s['wins']=0;s['losses']=0;s['trades']=0
    STATE['error_count']=0;add_log('🔄 New day reset!','INFO')

def get_ai_analysis():
    if not CFG['openrouter']:return
    try:
        sigs=[s for s in STATE['signals'] if s['action']!='HOLD'][:5]
        sig_text=', '.join([f"{s['sym']}:{s['action']}({s['conf']:.0f}%)" for s in sigs])
        s=STATE['stats']
        r=requests.post('https://openrouter.ai/api/v1/chat/completions',
            headers={'Authorization':f'Bearer {CFG["openrouter"]}','Content-Type':'application/json'},
            json={'model':'anthropic/claude-3-haiku','messages':[
                {'role':'system','content':'Expert NSE intraday trader. 3 line Hindi/Hinglish analysis.'},
                {'role':'user','content':f'Signals:{sig_text} PnL:₹{s["today_pnl"]:.0f} Sentiment:{STATE["market_sentiment"]} Strategy:{CFG["strategy"]}'}],
            'max_tokens':200},timeout=15)
        STATE['ai_analysis']=r.json()['choices'][0]['message']['content']
        add_log('🤖 AI updated','INFO')
    except Exception as e:add_log(f'AI: {e}','WARNING')

# BLOOMBERG TERMINAL DASHBOARD
DASHBOARD=r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Dhan Quantum v6.0</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700;800&family=Orbitron:wght@700;900&display=swap');
:root{
  --bg:#000508;--bg2:#020c12;--bg3:#041018;
  --card:#030f18;--border:#0a2030;--border2:#0d2840;
  --accent:#00d4ff;--accent2:#0088bb;
  --green:#00ff9d;--green2:#00cc7a;
  --red:#ff3060;--red2:#cc2050;
  --yellow:#ffd000;--purple:#c084fc;
  --orange:#fb923c;--cyan:#22d3ee;
  --text:#c8e8f8;--dim:#2a5070;--muted:#1a3850;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{font-family:'JetBrains Mono',monospace;background:var(--bg);color:var(--text);font-size:10px}

/* SCANLINES EFFECT */
body::after{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,20,40,0.03) 2px,rgba(0,20,40,0.03) 4px);pointer-events:none;z-index:9999}

/* HEADER */
.hdr{background:linear-gradient(90deg,#000508,#020c12,#000508);border-bottom:1px solid #0a2030;padding:6px 12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;flex-shrink:0}
.logo-wrap{display:flex;align-items:center;gap:10px}
.logo-icon{width:32px;height:32px;background:linear-gradient(135deg,#00d4ff,#0055aa);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 0 15px #00d4ff30}
.logo-title{font-family:'Orbitron',monospace;font-size:12px;font-weight:900;color:var(--accent);letter-spacing:3px;text-shadow:0 0 20px #00d4ff50}
.logo-sub{font-size:7px;color:var(--dim);letter-spacing:2px;margin-top:1px}
.hdr-right{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.bdg{padding:2px 8px;border-radius:3px;font-size:7px;font-weight:700;border:1px solid;letter-spacing:0.5px;font-family:'JetBrains Mono',monospace}
.time-display{font-size:11px;color:var(--accent);font-weight:700;letter-spacing:2px;font-family:'Orbitron',monospace}

/* TICKER TAPE */
.ticker{background:#000;border-bottom:1px solid var(--border);padding:4px 0;overflow:hidden;white-space:nowrap;flex-shrink:0}
.ticker-inner{display:inline-block;animation:ticker 40s linear infinite}
@keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.ticker-item{display:inline-block;margin:0 20px;font-size:9px;font-weight:600}

/* TOKEN BAR */
.token-bar{background:var(--bg2);border-bottom:1px solid var(--border);padding:5px 12px;flex-shrink:0}
.trow{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tlbl{font-size:7px;color:var(--dim);letter-spacing:1px;min-width:80px;font-weight:700}
.inp{padding:4px 8px;background:var(--bg3);border:1px solid var(--border2);border-radius:3px;color:var(--text);font-family:'JetBrains Mono',monospace;font-size:8px;outline:none;transition:border 0.2s}
.inp:focus{border-color:var(--accent);box-shadow:0 0 8px #00d4ff20}
.btn{padding:4px 10px;border:none;border-radius:3px;cursor:pointer;font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:700;letter-spacing:0.5px;transition:all 0.2s;text-transform:uppercase}
.btn:hover{filter:brightness(1.3);transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.bg{background:linear-gradient(90deg,#004422,#00aa44);color:#fff;box-shadow:0 0 10px #00aa4430}
.br{background:linear-gradient(90deg,#440011,#aa0033);color:#fff;box-shadow:0 0 10px #aa003330}
.bb{background:linear-gradient(90deg,#002244,#0055aa);color:#fff}
.bp{background:linear-gradient(90deg,#220044,#5500aa);color:#fff}
.bo{background:linear-gradient(90deg,#442200,#aa5500);color:#fff}

/* MAIN LAYOUT */
.main{display:flex;height:calc(100vh - 140px);overflow:hidden}

/* LEFT PANEL */
.left-panel{width:260px;min-width:260px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.panel-hdr{padding:6px 10px;background:var(--bg2);border-bottom:1px solid var(--border);font-size:8px;font-weight:700;color:var(--dim);letter-spacing:2px;display:flex;justify-content:space-between;align-items:center}
.market-list{flex:1;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
.market-row{display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid var(--muted);cursor:pointer;transition:background 0.1s}
.market-row:hover{background:var(--bg2)}
.market-row.active{background:#001a30;border-left:2px solid var(--accent)}
.mr-sym{font-size:9px;font-weight:700;color:var(--text)}
.mr-sec{font-size:7px;color:var(--dim);margin-top:1px}
.mr-price{text-align:right}
.mr-ltp{font-size:9px;font-weight:700;color:var(--yellow)}
.mr-chg{font-size:7px;font-weight:600;margin-top:1px}
.mr-sig{padding:1px 5px;border-radius:2px;font-size:7px;font-weight:700}
.sig-b{background:#001a0d;color:var(--green);border:1px solid #00ff9d20}
.sig-s{background:#1a0008;color:var(--red);border:1px solid #ff306020}
.sig-h{background:var(--muted);color:var(--dim);border:1px solid var(--border)}

/* CENTER PANEL */
.center-panel{flex:1;display:flex;flex-direction:column;overflow:hidden}

/* STATS BAR */
.stats-bar{display:flex;gap:1px;padding:6px 8px;background:var(--bg2);border-bottom:1px solid var(--border);flex-wrap:wrap;gap:6px}
.stat-item{background:var(--card);border:1px solid var(--border);border-radius:4px;padding:5px 10px;min-width:90px;flex:1}
.stat-lbl{font-size:6px;color:var(--dim);letter-spacing:1.5px;font-weight:700;text-transform:uppercase;margin-bottom:2px}
.stat-val{font-size:16px;font-weight:800;line-height:1}
.stat-sub{font-size:6px;color:var(--dim);margin-top:2px}

/* TABS */
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid var(--border);padding:0 8px;flex-shrink:0}
.tab{padding:6px 12px;border:none;cursor:pointer;background:transparent;font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:700;color:var(--dim);border-bottom:2px solid transparent;white-space:nowrap;letter-spacing:0.5px;transition:all 0.15s;text-transform:uppercase}
.tab.on{color:var(--accent);border-bottom-color:var(--accent);background:#001830}
.tab-content{flex:1;overflow-y:auto;padding:8px;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
.tp{display:none}.tp.on{display:block}

/* TABLE */
table{width:100%;border-collapse:collapse;font-size:8px}
th{padding:5px 8px;text-align:left;color:var(--dim);border-bottom:1px solid var(--border);font-weight:700;letter-spacing:0.5px;font-size:7px;text-transform:uppercase;background:var(--bg2);position:sticky;top:0;z-index:1}
td{padding:5px 8px;border-bottom:1px solid var(--muted)}
tr:hover td{background:#001830}
.fw{font-weight:700}

/* RIGHT PANEL */
.right-panel{width:240px;min-width:240px;border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.pos-list{flex:1;overflow-y:auto;padding:6px;scrollbar-width:thin}
.pos-card{background:var(--card);border:1px solid var(--border);border-radius:4px;padding:8px;margin-bottom:5px;transition:border-color 0.3s}
.pos-card.profit{border-color:#00ff9d30}
.pos-card.loss{border-color:#ff306030}
.pos-sym{font-size:11px;font-weight:800;margin-bottom:3px}
.pos-info{display:flex;flex-wrap:wrap;gap:4px;font-size:7px;color:var(--dim)}
.pos-pnl{font-size:13px;font-weight:800}
.prog{height:2px;background:var(--border);border-radius:1px;margin-top:4px;overflow:hidden}
.prog-f{height:100%;border-radius:1px;transition:width 0.5s}

/* LOG */
.logbox{font-size:8px;line-height:1.9;padding:4px 0}
.li{color:var(--dim)}.ls{color:var(--green)}.le{color:var(--red)}.lw{color:var(--yellow)}.lt{color:var(--cyan)}

/* CONTROLS */
.ctrl-panel{padding:8px;border-top:1px solid var(--border);background:var(--bg2);flex-shrink:0}
.ctrl-row{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:5px}

/* INDICATOR BARS */
.ind-row{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.ind-chip{background:var(--bg3);border:1px solid var(--border);border-radius:3px;padding:2px 6px;font-size:7px}
.ind-lbl{color:var(--dim);margin-right:3px}

/* AI BOX */
.ai-box{background:#020008;border:1px solid #330055;border-radius:4px;padding:8px;margin-top:6px;font-size:8px;line-height:1.8;color:#d0b0ff;max-height:100px;overflow-y:auto}

/* BLINK */
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.1}}
.dot{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:3px;vertical-align:middle}
.dg{background:var(--green);box-shadow:0 0 5px var(--green);animation:blink 1.5s infinite}
.dr{background:var(--red)}
.dy{background:var(--yellow);animation:blink 1s infinite}

/* GLOW EFFECTS */
@keyframes glow{0%,100%{box-shadow:0 0 5px #00d4ff20}50%{box-shadow:0 0 15px #00d4ff40}}
.running-glow{animation:glow 2s infinite}

/* MOBILE */
@media(max-width:768px){
  html,body{overflow:auto;height:auto}
  .main{flex-direction:column;height:auto;overflow:visible}
  .left-panel{width:100%;min-width:unset;border-right:none;border-bottom:1px solid var(--border);max-height:250px}
  .right-panel{width:100%;min-width:unset;border-left:none;border-top:1px solid var(--border);max-height:300px}
  .center-panel{overflow:visible}
  .tab-content{overflow:visible;max-height:none}
  .stats-bar{overflow-x:auto;flex-wrap:nowrap}
  .stat-item{min-width:80px}
}
</style>
</head>
<body>

<!-- HEADER -->
<div class="hdr">
  <div class="logo-wrap">
    <div class="logo-icon">⚡</div>
    <div>
      <div class="logo-title">DHAN QUANTUM v6.0</div>
      <div class="logo-sub">NSE INTRADAY • REAL-TIME • AI POWERED • AUTO TOKEN • 24/7</div>
    </div>
  </div>
  <div class="hdr-right">
    <div class="time-display" id="clockDisplay">--:--:--</div>
    <div class="badges" id="hdrBdg" style="display:flex;gap:4px;flex-wrap:wrap">
      <span class="bdg" style="border-color:#2a5070;color:#2a5070">⏳ LOADING</span>
    </div>
  </div>
</div>

<!-- TICKER -->
<div class="ticker">
  <div class="ticker-inner" id="tickerInner">
    <span style="color:var(--dim);margin:0 20px">LOADING MARKET DATA...</span>
  </div>
</div>

<!-- TOKEN BAR -->
<div class="token-bar">
  <div class="trow">
    <span class="tlbl">🔑 DHAN:</span>
    <input class="inp" id="inpCid" placeholder="Client ID" style="width:90px">
    <input class="inp" id="inpTok" type="password" placeholder="Token (auto-refreshes via API Key)" style="flex:1;min-width:140px">
    <button class="btn bb" onclick="saveToken()">SAVE</button>
    <button class="btn bp" onclick="forceRefresh()">🔄 REFRESH</button>
    <span id="tokStat" style="font-size:7px;color:var(--green)"></span>
  </div>
</div>

<!-- MAIN LAYOUT -->
<div class="main">

  <!-- LEFT: MARKET WATCHLIST -->
  <div class="left-panel">
    <div class="panel-hdr">
      <span>📊 MARKET WATCH</span>
      <span id="mktSent" style="color:var(--yellow)">—</span>
    </div>
    <div class="market-list" id="marketList">
      <div style="text-align:center;color:var(--dim);padding:20px;font-size:8px">Loading...</div>
    </div>
  </div>

  <!-- CENTER: MAIN CONTENT -->
  <div class="center-panel">

    <!-- STATS BAR -->
    <div class="stats-bar" id="statsBar"></div>

    <!-- CONTROL ROW -->
    <div style="padding:5px 8px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;gap:5px;flex-wrap:wrap;align-items:center;flex-shrink:0">
      <button class="btn bg running-glow" id="btnStart" onclick="botCmd('start')">▶ START</button>
      <button class="btn br" id="btnStop" onclick="botCmd('stop')" style="display:none">⏹ STOP</button>
      <select class="inp" id="selStrat" style="width:170px">
        <option value="MOMENTUM">⚡ Momentum (SL 0.8% | Tgt 2%)</option>
        <option value="SCALP">⚡ Scalping (SL 0.3% | Tgt 0.65%)</option>
        <option value="SWING">⚡ Swing (SL 1.5% | Tgt 3.5%)</option>
        <option value="BREAKOUT">⚡ Breakout (SL 0.6% | Tgt 1.8%)</option>
        <option value="REVERSAL">⚡ Reversal (SL 0.7% | Tgt 1.8%)</option>
        <option value="AI_AUTO">🤖 AI Auto Strategy</option>
        <option value="AGGRESSIVE">🔥 Aggressive</option>
        <option value="CONSERVATIVE">🛡️ Conservative</option>
      </select>
      <input class="inp" type="number" id="inpCap" value="5000" placeholder="₹" style="width:70px">
      <input class="inp" type="number" id="inpMax" value="6" style="width:45px">
      <button class="btn bb" onclick="saveConfig()">SAVE</button>
      <button class="btn bo" onclick="doSq()">⚠️ SQ OFF</button>
      <button class="btn bb" onclick="doRefresh()">📡 PRICES</button>
      <button class="btn bb" onclick="doFunds()">💰 FUNDS</button>
    </div>

    <!-- TABS -->
    <div class="tabs">
      <button class="tab on" onclick="sw('signals',this)">🎯 SIGNALS</button>
      <button class="tab" onclick="sw('history',this)">📋 HISTORY</button>
      <button class="tab" onclick="sw('ai',this)">🤖 AI</button>
      <button class="tab" onclick="sw('logs',this)">📝 LOGS</button>
      <button class="tab" onclick="sw('risk',this)">🛡️ RISK</button>
    </div>

    <div class="tab-content">

      <!-- SIGNALS -->
      <div id="tab-signals" class="tp on">
        <table>
          <thead><tr>
            <th>SYMBOL</th><th>LTP</th><th>CHG%</th><th>RSI</th>
            <th>MACD</th><th>STOCH</th><th>PATTERN</th>
            <th>SIGNAL</th><th>CONF</th><th>STRATEGY</th><th>SOURCE</th>
          </tr></thead>
          <tbody id="sigTbl">
            <tr><td colspan="11" style="text-align:center;color:var(--dim);padding:30px">Bot start karein — signals yahan dikhenge</td></tr>
          </tbody>
        </table>
      </div>

      <!-- HISTORY -->
      <div id="tab-history" class="tp">
        <table>
          <thead><tr><th>TIME</th><th>SYM</th><th>SIDE</th><th>QTY</th><th>ENTRY</th><th>EXIT</th><th>P&L</th><th>RR</th><th>STRATEGY</th><th>REASON</th></tr></thead>
          <tbody id="histTbl">
            <tr><td colspan="10" style="text-align:center;color:var(--dim);padding:20px">No trades yet</td></tr>
          </tbody>
        </table>
      </div>

      <!-- AI -->
      <div id="tab-ai" class="tp">
        <div style="font-size:8px;color:var(--dim);margin-bottom:8px;letter-spacing:1px">🤖 AI TRADING INTELLIGENCE — OPENROUTER POWERED</div>
        <div class="ai-box" id="aiBox" style="max-height:200px">
          <span style="color:var(--dim)">// AI analysis loads automatically every 15 minutes when bot is running...</span>
        </div>
        <div style="margin-top:10px;display:flex;gap:6px">
          <input class="inp" id="aiInput" placeholder="Ask AI: Aaj kya buy karein? Market outlook? Risk tips?" style="flex:1">
          <button class="btn bp" onclick="askAI()">ASK ➤</button>
        </div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px">
          <button class="btn" onclick="qa('Aaj market bullish hai ya bearish? Top 3 stocks batao')" style="background:var(--bg3);border:1px solid var(--border);color:var(--dim);font-size:7px">📊 Market View</button>
          <button class="btn" onclick="qa('Best intraday stocks aaj ke liye')" style="background:var(--bg3);border:1px solid var(--border);color:var(--dim);font-size:7px">🎯 Top Picks</button>
          <button class="btn" onclick="qa('Risk management tips NSE intraday')" style="background:var(--bg3);border:1px solid var(--border);color:var(--dim);font-size:7px">🛡️ Risk Tips</button>
          <button class="btn" onclick="qa('Stop loss strategy aaj ki volatility mein')" style="background:var(--bg3);border:1px solid var(--border);color:var(--dim);font-size:7px">⛔ SL Tips</button>
        </div>
      </div>

      <!-- LOGS -->
      <div id="tab-logs" class="tp">
        <div class="logbox" id="logBox"></div>
      </div>

      <!-- RISK -->
      <div id="tab-risk" class="tp">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">MAX DAILY LOSS (₹)</div><input class="inp" id="rMaxLoss" value="2000" style="width:100%"></div>
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">PROFIT TARGET (₹)</div><input class="inp" id="rMaxProfit" value="5000" style="width:100%"></div>
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">RISK PER TRADE (%)</div><input class="inp" id="rRisk" value="1.5" style="width:100%"></div>
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">MAX POSITIONS</div><input class="inp" id="rMaxPos" value="6" style="width:100%"></div>
        </div>
        <button class="btn bb" onclick="saveRisk()">SAVE RISK SETTINGS</button>
        <div style="margin-top:10px" id="riskMeter"></div>
      </div>

    </div>
  </div>

  <!-- RIGHT: POSITIONS -->
  <div class="right-panel">
    <div class="panel-hdr">
      <span>📂 POSITIONS</span>
      <span id="posCount" style="color:var(--accent)">0/6</span>
    </div>
    <div class="pos-list" id="posList">
      <div style="text-align:center;color:var(--dim);padding:20px;font-size:8px">No open positions</div>
    </div>
    <div class="ctrl-panel">
      <div style="font-size:7px;color:var(--dim);letter-spacing:1px;margin-bottom:5px">AUTO TOKEN STATUS</div>
      <div id="autoTokStat" style="font-size:8px;color:var(--green)">✅ Auto-refresh via API Key</div>
      <div style="margin-top:6px;font-size:7px;color:var(--dim)" id="dataSource">--</div>
      <div style="margin-top:4px;font-size:7px;color:var(--dim)" id="lastUpdate">--</div>
    </div>
  </div>

</div>

<script>
let D={};
let orKey=localStorage.getItem('or_key')||'';
let aiChat=[];

// Clock
setInterval(()=>{
  const n=new Date();
  document.getElementById('clockDisplay').textContent=
    n.toLocaleTimeString('en-IN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
},1000);

function sw(id,btn){
  document.querySelectorAll('.tp').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.getElementById('tab-'+id).classList.add('on');
  if(btn)btn.classList.add('on');
}

function isMarketOpen(){
  const n=new Date();if(n.getDay()===0||n.getDay()===6)return false;
  const t=n.getHours()*60+n.getMinutes();return t>=555&&t<=930;
}

async function refresh(){
  try{
    const r=await fetch('/api/state');D=await r.json();
    renderBadges();renderStats();renderMarketList();
    renderSigTable();renderPositions();renderHistory();
    renderLogs();renderRiskMeter();renderTicker();
    if(D.ai_analysis)document.getElementById('aiBox').textContent=D.ai_analysis;
    document.getElementById('dataSource').textContent='Source: '+(D.data_source||'—');
    document.getElementById('lastUpdate').textContent='Updated: '+(D.last_price_update||'—');
    document.getElementById('autoTokStat').textContent=D.api_key_set?'✅ Auto-refresh ACTIVE':'⚠️ Manual token mode';
    document.getElementById('autoTokStat').style.color=D.api_key_set?'var(--green)':'var(--yellow)';
  }catch(e){}
}

function renderBadges(){
  const mo=isMarketOpen();
  document.getElementById('hdrBdg').innerHTML=`
    <span class="bdg" style="border-color:${D.token_ok?'var(--green)':'var(--red)'};color:${D.token_ok?'var(--green)':'var(--red)'}">${D.token_ok?'🔑 TOKEN OK':'🔴 NO TOKEN'}</span>
    <span class="bdg" style="border-color:${D.running?'var(--green)':'var(--dim)'};color:${D.running?'var(--green)':'var(--dim)'}"><span class="dot ${D.running?'dg':'dr'}"></span>${D.running?'LIVE':'IDLE'}</span>
    <span class="bdg" style="border-color:${mo?'var(--green)':'var(--red)'};color:${mo?'var(--green)':'var(--red)'}">${mo?'🟢 NSE OPEN':'🔴 NSE CLOSED'}</span>
    <span class="bdg" style="border-color:var(--yellow);color:var(--yellow)">₹${Math.floor(D.funds||0).toLocaleString('en-IN')}</span>
    <span class="bdg" style="border-color:${D.sentiment==='BULLISH'?'var(--green)':D.sentiment==='BEARISH'?'var(--red)':'var(--yellow)'};color:${D.sentiment==='BULLISH'?'var(--green)':D.sentiment==='BEARISH'?'var(--red)':'var(--yellow)'}">${D.sentiment||'NEUTRAL'}</span>
  `;
  document.getElementById('mktSent').textContent=D.sentiment||'—';
  document.getElementById('mktSent').style.color=D.sentiment==='BULLISH'?'var(--green)':D.sentiment==='BEARISH'?'var(--red)':'var(--yellow)';
  document.getElementById('tokStat').textContent=D.token_status==='auto_refreshed'?'🔄 Auto':'✅ OK';
  document.getElementById('btnStart').style.display=D.running?'none':'inline-block';
  document.getElementById('btnStop').style.display=D.running?'inline-block':'none';
  document.getElementById('posCount').textContent=`${Object.keys(D.positions||{}).length}/${D.max_trades||6}`;
}

function renderStats(){
  const s=D.stats||{};const wr=s.trades>0?((s.wins/s.trades)*100).toFixed(0):0;
  document.getElementById('statsBar').innerHTML=[
    {l:'TODAY P&L',v:`₹${(s.today_pnl||0).toFixed(0)}`,c:s.today_pnl>=0?'var(--green)':'var(--red)',ss:`${s.today_trades||0} trades`},
    {l:'TOTAL P&L',v:`₹${(s.total_pnl||0).toFixed(0)}`,c:s.total_pnl>=0?'var(--green)':'var(--red)',ss:'All time'},
    {l:'WIN RATE',v:`${wr}%`,c:'var(--purple)',ss:`W:${s.wins||0} L:${s.losses||0}`},
    {l:'BEST TRADE',v:`₹${(s.best_trade||0).toFixed(0)}`,c:'var(--green)',ss:'Single trade'},
    {l:'WORST',v:`₹${(s.worst_trade||0).toFixed(0)}`,c:'var(--red)',ss:'Single trade'},
    {l:'STREAK',v:s.streak||0,c:(s.streak||0)>=0?'var(--green)':'var(--red)',ss:`Best:${s.max_streak||0}`},
    {l:'OPEN POS',v:Object.keys(D.positions||{}).length,c:'var(--cyan)',ss:`Max:${D.max_trades||6}`},
    {l:'DATA',v:D.data_source?.includes('Dhan')?'LIVE':'DELAYED',c:D.data_source?.includes('Dhan')?'var(--green)':'var(--yellow)',ss:D.last_price_update||'—'},
  ].map(x=>`<div class="stat-item"><div class="stat-lbl">${x.l}</div><div class="stat-val" style="color:${x.c}">${x.v}</div><div class="stat-sub">${x.ss}</div></div>`).join('');
}

function renderMarketList(){
  const sigs=D.signals||[];const prices=D.prices||{};
  if(!sigs.length&&!Object.keys(prices).length){document.getElementById('marketList').innerHTML='<div style="text-align:center;color:var(--dim);padding:20px;font-size:8px">Start bot for live data</div>';return;}
  document.getElementById('marketList').innerHTML=(sigs.length?sigs:Object.entries(prices).map(([sym,pd])=>({sym,price:pd.price||0,chg:pd.chg||0,action:'HOLD',conf:0}))).map(s=>`
    <div class="market-row">
      <div><div class="mr-sym">${s.sym}</div><div class="mr-sec">${s.sector||''}</div></div>
      <div class="mr-price">
        <div class="mr-ltp">₹${s.price?.toFixed(1)||'—'}</div>
        <div class="mr-chg" style="color:${(s.chg||0)>=0?'var(--green)':'var(--red)'}">${(s.chg||0)>=0?'+':''}${(s.chg||0).toFixed(2)}%</div>
        <span class="mr-sig ${s.action==='BUY'?'sig-b':s.action==='SELL'?'sig-s':'sig-h'}">${s.action}</span>
      </div>
    </div>`).join('');
}

function renderSigTable(){
  if(!D.signals||!D.signals.length)return;
  document.getElementById('sigTbl').innerHTML=D.signals.map(s=>`
    <tr>
      <td class="fw">${s.sym} <span style="font-size:6px;color:var(--dim)">${s.sector||''}</span></td>
      <td style="color:var(--yellow)">${s.price?.toFixed(2)||'—'}</td>
      <td style="color:${(s.chg||0)>=0?'var(--green)':'var(--red)'};font-weight:700">${(s.chg||0)>=0?'+':''}${(s.chg||0).toFixed(2)}%</td>
      <td style="color:var(--purple)">${(s.rsi||50).toFixed(0)}</td>
      <td style="color:${(s.macd||0)>0?'var(--green)':'var(--red)'}">${(s.macd||0)>0?'▲':'▼'}${Math.abs(s.macd||0).toFixed(3)}</td>
      <td style="color:var(--cyan)">${(s.indicators||{}).stoch?.toFixed(0)||'—'}</td>
      <td style="color:var(--orange);font-size:7px">${s.pattern||'—'}</td>
      <td><span style="padding:2px 6px;border-radius:2px;font-size:7px;font-weight:700;background:${s.action==='BUY'?'#001a0d':s.action==='SELL'?'#1a0008':'var(--muted)'};color:${s.action==='BUY'?'var(--green)':s.action==='SELL'?'var(--red)':'var(--dim)'};border:1px solid ${s.action==='BUY'?'#00ff9d30':s.action==='SELL'?'#ff306030':'var(--border)'}">${s.action}</span></td>
      <td style="color:var(--accent);font-weight:700">${s.conf?.toFixed(0)||0}%</td>
      <td style="color:var(--purple);font-size:7px">${s.used_strategy||'—'}</td>
      <td style="font-size:6px;color:${s.source?.includes('Dhan')?'var(--green)':'var(--yellow)'}">${s.source?.includes('Dhan')?'🟢LIVE':'🟡DLY'}</td>
    </tr>`).join('');
}

function renderPositions(){
  const pos=D.positions||{};const prices=D.prices||{};
  if(!Object.keys(pos).length){document.getElementById('posList').innerHTML='<div style="text-align:center;color:var(--dim);padding:20px;font-size:8px">No open positions</div>';return;}
  document.getElementById('posList').innerHTML=Object.values(pos).map(p=>{
    const cur=(prices[p.sym]||{}).price||p.entry;
    const pnl=p.side==='BUY'?(cur-p.entry)*p.qty:(p.entry-cur)*p.qty;
    const pct=((cur-p.entry)/p.entry*100*(p.side==='BUY'?1:-1));
    return `<div class="pos-card ${pnl>=0?'profit':'loss'}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
        <span class="pos-sym">${p.sym}</span>
        <span class="pos-pnl" style="color:${pnl>=0?'var(--green)':'var(--red)'}">₹${pnl.toFixed(0)}</span>
      </div>
      <div class="pos-info">
        <span style="color:${p.side==='BUY'?'var(--green)':'var(--red)'}">${p.side}</span>
        <span>x${p.qty}</span>
        <span>E:₹${p.entry.toFixed(0)}</span>
        <span style="color:var(--cyan)">L:₹${cur.toFixed(0)}</span>
      </div>
      <div class="pos-info" style="margin-top:2px">
        <span style="color:var(--red)">SL:₹${p.sl?.toFixed(0)}</span>
        <span style="color:var(--green)">T:₹${p.tgt?.toFixed(0)}</span>
        <span style="color:var(--dim)">${pct.toFixed(1)}%</span>
      </div>
      <div class="prog"><div class="prog-f" style="width:${Math.min(Math.abs(pct)*15,100)}%;background:${pnl>=0?'var(--green)':'var(--red)'}"></div></div>
    </div>`;}).join('');
}

function renderHistory(){
  if(!D.trades||!D.trades.length)return;
  document.getElementById('histTbl').innerHTML=D.trades.slice(0,30).map(t=>`
    <tr>
      <td style="color:var(--dim)">${t.time}</td>
      <td class="fw">${t.sym}</td>
      <td style="color:${t.side==='BUY'?'var(--green)':'var(--red)'};font-weight:700">${t.side}</td>
      <td>${t.qty}</td>
      <td style="color:var(--yellow)">₹${t.entry?.toFixed(2)}</td>
      <td style="color:var(--cyan)">₹${t.exit?.toFixed(2)}</td>
      <td class="fw" style="color:${t.pnl>=0?'var(--green)':'var(--red)'}">₹${t.pnl?.toFixed(2)}</td>
      <td style="color:var(--dim)">${t.rr||'—'}</td>
      <td style="color:var(--purple);font-size:7px">${t.strategy||'—'}</td>
      <td style="color:var(--dim);font-size:7px">${t.reason}</td>
    </tr>`).join('');
}

function renderLogs(){
  if(!D.logs||!D.logs.length)return;
  document.getElementById('logBox').innerHTML=D.logs.slice(0,60).map(l=>`
    <div class="l${l.level==='ERROR'?'e':l.level==='WARNING'?'w':l.level==='INFO'?'i':'t'}">[${l.time}] ${l.msg}</div>`).join('');
}

function renderRiskMeter(){
  const s=D.stats||{};const ml=D.max_loss||2000;const mp=D.max_profit||5000;
  const lossP=Math.abs(Math.min(0,s.today_pnl||0))/ml*100;
  const profP=Math.max(0,s.today_pnl||0)/mp*100;
  document.getElementById('riskMeter').innerHTML=`
    <div style="margin-bottom:8px"><div style="display:flex;justify-content:space-between;font-size:7px;color:var(--dim);margin-bottom:2px"><span>LOSS USAGE</span><span>₹${Math.abs(Math.min(0,s.today_pnl||0)).toFixed(0)}/₹${ml}</span></div>
    <div class="prog"><div class="prog-f" style="width:${Math.min(lossP,100)}%;background:${lossP>80?'var(--red)':lossP>50?'var(--yellow)':'var(--green)'}"></div></div></div>
    <div style="margin-bottom:8px"><div style="display:flex;justify-content:space-between;font-size:7px;color:var(--dim);margin-bottom:2px"><span>PROFIT PROGRESS</span><span>₹${Math.max(0,s.today_pnl||0).toFixed(0)}/₹${mp}</span></div>
    <div class="prog"><div class="prog-f" style="width:${Math.min(profP,100)}%;background:var(--green)"></div></div></div>
    <div style="font-size:8px;color:var(--dim)">Positions: <b style="color:var(--cyan)">${Object.keys(D.positions||{}).length}/${D.max_trades||6}</b> | Streak: <b style="color:${(s.streak||0)>=0?'var(--green)':'var(--red)'}">${s.streak||0}</b> | Errors: <b style="color:${(D.error_count||0)>5?'var(--red)':'var(--green)'}">${D.error_count||0}</b></div>`;
}

function renderTicker(){
  const sigs=D.signals||[];if(!sigs.length)return;
  const items=sigs.map(s=>`<span class="ticker-item"><span style="color:var(--text);font-weight:700">${s.sym}</span> <span style="color:var(--yellow)">₹${s.price?.toFixed(1)||'—'}</span> <span style="color:${(s.chg||0)>=0?'var(--green)':'var(--red)'}">${(s.chg||0)>=0?'▲':'▼'}${Math.abs(s.chg||0).toFixed(2)}%</span> <span style="color:${s.action==='BUY'?'var(--green)':s.action==='SELL'?'var(--red)':'var(--dim)'}">[${s.action}]</span></span>`).join('');
  document.getElementById('tickerInner').innerHTML=items+items;
}

// AI CHAT
async function askAI(){
  const inp=document.getElementById('aiInput');const msg=inp.value.trim();if(!msg)return;
  let key=orKey||localStorage.getItem('or_key');
  if(!key){key=prompt('OpenRouter API Key (free at openrouter.ai):');if(key){localStorage.setItem('or_key',key);orKey=key;}else return;}
  inp.value='';
  const box=document.getElementById('aiBox');
  box.innerHTML+=`<div style="color:var(--cyan);margin-top:6px">👤 ${msg}</div><div id="aiReply" style="color:#d0b0ff;margin-top:3px">⏳ Thinking...</div>`;
  box.scrollTop=box.scrollHeight;
  const ctx=`Signals:${(D.signals||[]).filter(s=>s.action!=='HOLD').slice(0,5).map(s=>`${s.sym}:${s.action}(${s.conf?.toFixed(0)}%)`).join(',')} PnL:₹${(D.stats||{}).today_pnl?.toFixed(0)||0} Sentiment:${D.sentiment||'NEUTRAL'}`;
  try{
    const r=await fetch('https://openrouter.ai/api/v1/chat/completions',{method:'POST',headers:{'Authorization':'Bearer '+key,'Content-Type':'application/json','HTTP-Referer':'https://dhan-quantum.onrender.com','X-Title':'Dhan Quantum v6.0'},body:JSON.stringify({model:'anthropic/claude-3-haiku',messages:[{role:'system',content:'Expert NSE trader. Hindi/Hinglish mein concise actionable advice.'},{role:'user',content:`Context: ${ctx}\nSawaal: ${msg}`}],max_tokens:400})});
    const d=await r.json();const reply=d.choices?.[0]?.message?.content||'Response nahi mila.';
    const el=document.getElementById('aiReply');if(el){el.textContent=reply;el.id='';}
  }catch(e){const el=document.getElementById('aiReply');if(el){el.textContent='Error: '+e.message;el.id='';}}
  box.scrollTop=box.scrollHeight;
}
function qa(q){document.getElementById('aiInput').value=q;askAI();}

// API CALLS
async function botCmd(a){
  await fetch('/api/bot/'+a,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({strategy:document.getElementById('selStrat').value,capital:parseInt(document.getElementById('inpCap').value)||5000,max_trades:parseInt(document.getElementById('inpMax').value)||6})});
  refresh();
}
async function saveConfig(){await botCmd('config');alert('Config saved! ✅');}
async function doRefresh(){await fetch('/api/prices/refresh',{method:'POST'});refresh();}
async function doFunds(){await fetch('/api/funds',{method:'POST'});setTimeout(refresh,2000);}
async function doSq(){if(!confirm('All positions square off karein?'))return;await fetch('/api/squareoff',{method:'POST'});refresh();}
async function forceRefresh(){await fetch('/api/token/refresh',{method:'POST'});document.getElementById('tokStat').textContent='Refreshing...';setTimeout(refresh,3000);}
async function saveToken(){
  const c=document.getElementById('inpCid').value.trim();const t=document.getElementById('inpTok').value.trim();
  if(!c){alert('Client ID required!');return;}
  await fetch('/api/token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:c,token:t})});
  document.getElementById('tokStat').textContent='Saved!';refresh();
}
async function saveRisk(){
  await fetch('/api/risk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({max_loss:parseInt(document.getElementById('rMaxLoss').value)||2000,max_profit:parseInt(document.getElementById('rMaxProfit').value)||5000,risk_pct:parseFloat(document.getElementById('rRisk').value)||1.5,max_trades:parseInt(document.getElementById('rMaxPos').value)||6})});
  alert('Risk settings saved! 🛡️');
}

refresh();
setInterval(refresh,4000);
</script>
</body>
</html>"""

@app.route('/')
def index():return render_template_string(DASHBOARD)

@app.route('/api/state')
def api_state():
    return jsonify({
        'running':STATE['running'],'token_ok':bool(CFG['token'] and CFG['client_id']),
        'token_status':STATE['token_status'],'api_key_set':bool(CFG['api_key'] and CFG['api_secret']),
        'funds':STATE['funds'],'stats':STATE['stats'],'positions':STATE['positions'],
        'trades':list(STATE['trades'])[:30],'logs':list(STATE['logs'])[:80],
        'signals':STATE['signals'],
        'prices':{k:{kk:vv for kk,vv in v.items() if kk not in ['closes','volume']} for k,v in STATE['prices'].items()},
        'last_scan':STATE['last_scan'],'ai_analysis':STATE['ai_analysis'],
        'sentiment':STATE['market_sentiment'],'max_trades':CFG['max_trades'],
        'max_loss':CFG['max_loss'],'max_profit':CFG['max_profit'],'strategy':CFG['strategy'],
        'error_count':STATE['error_count'],'data_source':STATE['data_source'],
        'last_price_update':STATE['last_price_update'],
    })

@app.route('/api/bot/<action>',methods=['POST'])
def api_bot(action):
    data=request.json or {}
    if action in ('start','config'):
        if data.get('strategy'):CFG['strategy']=data['strategy']
        if data.get('capital'):CFG['capital']=int(data['capital'])
        if data.get('max_trades'):CFG['max_trades']=int(data['max_trades'])
    if action=='start':
        STATE['running']=True
        add_log(f'🤖 BOT STARTED | {CFG["strategy"]} | ₹{CFG["capital"]} | Max:{CFG["max_trades"]}','INFO')
        telegram(f'🤖 <b>Dhan Quantum v6.0 STARTED!</b>\nStrategy:{CFG["strategy"]}\n₹{CFG["capital"]}/trade\nAuto Token:{"✅" if CFG["api_key"] else "⚠️"}')
        threading.Thread(target=fetch_all_prices,daemon=True).start()
        threading.Thread(target=scan,daemon=True).start()
    elif action=='stop':
        STATE['running']=False;add_log('⏹ Bot stopped','WARNING');telegram('⏹ Bot stopped.')
    return jsonify({'ok':True})

@app.route('/api/token',methods=['POST'])
def api_token():
    data=request.json or {}
    if data.get('token'):CFG['token']=data['token']
    if data.get('client_id'):CFG['client_id']=data['client_id']
    STATE['token_status']='manually_set';add_log('🔑 Token updated','INFO')
    threading.Thread(target=get_funds,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/token/refresh',methods=['POST'])
def api_tok_refresh():
    threading.Thread(target=check_token,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/prices/refresh',methods=['POST'])
def api_prices():
    threading.Thread(target=fetch_all_prices,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/funds',methods=['POST'])
def api_funds():
    threading.Thread(target=get_funds,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/squareoff',methods=['POST'])
def api_sq():
    threading.Thread(target=squareoff_all,daemon=True).start()
    return jsonify({'ok':True})

@app.route('/api/risk',methods=['POST'])
def api_risk():
    data=request.json or {}
    if data.get('max_loss'):CFG['max_loss']=int(data['max_loss'])
    if data.get('max_profit'):CFG['max_profit']=int(data['max_profit'])
    if data.get('risk_pct'):CFG['risk_pct']=float(data['risk_pct'])
    if data.get('max_trades'):CFG['max_trades']=int(data['max_trades'])
    return jsonify({'ok':True})

@app.route('/health')
def health():
    return jsonify({'status':'ok','version':'6.0-bloomberg','time':datetime.now().isoformat(),'running':STATE['running'],'token':STATE['token_status']})

def run_scheduler():
    schedule.every().day.at('08:30').do(lambda:threading.Thread(target=check_token,daemon=True).start())
    schedule.every().day.at('09:00').do(daily_reset)
    schedule.every().day.at('09:05').do(lambda:threading.Thread(target=get_funds,daemon=True).start())
    schedule.every().day.at('09:10').do(lambda:threading.Thread(target=fetch_all_prices,daemon=True).start())
    schedule.every().day.at('15:15').do(squareoff_all)
    schedule.every(1).minutes.do(lambda:threading.Thread(target=scan,daemon=True).start() if STATE['running'] else None)
    schedule.every(1).minutes.do(lambda:threading.Thread(target=fetch_dhan_ltp,daemon=True).start() if market_open() and CFG['token'] else None)
    schedule.every(5).minutes.do(lambda:threading.Thread(target=fetch_all_prices,daemon=True).start())
    schedule.every(15).minutes.do(lambda:threading.Thread(target=get_ai_analysis,daemon=True).start())
    schedule.every(6).hours.do(lambda:threading.Thread(target=check_token,daemon=True).start())
    add_log('⏱️ Scheduler active | Token@8:30 | Scan@1min | AI@15min','INFO')
    while True:
        try:schedule.run_pending()
        except Exception as e:add_log(f'Scheduler: {e}','WARNING')
        time.sleep(15)

if __name__=='__main__':
    log.info('━'*60)
    log.info('  DHAN QUANTUM TRADER v6.0 — BLOOMBERG EDITION')
    log.info('  Auto Token | Real-Time LTP | AI | 8 Strategies')
    log.info('  Built on Mobile 📱 — Made in India 🇮🇳')
    log.info('━'*60)
    if CFG['api_key'] and CFG['api_secret']:
        log.info('✅ API Key found — Auto token refresh ENABLED!')
        threading.Thread(target=check_token,daemon=True).start()
    elif CFG['token']:
        log.info('✅ Manual token');STATE['token_status']='manual'
    else:
        log.warning('⚠️ Set DHAN_CLIENT_ID + DHAN_TOKEN or DHAN_API_KEY+DHAN_API_SECRET')
    if CFG['client_id']:threading.Thread(target=fetch_all_prices,daemon=True).start()
    add_log('🚀 Dhan Quantum v6.0 Bloomberg Edition LIVE!','INFO')
    add_log(f'🔑 Auto Token: {"✅ ON" if CFG["api_key"] else "⚠️ Manual"}','INFO')
    threading.Thread(target=run_scheduler,daemon=True).start()
    PORT=int(os.environ.get('PORT',5000))
    log.info(f'🌐 http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0',port=PORT,debug=False,threaded=True)
