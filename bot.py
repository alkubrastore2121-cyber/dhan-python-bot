#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║    DHAN QUANTUM TRADER v7.0 — BLOOMBERG TERMINAL EDITION   ║
║    NSE Algo Bot | Manual Token + Telegram Reminder         ║
║    Real-Time Dhan Data | AI Powered | 8 Strategies         ║
╚══════════════════════════════════════════════════════════════╝

FIXES in v7.0:
  - Token: Honest manual system, no broken auto-refresh
  - Yahoo fallback REMOVED — sirf Dhan real-time data
  - Telegram reminder subah 8:00 AM — "Token update karo!"
  - Token expiry warning dashboard pe (24hr countdown)
  - Dashboard: Fully upgraded professional Bloomberg UI
  - UptimeRobot /ping endpoint added (server kabhi nahi soyega)
  - Better error messages & recovery
"""

import os, time, json, logging, threading, random
import requests, schedule, numpy as np
from datetime import datetime, time as dtime, timedelta
from collections import deque
from flask import Flask, jsonify, request, render_template_string

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('DhanQ7')

# ─── CONFIG ──────────────────────────────────────────────────────
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
    'token_set_at': None,   # datetime when token was last set
}

DHAN_API = 'https://api.dhan.co'
app = Flask(__name__)
app.secret_key = 'dhan-quantum-v7'

# ─── WATCHLIST ────────────────────────────────────────────────────
WATCHLIST = [
    {'sym': 'RELIANCE',   'id': '500325', 'sector': 'Energy'},
    {'sym': 'TCS',        'id': '532540', 'sector': 'IT'},
    {'sym': 'HDFCBANK',   'id': '500180', 'sector': 'Banking'},
    {'sym': 'INFY',       'id': '500209', 'sector': 'IT'},
    {'sym': 'ICICIBANK',  'id': '532174', 'sector': 'Banking'},
    {'sym': 'SBIN',       'id': '500112', 'sector': 'Banking'},
    {'sym': 'AXISBANK',   'id': '532215', 'sector': 'Banking'},
    {'sym': 'WIPRO',      'id': '507685', 'sector': 'IT'},
    {'sym': 'TATAMOTORS', 'id': '500570', 'sector': 'Auto'},
    {'sym': 'BAJFINANCE', 'id': '500034', 'sector': 'NBFC'},
    {'sym': 'ADANIENT',   'id': '512599', 'sector': 'Infra'},
    {'sym': 'KOTAKBANK',  'id': '500247', 'sector': 'Banking'},
    {'sym': 'MARUTI',     'id': '532500', 'sector': 'Auto'},
    {'sym': 'LTIM',       'id': '540005', 'sector': 'IT'},
    {'sym': 'BHARTIARTL', 'id': '532454', 'sector': 'Telecom'},
    {'sym': 'SUNPHARMA',  'id': '524715', 'sector': 'Pharma'},
    {'sym': 'TATASTEEL',  'id': '500470', 'sector': 'Metal'},
    {'sym': 'NTPC',       'id': '532555', 'sector': 'Power'},
    {'sym': 'HINDALCO',   'id': '500440', 'sector': 'Metal'},
    {'sym': 'POWERGRID',  'id': '532898', 'sector': 'Power'},
]

# ─── STRATEGIES ───────────────────────────────────────────────────
STRATS = {
    'SCALP':       {'sl': 0.30, 'tgt': 0.65, 'rlo': 30, 'rhi': 70, 'conf': 55},
    'MOMENTUM':    {'sl': 0.80, 'tgt': 2.00, 'rlo': 38, 'rhi': 62, 'conf': 58},
    'SWING':       {'sl': 1.50, 'tgt': 3.50, 'rlo': 30, 'rhi': 70, 'conf': 60},
    'BREAKOUT':    {'sl': 0.60, 'tgt': 1.80, 'rlo': 45, 'rhi': 55, 'conf': 65},
    'REVERSAL':    {'sl': 0.70, 'tgt': 1.80, 'rlo': 25, 'rhi': 75, 'conf': 62},
    'AGGRESSIVE':  {'sl': 0.50, 'tgt': 1.20, 'rlo': 35, 'rhi': 65, 'conf': 55},
    'CONSERVATIVE':{'sl': 1.20, 'tgt': 3.00, 'rlo': 35, 'rhi': 65, 'conf': 68},
    'AI_AUTO':     {'sl': 0.80, 'tgt': 2.00, 'rlo': 38, 'rhi': 62, 'conf': 58},
}

# ─── STATE ────────────────────────────────────────────────────────
STATE = {
    'running': False, 'positions': {}, 'trades': deque(maxlen=100),
    'logs': deque(maxlen=500), 'signals': [], 'prices': {},
    'funds': 0.0, 'last_scan': None, 'last_price_update': None,
    'ai_analysis': '', 'market_sentiment': 'NEUTRAL',
    'data_source': 'waiting', 'token_status': 'not_set',
    'token_age_hours': 0, 'token_expires_in': '—',
    'error_count': 0,
    'stats': {
        'trades': 0, 'wins': 0, 'losses': 0, 'today_pnl': 0.0,
        'total_pnl': 0.0, 'best_trade': 0.0, 'worst_trade': 0.0,
        'streak': 0, 'max_streak': 0, 'today_trades': 0
    },
}

# ─── HELPERS ─────────────────────────────────────────────────────
def add_log(msg, level='INFO'):
    now = datetime.now().strftime('%H:%M:%S')
    STATE['logs'].appendleft({'time': now, 'msg': msg, 'level': level})
    getattr(log, level.lower(), log.info)(msg)

def telegram(msg, urgent=False):
    if not CFG['tg_token'] or not CFG['tg_chat']:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{CFG['tg_token']}/sendMessage",
            json={'chat_id': CFG['tg_chat'],
                  'text': ('🚨 ' if urgent else '') + msg,
                  'parse_mode': 'HTML'},
            timeout=5
        )
    except:
        pass

def dhan_headers():
    return {
        'Content-Type': 'application/json',
        'access-token': CFG['token'],
        'client_id': CFG['client_id']
    }

def market_open():
    n = datetime.now()
    if n.weekday() >= 5:
        return False
    return dtime(9, 15) <= n.time() <= dtime(15, 30)

def trading_time():
    return dtime(9, 15) <= datetime.now().time() <= dtime(15, 0)

def token_age_hours():
    if not CFG['token_set_at']:
        return 99
    diff = datetime.now() - CFG['token_set_at']
    return diff.total_seconds() / 3600

def token_expires_in_str():
    h = token_age_hours()
    remaining = max(0, 24 - h)
    if remaining <= 0:
        return 'EXPIRED ⚠️'
    hrs = int(remaining)
    mins = int((remaining - hrs) * 60)
    if hrs == 0:
        return f'{mins}m ⚠️'
    return f'{hrs}h {mins}m'

# ─── TOKEN CHECK (no broken auto-refresh) ────────────────────────
def check_token():
    """Just verify if existing token is working."""
    if not CFG['token'] or not CFG['client_id']:
        STATE['token_status'] = 'not_set'
        return False
    try:
        r = requests.get(f'{DHAN_API}/fundlimit', headers=dhan_headers(), timeout=10)
        if r.status_code == 200:
            d = r.json()
            if d.get('availableBalance') is not None:
                STATE['token_status'] = 'valid'
                STATE['funds'] = float(d.get('availableBalance', 0))
                add_log(f'✅ Token valid | Funds: ₹{STATE["funds"]:,.0f}', 'INFO')
                return True
        if r.status_code == 401:
            STATE['token_status'] = 'expired'
            add_log('⚠️ Token EXPIRED! Dashboard mein naya token daalo.', 'WARNING')
            telegram('⚠️ <b>Token Expired!</b>\nDhan app se naya token copy karo aur dashboard mein daalo.\n\nSteps:\n1. Dhan app open karo\n2. Profile → API → Generate Token\n3. Dashboard mein paste karo', urgent=True)
            return False
        STATE['token_status'] = f'error_{r.status_code}'
        return False
    except Exception as e:
        add_log(f'Token check error: {e}', 'WARNING')
        return False

# ─── MORNING TOKEN REMINDER ───────────────────────────────────────
def morning_token_reminder():
    """8 AM reminder via Telegram to update token."""
    msg = (
        '🌅 <b>Good Morning! Dhan Token Update Karo</b>\n\n'
        'Aaj trading ke liye token update karna zaroori hai:\n\n'
        '1️⃣ Dhan App kholo\n'
        '2️⃣ Profile → My Account → Access Token\n'
        '3️⃣ Token copy karo\n'
        '4️⃣ Dashboard → Token bar mein paste karo → SAVE\n\n'
        '⏰ Market 9:15 AM pe khulti hai\n'
        '📊 Bot auto-start hoga token save hone ke baad'
    )
    telegram(msg)
    add_log('📲 Morning token reminder sent via Telegram', 'INFO')

# ─── PRICE ENGINE (Dhan only, no Yahoo) ──────────────────────────
def fetch_dhan_ltp():
    if not CFG['token'] or not CFG['client_id']:
        add_log('⚠️ Token nahi hai — prices nahi aa sakti', 'WARNING')
        STATE['data_source'] = 'No token ⚠️'
        return False
    try:
        r = requests.post(
            f"{DHAN_API}/v2/marketfeed/ltp",
            json={"NSE_EQ": [w['id'] for w in WATCHLIST]},
            headers=dhan_headers(),
            timeout=10
        )
        if r.status_code == 401:
            STATE['token_status'] = 'expired'
            STATE['data_source'] = 'Token expired ⚠️'
            add_log('⚠️ Token expired — naya token daalo!', 'WARNING')
            return False
        d = r.json()
        nse = (d.get('data') or d).get('NSE_EQ', {}) or d.get('NSE_EQ', {})
        upd = 0
        for w in WATCHLIST:
            sec = nse.get(w['id'], {})
            p = sec.get('last_price') or sec.get('ltp') or sec.get('lastPrice')
            if p and float(p) > 0:
                prev = STATE['prices'].get(w['sym'], {}).get('price', float(p))
                if w['sym'] not in STATE['prices']:
                    STATE['prices'][w['sym']] = {'closes': [], 'volume': []}
                STATE['prices'][w['sym']].update({
                    'price': float(p), 'prev': prev,
                    'chg': round(((float(p) - prev) / prev * 100) if prev else 0, 3),
                    'updated': datetime.now().strftime('%H:%M:%S'),
                    'source': 'DHAN_RT ✅'
                })
                STATE['prices'][w['sym']]['closes'].append(float(p))
                if len(STATE['prices'][w['sym']]['closes']) > 100:
                    STATE['prices'][w['sym']]['closes'].pop(0)
                upd += 1
        if upd > 0:
            STATE['data_source'] = f'Dhan Real-Time ✅ ({upd}/{len(WATCHLIST)})'
            STATE['last_price_update'] = datetime.now().strftime('%H:%M:%S')
            add_log(f'📡 LTP: {upd}/{len(WATCHLIST)} stocks updated', 'INFO')
            # Update market sentiment
            prices = STATE['prices']
            bull = sum(1 for p in prices.values() if p.get('chg', 0) > 0.1)
            bear = sum(1 for p in prices.values() if p.get('chg', 0) < -0.1)
            t = len(prices)
            STATE['market_sentiment'] = (
                'BULLISH' if bull > t * 0.65 else
                'BEARISH' if bear > t * 0.65 else 'NEUTRAL'
            )
            return True
        add_log('⚠️ LTP: 0 prices received — check security IDs', 'WARNING')
        return False
    except Exception as e:
        add_log(f'LTP error: {e}', 'WARNING')
        STATE['data_source'] = f'Error: {str(e)[:40]}'
        return False

# ─── TECHNICAL INDICATORS ─────────────────────────────────────────
def rsi(p, n=14):
    if len(p) < n + 1:
        return 50.0
    a = np.array(p[-n * 3:], dtype=float)
    d = np.diff(a)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.mean(g[:n])
    al = np.mean(l[:n])
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
    return round(100.0 if al == 0 else 100 - 100 / (1 + ag / al), 2)

def ema(p, n):
    if len(p) < n:
        return float(p[-1])
    a = np.array(p, dtype=float)
    k = 2 / (n + 1)
    e = float(np.mean(a[:n]))
    for x in a[n:]:
        e = float(x) * k + e * (1 - k)
    return round(e, 2)

def bb(p, n=20):
    if len(p) < n:
        v = float(p[-1])
        return round(v * 1.02, 2), round(v, 2), round(v * 0.98, 2)
    sl = np.array(p[-n:], dtype=float)
    m = float(np.mean(sl))
    s = float(np.std(sl))
    return round(m + 2 * s, 2), round(m, 2), round(m - 2 * s, 2)

def macd_calc(p):
    if len(p) < 26:
        return 0, 0, 0
    m = ema(p, 12) - ema(p, 26)
    return round(m, 4), round(m * 0.9, 4), round(m * 0.1, 4)

def stoch(p, n=14):
    if len(p) < n:
        return 50, 50
    a = p[-n:]
    lo = min(a)
    hi = max(a)
    if hi == lo:
        return 50, 50
    k = ((p[-1] - lo) / (hi - lo)) * 100
    return round(k, 1), round(k * 0.9, 1)

def detect_pattern(p):
    if len(p) < 5:
        return 'NONE'
    c = p[-5:]
    if c[-1] > c[-2] and c[-2] < c[-3]:
        return 'MORNING_STAR'
    if c[-1] < c[-2] and c[-2] > c[-3]:
        return 'EVENING_STAR'
    if all(c[i] > c[i - 1] for i in range(1, 5)):
        return 'UPTREND'
    if all(c[i] < c[i - 1] for i in range(1, 5)):
        return 'DOWNTREND'
    return 'NEUTRAL'

def pick_strategy(prices):
    if len(prices) < 20:
        return 'MOMENTUM'
    r = rsi(prices)
    mc, ms, mh = macd_calc(prices)
    mom = (prices[-1] - prices[-5]) / prices[-5] * 100 if len(prices) >= 5 else 0
    at = np.mean([abs(prices[i] - prices[i - 1]) for i in range(1, min(15, len(prices)))])
    vol = at / prices[-1] * 100 if prices[-1] else 1
    if vol > 1.5:
        return 'BREAKOUT' if mh > 0 else 'SCALP'
    if r < 30 or r > 70:
        return 'REVERSAL'
    if abs(mom) > 2:
        return 'MOMENTUM'
    if vol < 0.5:
        return 'CONSERVATIVE'
    return 'MOMENTUM'

def generate_signal(prices, strat_name=None):
    if strat_name is None:
        strat_name = CFG['strategy']
    if strat_name == 'AI_AUTO':
        strat_name = pick_strategy(prices)
    strat = STRATS.get(strat_name, STRATS['MOMENTUM'])
    if len(prices) < 15:
        return 'HOLD', 0, {}, [], strat_name
    cur = prices[-1]
    r = rsi(prices)
    e9 = ema(prices, 9)
    e21 = ema(prices, min(21, len(prices)))
    e50 = ema(prices, min(50, len(prices)))
    bbu, bbm, bbl = bb(prices)
    mc, ms, mh = macd_calc(prices)
    sk, sd = stoch(prices)
    vw = np.mean(prices[-20:]) if len(prices) >= 20 else cur
    at = np.mean([abs(prices[i] - prices[i - 1]) for i in range(1, min(15, len(prices)))])
    mom = (prices[-1] - prices[-5]) / prices[-5] * 100 if len(prices) >= 5 else 0
    pat = detect_pattern(prices)
    sup = min(prices[-20:]) if len(prices) >= 20 else cur * 0.98
    res = max(prices[-20:]) if len(prices) >= 20 else cur * 1.02

    bull = 0
    bear = 0
    reasons = []

    if r < strat['rlo']:
        bull += 28; reasons.append(f'RSI Oversold({r:.0f})')
    elif r < 45:
        bull += 10
    if r > strat['rhi']:
        bear += 28; reasons.append(f'RSI Overbought({r:.0f})')
    elif r > 55:
        bear += 10
    if e9 > e21:
        bull += 22; reasons.append('EMA9>21↑')
    else:
        bear += 22; reasons.append('EMA9<21↓')
    if cur > e50:
        bull += 15; reasons.append('Above EMA50')
    else:
        bear += 15; reasons.append('Below EMA50')
    if cur <= bbl:
        bull += 22; reasons.append('BB Lower🎯')
    if cur >= bbu:
        bear += 22; reasons.append('BB Upper🎯')
    if mc > 0 and mh > 0:
        bull += 18; reasons.append('MACD Bull↗')
    elif mc < 0 and mh < 0:
        bear += 18; reasons.append('MACD Bear↘')
    if cur > vw * 1.002:
        bull += 12; reasons.append('Above VWAP')
    elif cur < vw * 0.998:
        bear += 12; reasons.append('Below VWAP')
    if sk < 25:
        bull += 15; reasons.append('Stoch Oversold')
    if sk > 75:
        bear += 15; reasons.append('Stoch Overbought')
    if mom > 1.5:
        bull += 12; reasons.append(f'Mom+{mom:.1f}%')
    elif mom < -1.5:
        bear += 12; reasons.append(f'Mom{mom:.1f}%')
    if cur <= sup * 1.008:
        bull += 12; reasons.append('Near Support')
    if cur >= res * 0.992:
        bear += 12; reasons.append('Near Resistance')
    if 'MORNING_STAR' in pat or 'UPTREND' in pat:
        bull += 18; reasons.append(pat)
    if 'EVENING_STAR' in pat or 'DOWNTREND' in pat:
        bear += 18; reasons.append(pat)
    sent = STATE['market_sentiment']
    if sent == 'BULLISH':
        bull += 8
    elif sent == 'BEARISH':
        bear += 8

    total = bull + bear or 1
    conf = round(max(bull, bear) / total * 100, 1)
    inds = {
        'rsi': r, 'ema9': e9, 'ema21': e21,
        'bbu': bbu, 'bbm': bbm, 'bbl': bbl,
        'macd': mc, 'macd_hist': mh, 'vwap': round(vw, 2),
        'atr': round(at, 2), 'stoch': sk, 'momentum': round(mom, 2),
        'pattern': pat, 'support': round(sup, 2), 'resistance': round(res, 2)
    }
    if bull > bear and conf > strat['conf']:
        return 'BUY', conf, inds, reasons, strat_name
    if bear > bull and conf > strat['conf']:
        return 'SELL', conf, inds, reasons, strat_name
    return 'HOLD', conf, inds, reasons, strat_name

# ─── ORDER MANAGEMENT ─────────────────────────────────────────────
def place_order(sym, sec_id, side, qty, otype='MARKET', price=0.0, trigger=0.0):
    if not CFG['token'] or not CFG['client_id']:
        add_log('❌ Token nahi! Order place nahi ho sakta.', 'ERROR')
        return None
    payload = {
        'dhanClientId': CFG['client_id'],
        'transactionType': side,
        'exchangeSegment': 'NSE_EQ',
        'productType': 'INTRADAY',
        'orderType': otype,
        'validity': 'DAY',
        'tradingSymbol': sym,
        'securityId': str(sec_id),
        'quantity': int(qty),
        'price': round(float(price), 2),
        'triggerPrice': round(float(trigger), 2),
        'disclosedQuantity': 0,
        'afterMarketOrder': False,
        'amoTime': 'OPEN',
        'boProfitValue': 0,
        'boStopLossValue': 0,
    }
    for attempt in range(3):
        try:
            time.sleep(random.uniform(1, 3))
            r = requests.post(f'{DHAN_API}/orders', json=payload, headers=dhan_headers(), timeout=10)
            try:
                data = r.json()
            except:
                data = {'raw': r.text[:200]}
            oid = data.get('orderId') or (data.get('data') or {}).get('orderId')
            if oid:
                add_log(f'✅ {side} {sym} x{qty} | Order #{oid}', 'INFO')
                STATE['error_count'] = 0
                return oid
            if r.status_code == 401:
                STATE['token_status'] = 'expired'
                add_log('⚠️ Token expired during order!', 'WARNING')
                return None
            add_log(f'⚠️ Order failed {sym}: {str(data)[:120]}', 'WARNING')
            return None
        except requests.Timeout:
            time.sleep(3)
        except Exception as e:
            add_log(f'❌ Order error {sym}: {e}', 'ERROR')
            STATE['error_count'] += 1
            return None
    return None

def place_sl(sym, sec_id, side, qty, sl_price):
    lmt = sl_price * 0.994 if side == 'SELL' else sl_price * 1.006
    return place_order(sym, sec_id, side, qty, 'SL', round(lmt, 2), round(sl_price, 2))

def get_funds():
    try:
        r = requests.get(f'{DHAN_API}/fundlimit', headers=dhan_headers(), timeout=10)
        d = r.json()
        bal = float(d.get('availableBalance', 0))
        STATE['funds'] = bal
        add_log(f'💰 Available: ₹{bal:,.0f}', 'INFO')
        return bal
    except Exception as e:
        add_log(f'Funds error: {e}', 'WARNING')
        return STATE['funds']

def calc_qty(price, at, sl_pct):
    risk = CFG['capital'] * CFG['risk_pct'] / 100
    sl_amt = price * sl_pct / 100
    if sl_amt <= 0:
        sl_amt = at or price * 0.01
    return max(1, min(int(risk / sl_amt), int(CFG['capital'] / price)))

def update_trailing(sym, cur):
    if not CFG['trailing_sl'] or sym not in STATE['positions']:
        return
    pos = STATE['positions'][sym]
    strat = STRATS.get(pos.get('strategy', CFG['strategy']), STRATS['MOMENTUM'])
    if pos['side'] == 'BUY':
        new_sl = cur * (1 - strat['sl'] / 100)
        if new_sl > pos['sl']:
            pos['sl'] = round(new_sl, 2)
    else:
        new_sl = cur * (1 + strat['sl'] / 100)
        if new_sl < pos['sl']:
            pos['sl'] = round(new_sl, 2)

def close_pos(sym, reason, exit_price=None):
    if sym not in STATE['positions']:
        return
    pos = STATE['positions'][sym]
    if exit_price is None:
        exit_price = STATE['prices'].get(sym, {}).get('price', pos['entry'])
    pnl = round(
        (exit_price - pos['entry']) * pos['qty'] if pos['side'] == 'BUY'
        else (pos['entry'] - exit_price) * pos['qty'], 2
    )
    s = STATE['stats']
    s['today_pnl'] = round(s['today_pnl'] + pnl, 2)
    s['total_pnl'] = round(s['total_pnl'] + pnl, 2)
    s['trades'] += 1
    s['today_trades'] += 1
    if pnl > 0:
        s['wins'] += 1
        s['streak'] = max(0, s.get('streak', 0)) + 1
        s['max_streak'] = max(s.get('max_streak', 0), s['streak'])
        s['best_trade'] = max(s.get('best_trade', 0), pnl)
    else:
        s['losses'] += 1
        s['streak'] = min(0, s.get('streak', 0)) - 1
        s['worst_trade'] = min(s.get('worst_trade', 0), pnl)
    emoji = '✅' if pnl > 0 else '❌'
    add_log(f'{emoji} CLOSED {sym} | {reason} | ₹{pos["entry"]:.2f}→₹{exit_price:.2f} | PnL:₹{pnl:+.2f}', 'INFO')
    telegram(f'{emoji} <b>{sym} CLOSED</b>\n{reason}\nEntry: ₹{pos["entry"]:.2f} → Exit: ₹{exit_price:.2f}\nPnL: <b>₹{pnl:+.2f}</b>\nToday: ₹{s["today_pnl"]:+.2f}')
    STATE['trades'].appendleft({
        'sym': sym, 'side': pos['side'], 'qty': pos['qty'],
        'entry': pos['entry'], 'exit': exit_price, 'pnl': pnl,
        'reason': reason, 'time': datetime.now().strftime('%H:%M'),
        'strategy': pos.get('strategy', CFG['strategy']), 'rr': pos.get('rr', '—')
    })
    exit_side = 'SELL' if pos['side'] == 'BUY' else 'BUY'
    time.sleep(1)
    place_order(sym, pos['secId'], exit_side, pos['qty'])
    del STATE['positions'][sym]

# ─── MAIN SCAN LOOP ───────────────────────────────────────────────
def scan():
    if not STATE['running']:
        return
    if not market_open():
        if not STATE['positions']:
            add_log('🔴 Market closed — Standby mode', 'INFO')
        return
    s = STATE['stats']
    if s['today_pnl'] <= -CFG['max_loss']:
        add_log(f'🚨 MAX LOSS HIT ₹{CFG["max_loss"]}! Bot stopped.', 'WARNING')
        telegram(f'🚨 <b>Max Loss Hit!</b> ₹{abs(s["today_pnl"]):.0f} lost. Bot stopped.', urgent=True)
        STATE['running'] = False
        return
    if s['today_pnl'] >= CFG['max_profit']:
        add_log(f'🎯 PROFIT TARGET ₹{CFG["max_profit"]} hit! Bot stopped.', 'INFO')
        telegram(f'🎯 <b>Target Hit!</b> ₹{s["today_pnl"]:.0f} profit. Great day!')
        STATE['running'] = False
        return

    # Refresh prices on each scan
    if CFG['token']:
        fetch_dhan_ltp()

    add_log(f'🔍 Scan | {CFG["strategy"]} | Pos:{len(STATE["positions"])}/{CFG["max_trades"]} | PnL:₹{s["today_pnl"]:+.0f}', 'INFO')

    # Check existing positions
    for sym in list(STATE['positions'].keys()):
        pos = STATE['positions'][sym]
        cur = STATE['prices'].get(sym, {}).get('price', pos['entry'])
        if cur <= 0:
            continue
        update_trailing(sym, cur)
        if pos['side'] == 'BUY':
            if cur <= pos['sl']:
                close_pos(sym, '🛑 SL Hit', cur)
            elif cur >= pos['tgt']:
                close_pos(sym, '🎯 Target Hit', cur)
        else:
            if cur >= pos['sl']:
                close_pos(sym, '🛑 SL Hit', cur)
            elif cur <= pos['tgt']:
                close_pos(sym, '🎯 Target Hit', cur)

    if not trading_time():
        add_log('⏰ New entries paused (after 3 PM)', 'INFO')
        return

    # Scan for new entries
    signals = []
    for w in WATCHLIST:
        sym = w['sym']
        pd = STATE['prices'].get(sym, {})
        closes = pd.get('closes', [])
        price = pd.get('price', 0)
        if not closes or price <= 0:
            continue
        action, conf, inds, reasons, used = generate_signal(closes)
        signals.append({
            'sym': sym, 'price': price, 'chg': pd.get('chg', 0),
            'action': action, 'conf': conf, 'reasons': reasons[:4],
            'rsi': inds.get('rsi', 50), 'macd': inds.get('macd', 0),
            'pattern': inds.get('pattern', '—'), 'sector': w.get('sector', ''),
            'indicators': inds, 'used_strategy': used,
            'source': pd.get('source', '—')
        })
        threshold = STRATS.get(used, STRATS['MOMENTUM'])['conf']
        if (action != 'HOLD' and sym not in STATE['positions']
                and len(STATE['positions']) < CFG['max_trades']
                and conf > threshold):
            strat = STRATS.get(used, STRATS['MOMENTUM'])
            at = inds.get('atr', price * 0.01)
            qty = calc_qty(price, at, strat['sl'])
            sl = round(price * (1 - strat['sl'] / 100) if action == 'BUY' else price * (1 + strat['sl'] / 100), 2)
            tgt = round(price * (1 + strat['tgt'] / 100) if action == 'BUY' else price * (1 - strat['tgt'] / 100), 2)
            rr = round(abs(tgt - price) / abs(price - sl), 2) if price != sl else 0
            add_log(f'🚀 {action} {sym} x{qty} @ ₹{price:.2f} SL:{sl} Tgt:{tgt} RR:{rr} [{conf:.0f}%]', 'INFO')
            telegram(f'🚀 <b>{action} {sym}</b> x{qty} @ ₹{price:.2f}\nSL:₹{sl} Tgt:₹{tgt} RR:1:{rr}\nConf:{conf:.0f}% | {used}')
            oid = place_order(sym, w['id'], action, qty)
            if oid:
                STATE['positions'][sym] = {
                    'sym': sym, 'secId': w['id'], 'side': action,
                    'qty': qty, 'entry': price, 'sl': sl, 'tgt': tgt,
                    'conf': conf, 'oid': oid, 'rr': rr, 'strategy': used,
                    'time': datetime.now().strftime('%H:%M')
                }
                time.sleep(2)
                sl_side = 'SELL' if action == 'BUY' else 'BUY'
                threading.Thread(target=place_sl, args=(sym, w['id'], sl_side, qty, sl), daemon=True).start()

    STATE['signals'] = sorted(signals, key=lambda x: x['conf'], reverse=True)
    STATE['last_scan'] = datetime.now().strftime('%H:%M:%S')

def squareoff_all():
    if not STATE['positions']:
        return
    add_log('⏰ 3:15 PM Auto Square Off!', 'WARNING')
    telegram('⏰ <b>Auto Square Off — 3:15 PM</b>')
    for sym in list(STATE['positions'].keys()):
        close_pos(sym, '⏰ Auto Square Off')

def daily_reset():
    s = STATE['stats']
    s['today_pnl'] = 0.0
    s['today_trades'] = 0
    s['wins'] = 0
    s['losses'] = 0
    s['trades'] = 0
    STATE['error_count'] = 0
    add_log('🔄 New day! Stats reset. Token update karna mat bhoolo.', 'INFO')

def get_ai_analysis():
    if not CFG['openrouter']:
        return
    try:
        sigs = [s for s in STATE['signals'] if s['action'] != 'HOLD'][:5]
        sig_text = ', '.join([f"{s['sym']}:{s['action']}({s['conf']:.0f}%)" for s in sigs])
        s = STATE['stats']
        r = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={'Authorization': f'Bearer {CFG["openrouter"]}', 'Content-Type': 'application/json'},
            json={
                'model': 'mistralai/mistral-7b-instruct',
                'messages': [
                    {'role': 'system', 'content': 'Expert NSE intraday trader. 3 line Hindi/Hinglish mein concise analysis.'},
                    {'role': 'user', 'content': f'Signals:{sig_text} PnL:₹{s["today_pnl"]:.0f} Sentiment:{STATE["market_sentiment"]} Strategy:{CFG["strategy"]}'}
                ],
                'max_tokens': 200
            },
            timeout=15
        )
        STATE['ai_analysis'] = r.json()['choices'][0]['message']['content']
        add_log('🤖 AI analysis updated', 'INFO')
    except Exception as e:
        add_log(f'AI error: {e}', 'WARNING')

# ─── BLOOMBERG TERMINAL DASHBOARD ─────────────────────────────────
DASHBOARD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Dhan Quantum v7.0 — Bloomberg</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700;800&family=Orbitron:wght@700;900&display=swap');
:root{
  --bg:#000508;--bg2:#020c12;--bg3:#041018;
  --card:#030f18;--border:#0a2030;--border2:#0d2840;
  --accent:#00d4ff;--accent2:#0088bb;
  --green:#00ff9d;--red:#ff3060;--yellow:#ffd000;
  --purple:#c084fc;--orange:#fb923c;--cyan:#22d3ee;
  --text:#c8e8f8;--dim:#2a5070;--muted:#1a3850;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{font-family:'JetBrains Mono',monospace;background:var(--bg);color:var(--text);font-size:10px}
body::after{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,20,40,0.03) 2px,rgba(0,20,40,0.03) 4px);pointer-events:none;z-index:9999}

/* HEADER */
.hdr{background:linear-gradient(90deg,#000508,#020c12,#000508);border-bottom:2px solid #0a2030;padding:6px 12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;flex-shrink:0}
.logo-wrap{display:flex;align-items:center;gap:10px}
.logo-icon{width:34px;height:34px;background:linear-gradient(135deg,#00d4ff,#0055aa);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 0 20px #00d4ff40}
.logo-title{font-family:'Orbitron',monospace;font-size:13px;font-weight:900;color:var(--accent);letter-spacing:3px;text-shadow:0 0 20px #00d4ff60}
.logo-sub{font-size:7px;color:var(--dim);letter-spacing:1.5px;margin-top:1px}
.hdr-right{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.bdg{padding:3px 8px;border-radius:3px;font-size:7px;font-weight:700;border:1px solid;letter-spacing:0.5px}
.time-display{font-size:12px;color:var(--accent);font-weight:700;letter-spacing:2px;font-family:'Orbitron',monospace}

/* TOKEN EXPIRY BAR */
.tok-bar{background:var(--bg2);border-bottom:1px solid var(--border);padding:5px 12px;flex-shrink:0}
.tok-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tok-lbl{font-size:7px;color:var(--dim);letter-spacing:1px;font-weight:700}
.inp{padding:4px 8px;background:var(--bg3);border:1px solid var(--border2);border-radius:3px;color:var(--text);font-family:'JetBrains Mono',monospace;font-size:8px;outline:none;transition:border 0.2s}
.inp:focus{border-color:var(--accent);box-shadow:0 0 8px #00d4ff20}
.btn{padding:4px 10px;border:none;border-radius:3px;cursor:pointer;font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:700;letter-spacing:0.5px;transition:all 0.2s;text-transform:uppercase}
.btn:hover{filter:brightness(1.3);transform:translateY(-1px)}
.bg{background:linear-gradient(90deg,#004422,#00aa44);color:#fff;box-shadow:0 0 10px #00aa4430}
.br{background:linear-gradient(90deg,#440011,#aa0033);color:#fff}
.bb2{background:linear-gradient(90deg,#002244,#0055aa);color:#fff}
.bp{background:linear-gradient(90deg,#220044,#5500aa);color:#fff}
.bo{background:linear-gradient(90deg,#442200,#aa5500);color:#fff}
.bw{background:linear-gradient(90deg,#1a2030,#253040);color:var(--text);border:1px solid var(--border)}

/* TOKEN EXPIRY INDICATOR */
.tok-expiry{display:flex;align-items:center;gap:8px;padding:4px 10px;border-radius:4px;border:1px solid}
.tok-expiry.ok{background:#001a08;border-color:#00ff9d30;color:var(--green)}
.tok-expiry.warn{background:#1a1000;border-color:#ffd00030;color:var(--yellow)}
.tok-expiry.expired{background:#1a0008;border-color:#ff306030;color:var(--red)}

/* TICKER */
.ticker{background:#000;border-bottom:1px solid var(--border);padding:4px 0;overflow:hidden;white-space:nowrap;flex-shrink:0}
.ticker-inner{display:inline-block;animation:ticker 50s linear infinite}
@keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.ticker-item{display:inline-block;margin:0 24px;font-size:9px;font-weight:600}

/* MAIN LAYOUT */
.main{display:flex;height:calc(100vh - 155px);overflow:hidden}

/* LEFT PANEL */
.left-panel{width:250px;min-width:250px;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.panel-hdr{padding:7px 10px;background:var(--bg2);border-bottom:1px solid var(--border);font-size:8px;font-weight:700;color:var(--dim);letter-spacing:2px;display:flex;justify-content:space-between;align-items:center}
.market-list{flex:1;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
.market-row{display:flex;justify-content:space-between;align-items:center;padding:5px 10px;border-bottom:1px solid var(--muted);transition:background 0.1s;cursor:default}
.market-row:hover{background:var(--bg2)}
.mr-sym{font-size:9px;font-weight:700}
.mr-sec{font-size:7px;color:var(--dim);margin-top:1px}
.mr-ltp{font-size:9px;font-weight:700;color:var(--yellow);text-align:right}
.mr-chg{font-size:7px;font-weight:600;text-align:right}
.mr-sig{padding:1px 5px;border-radius:2px;font-size:7px;font-weight:700;margin-top:2px;display:inline-block}
.sig-b{background:#001a0d;color:var(--green);border:1px solid #00ff9d30}
.sig-s{background:#1a0008;color:var(--red);border:1px solid #ff306030}
.sig-h{background:var(--muted);color:var(--dim);border:1px solid var(--border)}

/* CENTER */
.center-panel{flex:1;display:flex;flex-direction:column;overflow:hidden}

/* STATS BAR */
.stats-bar{display:flex;gap:6px;padding:6px 8px;background:var(--bg2);border-bottom:1px solid var(--border);flex-wrap:wrap;flex-shrink:0;overflow-x:auto}
.stat-item{background:var(--card);border:1px solid var(--border);border-radius:4px;padding:5px 10px;min-width:88px;flex:1}
.stat-lbl{font-size:6px;color:var(--dim);letter-spacing:1.5px;font-weight:700;text-transform:uppercase;margin-bottom:2px}
.stat-val{font-size:16px;font-weight:800;line-height:1}
.stat-sub{font-size:6px;color:var(--dim);margin-top:2px}

/* CONTROLS */
.ctrl-row{padding:5px 8px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;gap:5px;flex-wrap:wrap;align-items:center;flex-shrink:0}

/* TABS */
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid var(--border);padding:0 8px;flex-shrink:0;overflow-x:auto}
.tab{padding:7px 12px;border:none;cursor:pointer;background:transparent;font-family:'JetBrains Mono',monospace;font-size:8px;font-weight:700;color:var(--dim);border-bottom:2px solid transparent;white-space:nowrap;letter-spacing:0.5px;transition:all 0.15s;text-transform:uppercase}
.tab.on{color:var(--accent);border-bottom-color:var(--accent);background:#001830}
.tab-content{flex:1;overflow-y:auto;padding:8px;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
.tp{display:none}.tp.on{display:block}

/* TABLE */
table{width:100%;border-collapse:collapse;font-size:8px}
th{padding:5px 8px;text-align:left;color:var(--dim);border-bottom:1px solid var(--border);font-weight:700;letter-spacing:0.5px;font-size:7px;text-transform:uppercase;background:var(--bg2);position:sticky;top:0;z-index:1}
td{padding:5px 8px;border-bottom:1px solid var(--muted)}
tr:hover td{background:#001828}
.fw{font-weight:700}

/* RIGHT PANEL */
.right-panel{width:240px;min-width:240px;border-left:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.pos-list{flex:1;overflow-y:auto;padding:6px;scrollbar-width:thin}
.pos-card{background:var(--card);border:1px solid var(--border);border-radius:5px;padding:9px;margin-bottom:6px;transition:border-color 0.3s}
.pos-card.profit{border-color:#00ff9d40;box-shadow:0 0 10px #00ff9d10}
.pos-card.loss{border-color:#ff306040;box-shadow:0 0 10px #ff306010}
.pos-sym{font-size:12px;font-weight:800;margin-bottom:3px}
.pos-info{display:flex;flex-wrap:wrap;gap:4px;font-size:7px;color:var(--dim)}
.pos-pnl{font-size:14px;font-weight:800}
.prog{height:3px;background:var(--border);border-radius:2px;margin-top:5px;overflow:hidden}
.prog-f{height:100%;border-radius:2px;transition:width 0.5s}

/* INFO PANEL */
.info-section{padding:8px;border-top:1px solid var(--border);background:var(--bg2)}

/* LOG */
.logbox{font-size:8px;line-height:2;padding:4px 0}
.li{color:var(--dim)}.ls{color:var(--green)}.le{color:var(--red)}.lw{color:var(--yellow)}.lt{color:var(--cyan)}

/* AI BOX */
.ai-box{background:#020008;border:1px solid #330055;border-radius:4px;padding:8px;font-size:8px;line-height:1.8;color:#d0b0ff;max-height:180px;overflow-y:auto}

/* GLOW */
@keyframes glow{0%,100%{box-shadow:0 0 5px #00d4ff20}50%{box-shadow:0 0 20px #00d4ff50}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.1}}
.dot{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:3px;vertical-align:middle}
.dg{background:var(--green);box-shadow:0 0 6px var(--green);animation:blink 1.5s infinite}
.dr{background:var(--red)}
.dy{background:var(--yellow);animation:blink 1s infinite}
.running-glow{animation:glow 2s infinite}

/* TOKEN WARNING BANNER */
.tok-warn-banner{background:linear-gradient(90deg,#1a0800,#2a1000,#1a0800);border-bottom:2px solid var(--yellow);padding:5px 12px;font-size:8px;color:var(--yellow);font-weight:700;letter-spacing:0.5px;text-align:center;display:none;flex-shrink:0}
.tok-warn-banner.show{display:block}

@media(max-width:768px){
  html,body{overflow:auto;height:auto}
  .main{flex-direction:column;height:auto;overflow:visible}
  .left-panel,.right-panel{width:100%;min-width:unset;border:none;border-bottom:1px solid var(--border);max-height:260px}
  .center-panel{overflow:visible}
  .tab-content{overflow:visible;max-height:none}
  .stats-bar{overflow-x:auto;flex-wrap:nowrap}
  .stat-item{min-width:80px}
  html,body{overflow-y:auto}
}
</style>
</head>
<body>

<!-- TOKEN EXPIRY WARNING BANNER -->
<div class="tok-warn-banner" id="tokWarnBanner">
  ⚠️ TOKEN EXPIRE HONE WALA HAI — Dashboard mein naya token daalo! Dhan App → Profile → Access Token
</div>

<!-- HEADER -->
<div class="hdr">
  <div class="logo-wrap">
    <div class="logo-icon">⚡</div>
    <div>
      <div class="logo-title">DHAN QUANTUM v7.0</div>
      <div class="logo-sub">NSE INTRADAY ALGO • REAL-TIME • AI POWERED • BLOOMBERG TERMINAL</div>
    </div>
  </div>
  <div class="hdr-right">
    <div class="time-display" id="clockDisplay">--:--:--</div>
    <div id="hdrBdg" style="display:flex;gap:4px;flex-wrap:wrap">
      <span class="bdg" style="border-color:#2a5070;color:#2a5070">⏳ LOADING</span>
    </div>
  </div>
</div>

<!-- TICKER -->
<div class="ticker">
  <div class="ticker-inner" id="tickerInner">
    <span style="color:var(--dim);margin:0 20px;font-size:9px">⏳ Waiting for market data... Token daalo aur bot start karo</span>
  </div>
</div>

<!-- TOKEN BAR -->
<div class="tok-bar">
  <div class="tok-row">
    <span class="tok-lbl">🔑 DHAN TOKEN:</span>
    <input class="inp" id="inpCid" placeholder="Client ID" style="width:90px">
    <input class="inp" id="inpTok" type="password" placeholder="Access Token (Dhan App se copy karo)" style="flex:1;min-width:160px">
    <button class="btn bb2" onclick="saveToken()">💾 SAVE</button>
    <button class="btn bw" onclick="checkToken()">✓ CHECK</button>
    <div class="tok-expiry" id="tokExpiry" style="border-color:var(--dim);color:var(--dim)">
      <span>⏳ Token set nahi</span>
    </div>
  </div>
</div>

<!-- MAIN -->
<div class="main">

  <!-- LEFT: WATCHLIST -->
  <div class="left-panel">
    <div class="panel-hdr">
      <span>📊 MARKET WATCH (20)</span>
      <span id="mktSent" style="color:var(--yellow);font-size:8px">—</span>
    </div>
    <div class="market-list" id="marketList">
      <div style="text-align:center;color:var(--dim);padding:30px 10px;font-size:8px;line-height:2">
        Token daalo → Save karo<br>Bot Start karo<br>Real-time prices aayenge
      </div>
    </div>
  </div>

  <!-- CENTER -->
  <div class="center-panel">

    <!-- STATS BAR -->
    <div class="stats-bar" id="statsBar"></div>

    <!-- CONTROL ROW -->
    <div class="ctrl-row">
      <button class="btn bg running-glow" id="btnStart" onclick="botCmd('start')">▶ START BOT</button>
      <button class="btn br" id="btnStop" onclick="botCmd('stop')" style="display:none">⏹ STOP</button>
      <select class="inp" id="selStrat" style="width:200px">
        <option value="MOMENTUM">⚡ Momentum (SL 0.8% | Tgt 2%)</option>
        <option value="SCALP">⚡ Scalp (SL 0.3% | Tgt 0.65%)</option>
        <option value="SWING">📈 Swing (SL 1.5% | Tgt 3.5%)</option>
        <option value="BREAKOUT">🚀 Breakout (SL 0.6% | Tgt 1.8%)</option>
        <option value="REVERSAL">🔄 Reversal (SL 0.7% | Tgt 1.8%)</option>
        <option value="AGGRESSIVE">🔥 Aggressive (SL 0.5% | Tgt 1.2%)</option>
        <option value="CONSERVATIVE">🛡️ Conservative (SL 1.2% | Tgt 3%)</option>
        <option value="AI_AUTO">🤖 AI Auto (Smart Pick)</option>
      </select>
      <input class="inp" type="number" id="inpCap" value="5000" placeholder="₹Capital" style="width:75px">
      <span style="color:var(--dim);font-size:8px">Max:</span>
      <input class="inp" type="number" id="inpMax" value="6" style="width:40px">
      <button class="btn bb2" onclick="saveConfig()">SAVE</button>
      <button class="btn bo" onclick="doSq()">⚠️ SQ.OFF</button>
      <button class="btn bw" onclick="doFunds()">💰 FUNDS</button>
    </div>

    <!-- TABS -->
    <div class="tabs">
      <button class="tab on" onclick="sw('signals',this)">🎯 SIGNALS</button>
      <button class="tab" onclick="sw('history',this)">📋 HISTORY</button>
      <button class="tab" onclick="sw('ai',this)">🤖 AI CHAT</button>
      <button class="tab" onclick="sw('logs',this)">📝 LOGS</button>
      <button class="tab" onclick="sw('risk',this)">🛡️ RISK</button>
      <button class="tab" onclick="sw('guide',this)">📖 GUIDE</button>
    </div>

    <div class="tab-content">

      <!-- SIGNALS -->
      <div id="tab-signals" class="tp on">
        <table>
          <thead><tr>
            <th>SYMBOL</th><th>LTP</th><th>CHG%</th><th>RSI</th>
            <th>MACD</th><th>STOCH</th><th>PATTERN</th>
            <th>SIGNAL</th><th>CONF</th><th>STRATEGY</th>
          </tr></thead>
          <tbody id="sigTbl">
            <tr><td colspan="10" style="text-align:center;color:var(--dim);padding:40px">
              Token daalo → Save → Bot Start karein — signals yahan aayenge
            </td></tr>
          </tbody>
        </table>
      </div>

      <!-- HISTORY -->
      <div id="tab-history" class="tp">
        <table>
          <thead><tr><th>TIME</th><th>SYM</th><th>SIDE</th><th>QTY</th><th>ENTRY</th><th>EXIT</th><th>P&L</th><th>RR</th><th>STRATEGY</th><th>REASON</th></tr></thead>
          <tbody id="histTbl">
            <tr><td colspan="10" style="text-align:center;color:var(--dim);padding:30px">Koi trades nahi abhi tak</td></tr>
          </tbody>
        </table>
      </div>

      <!-- AI CHAT -->
      <div id="tab-ai" class="tp">
        <div style="font-size:8px;color:var(--dim);margin-bottom:8px;letter-spacing:1px">🤖 AI TRADING INTELLIGENCE — OPENROUTER POWERED (free models available)</div>
        <div class="ai-box" id="aiBox">
          <span style="color:var(--dim)">// OpenRouter key Settings mein daalo. AI analysis 15 min mein auto-update hogi jab bot chal raha ho...</span>
        </div>
        <div style="margin-top:8px;display:flex;gap:6px">
          <input class="inp" id="aiInput" placeholder="Pucho: Aaj kya buy karein? Market outlook?" style="flex:1">
          <button class="btn bp" onclick="askAI()">ASK ➤</button>
        </div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px">
          <button class="btn bw" onclick="qa('Aaj market bullish hai ya bearish?')" style="font-size:7px">📊 Market View</button>
          <button class="btn bw" onclick="qa('Best intraday stocks aaj ke liye')" style="font-size:7px">🎯 Top Picks</button>
          <button class="btn bw" onclick="qa('Risk management tips NSE intraday')" style="font-size:7px">🛡️ Risk Tips</button>
          <button class="btn bw" onclick="qa('Stop loss strategy kya honi chahiye')" style="font-size:7px">⛔ SL Tips</button>
        </div>
        <div style="margin-top:10px;padding:8px;background:var(--bg3);border:1px solid var(--border);border-radius:4px">
          <div style="font-size:7px;color:var(--dim);margin-bottom:4px;letter-spacing:1px">🔑 OPENROUTER API KEY (free at openrouter.ai)</div>
          <div style="display:flex;gap:6px">
            <input class="inp" id="orKeyInput" type="password" placeholder="sk-or-v1-..." style="flex:1">
            <button class="btn bb2" onclick="saveOrKey()">SAVE</button>
          </div>
        </div>
      </div>

      <!-- LOGS -->
      <div id="tab-logs" class="tp">
        <div class="logbox" id="logBox"><span style="color:var(--dim)">Logs yahan dikhenge...</span></div>
      </div>

      <!-- RISK -->
      <div id="tab-risk" class="tp">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">MAX DAILY LOSS (₹)</div><input class="inp" id="rMaxLoss" value="2000" style="width:100%"></div>
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">PROFIT TARGET (₹)</div><input class="inp" id="rMaxProfit" value="5000" style="width:100%"></div>
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">RISK PER TRADE (%)</div><input class="inp" id="rRisk" value="1.5" style="width:100%"></div>
          <div><div style="font-size:7px;color:var(--dim);margin-bottom:3px;letter-spacing:1px">MAX POSITIONS</div><input class="inp" id="rMaxPos" value="6" style="width:100%"></div>
        </div>
        <button class="btn bb2" onclick="saveRisk()" style="width:100%">💾 SAVE RISK SETTINGS</button>
        <div style="margin-top:10px" id="riskMeter"></div>
      </div>

      <!-- GUIDE -->
      <div id="tab-guide" class="tp">
        <div style="max-width:600px;line-height:2">
          <div style="color:var(--accent);font-weight:700;font-size:10px;margin-bottom:12px;letter-spacing:2px">📖 DAILY SETUP GUIDE — TOKEN SYSTEM</div>

          <div style="background:var(--bg2);border:1px solid #ffd00030;border-radius:4px;padding:12px;margin-bottom:10px">
            <div style="color:var(--yellow);font-weight:700;font-size:9px;margin-bottom:8px">⚠️ TOKEN KI SACH: DHAN AUTO-REFRESH SUPPORT NAHI KARTA</div>
            <div style="color:var(--dim);font-size:8px;line-height:2">
              Koi bhi code token auto-refresh nahi kar sakta — ye Dhan ki official limitation hai.<br>
              Token 24 ghante ya trading session ke baad expire hota hai.<br>
              <b style="color:var(--yellow)">Roz subah ek baar manually update karna padega</b> — sirf 30 second ka kaam hai.
            </div>
          </div>

          <div style="background:var(--bg2);border:1px solid #00ff9d30;border-radius:4px;padding:12px;margin-bottom:10px">
            <div style="color:var(--green);font-weight:700;font-size:9px;margin-bottom:8px">✅ DAILY ROUTINE (1 BAAR KARO)</div>
            <div style="color:var(--text);font-size:8px;line-height:2.2">
              <b style="color:var(--accent)">Step 1:</b> Raat ko sone se pehle ya subah 8 AM tak<br>
              <b style="color:var(--accent)">Step 2:</b> Dhan App kholo → Profile icon → My Account<br>
              <b style="color:var(--accent)">Step 3:</b> "Access Token" ya "API Access" section dhundo<br>
              <b style="color:var(--accent)">Step 4:</b> Token copy karo (ya Generate karke copy karo)<br>
              <b style="color:var(--accent)">Step 5:</b> Upar Token bar mein paste karo → SAVE dabao<br>
              <b style="color:var(--accent)">Step 6:</b> ✓ CHECK dabao — "Token OK" dikhega<br>
              <b style="color:var(--accent)">Step 7:</b> Bot Start karo — market 9:15 pe khud kaam karega
            </div>
          </div>

          <div style="background:var(--bg2);border:1px solid #00d4ff30;border-radius:4px;padding:12px;margin-bottom:10px">
            <div style="color:var(--accent);font-weight:700;font-size:9px;margin-bottom:8px">📲 TELEGRAM REMINDER SETUP</div>
            <div style="color:var(--dim);font-size:8px;line-height:2">
              Subah 8 AM ko Telegram pe automatic reminder aayega agar setup kiya ho:<br>
              Environment variables mein daalo:<br>
              <code style="color:var(--cyan)">TELEGRAM_TOKEN=your_bot_token</code><br>
              <code style="color:var(--cyan)">TELEGRAM_CHAT=your_chat_id</code>
            </div>
          </div>

          <div style="background:var(--bg2);border:1px solid #00d4ff30;border-radius:4px;padding:12px">
            <div style="color:var(--accent);font-weight:700;font-size:9px;margin-bottom:8px">🌐 RENDER/UPTIMEROBOT SETUP (Server Sleep Fix)</div>
            <div style="color:var(--dim);font-size:8px;line-height:2">
              1. uptimerobot.com pe free account banao<br>
              2. "Add New Monitor" → HTTP(s) type<br>
              3. URL: <code style="color:var(--cyan)">https://YOUR-APP.onrender.com/ping</code><br>
              4. Interval: 5 minutes → Save<br>
              <b style="color:var(--green)">Ab server kabhi nahi soyega! ✅</b>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- RIGHT: POSITIONS -->
  <div class="right-panel">
    <div class="panel-hdr">
      <span>📂 OPEN POSITIONS</span>
      <span id="posCount" style="color:var(--accent);font-weight:800">0/6</span>
    </div>
    <div class="pos-list" id="posList">
      <div style="text-align:center;color:var(--dim);padding:30px 10px;font-size:8px;line-height:2">
        Koi open position nahi<br>Bot start hone ke baad<br>yahan dikhega
      </div>
    </div>
    <div class="info-section">
      <div style="font-size:7px;color:var(--dim);letter-spacing:1px;margin-bottom:5px">📡 DATA SOURCE</div>
      <div id="dataSource" style="font-size:8px;color:var(--text)">—</div>
      <div id="lastUpdate" style="font-size:7px;color:var(--dim);margin-top:3px">—</div>
      <div style="font-size:7px;color:var(--dim);letter-spacing:1px;margin-top:8px;margin-bottom:3px">⚙️ ENVIRONMENT</div>
      <div id="envStatus" style="font-size:7px;color:var(--dim)">—</div>
    </div>
  </div>

</div>

<script>
let D={};
let orKey=localStorage.getItem('or_key')||'';

// Clock + Market Status
setInterval(()=>{
  const n=new Date();
  document.getElementById('clockDisplay').textContent=
    n.toLocaleTimeString('en-IN',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
},1000);

function isMarketOpen(){
  const n=new Date();if(n.getDay()===0||n.getDay()===6)return false;
  const t=n.getHours()*60+n.getMinutes();return t>=555&&t<=930;
}

function sw(id,btn){
  document.querySelectorAll('.tp').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.getElementById('tab-'+id).classList.add('on');
  if(btn)btn.classList.add('on');
}

async function refresh(){
  try{
    const r=await fetch('/api/state');D=await r.json();
    renderAll();
  }catch(e){}
}

function renderAll(){
  renderBadges();renderStats();renderMarketList();
  renderSigTable();renderPositions();renderHistory();
  renderLogs();renderRiskMeter();renderTicker();
  renderTokenExpiry();
  if(D.ai_analysis&&D.ai_analysis.trim()){
    const box=document.getElementById('aiBox');
    if(!box.dataset.userChat)box.textContent=D.ai_analysis;
  }
  document.getElementById('dataSource').textContent=D.data_source||'—';
  document.getElementById('lastUpdate').textContent='Last: '+(D.last_price_update||'never');
  document.getElementById('mktSent').textContent=D.sentiment||'—';
  document.getElementById('mktSent').style.color=D.sentiment==='BULLISH'?'var(--green)':D.sentiment==='BEARISH'?'var(--red)':'var(--yellow)';
  document.getElementById('btnStart').style.display=D.running?'none':'inline-block';
  document.getElementById('btnStop').style.display=D.running?'inline-block':'none';
  document.getElementById('posCount').textContent=`${Object.keys(D.positions||{}).length}/${D.max_trades||6}`;
  document.getElementById('envStatus').textContent=`TG:${D.tg_set?'✅':'❌'} OR:${D.or_set?'✅':'❌'}`;
}

function renderTokenExpiry(){
  const el=document.getElementById('tokExpiry');
  const banner=document.getElementById('tokWarnBanner');
  const expStr=D.token_expires_in||'—';
  const status=D.token_status||'not_set';
  if(status==='not_set'){
    el.className='tok-expiry';el.style.borderColor='var(--dim)';el.style.color='var(--dim)';
    el.innerHTML='⏳ Token set nahi — daalo!';
    banner.classList.remove('show');
  } else if(status==='expired'||expStr.includes('EXPIRED')){
    el.className='tok-expiry expired';
    el.innerHTML='⚠️ TOKEN EXPIRED — Update karo!';
    banner.classList.add('show');
  } else if(expStr.includes('⚠️')||expStr.startsWith('0h')||expStr.match(/^\d+m/)){
    el.className='tok-expiry warn';
    el.innerHTML=`⏰ Expires in: ${expStr}`;
    banner.classList.add('show');
  } else {
    el.className='tok-expiry ok';
    el.innerHTML=`✅ Valid — Expires in ${expStr}`;
    banner.classList.remove('show');
  }
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
}

function renderStats(){
  const s=D.stats||{};const wr=s.trades>0?((s.wins/s.trades)*100).toFixed(0):0;
  document.getElementById('statsBar').innerHTML=[
    {l:'TODAY P&L',v:`₹${(s.today_pnl||0).toFixed(0)}`,c:(s.today_pnl||0)>=0?'var(--green)':'var(--red)',ss:`${s.today_trades||0} trades`},
    {l:'TOTAL P&L',v:`₹${(s.total_pnl||0).toFixed(0)}`,c:(s.total_pnl||0)>=0?'var(--green)':'var(--red)',ss:'All time'},
    {l:'WIN RATE',v:`${wr}%`,c:'var(--purple)',ss:`W:${s.wins||0} L:${s.losses||0}`},
    {l:'BEST',v:`₹${(s.best_trade||0).toFixed(0)}`,c:'var(--green)',ss:'Single trade'},
    {l:'WORST',v:`₹${(s.worst_trade||0).toFixed(0)}`,c:'var(--red)',ss:'Single trade'},
    {l:'STREAK',v:s.streak||0,c:(s.streak||0)>=0?'var(--green)':'var(--red)',ss:`Best:${s.max_streak||0}`},
    {l:'POSITIONS',v:Object.keys(D.positions||{}).length,c:'var(--cyan)',ss:`Max:${D.max_trades||6}`},
    {l:'ERRORS',v:D.error_count||0,c:(D.error_count||0)>5?'var(--red)':'var(--dim)',ss:'Total'},
  ].map(x=>`<div class="stat-item"><div class="stat-lbl">${x.l}</div><div class="stat-val" style="color:${x.c}">${x.v}</div><div class="stat-sub">${x.ss}</div></div>`).join('');
}

function renderMarketList(){
  const sigs=D.signals||[];const prices=D.prices||{};
  const items=sigs.length?sigs:Object.entries(prices).map(([sym,pd])=>({sym,price:pd.price||0,chg:pd.chg||0,action:'HOLD',conf:0,sector:''}));
  if(!items.length){
    document.getElementById('marketList').innerHTML='<div style="text-align:center;color:var(--dim);padding:30px 10px;font-size:8px;line-height:2">Token daalo<br>Bot start karo<br>Data aayega</div>';
    return;
  }
  document.getElementById('marketList').innerHTML=items.map(s=>`
    <div class="market-row">
      <div><div class="mr-sym">${s.sym}</div><div class="mr-sec">${s.sector||''}</div></div>
      <div>
        <div class="mr-ltp">₹${(s.price||0).toFixed(1)}</div>
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
      <td style="color:var(--yellow);font-weight:700">₹${(s.price||0).toFixed(2)}</td>
      <td style="color:${(s.chg||0)>=0?'var(--green)':'var(--red)'};font-weight:700">${(s.chg||0)>=0?'+':''}${(s.chg||0).toFixed(2)}%</td>
      <td style="color:var(--purple)">${(s.rsi||50).toFixed(0)}</td>
      <td style="color:${(s.macd||0)>0?'var(--green)':'var(--red)'}">${(s.macd||0)>0?'▲':'▼'}${Math.abs(s.macd||0).toFixed(3)}</td>
      <td style="color:var(--cyan)">${((s.indicators||{}).stoch||50).toFixed(0)}</td>
      <td style="color:var(--orange);font-size:7px">${s.pattern||'—'}</td>
      <td><span style="padding:2px 6px;border-radius:2px;font-size:7px;font-weight:700;background:${s.action==='BUY'?'#001a0d':s.action==='SELL'?'#1a0008':'var(--muted)'};color:${s.action==='BUY'?'var(--green)':s.action==='SELL'?'var(--red)':'var(--dim)'};border:1px solid ${s.action==='BUY'?'#00ff9d30':s.action==='SELL'?'#ff306030':'var(--border)'}">${s.action}</span></td>
      <td style="color:var(--accent);font-weight:700">${(s.conf||0).toFixed(0)}%</td>
      <td style="color:var(--purple);font-size:7px">${s.used_strategy||'—'}</td>
    </tr>`).join('');
}

function renderPositions(){
  const pos=D.positions||{};const prices=D.prices||{};
  if(!Object.keys(pos).length){
    document.getElementById('posList').innerHTML='<div style="text-align:center;color:var(--dim);padding:30px 10px;font-size:8px;line-height:2">Koi open position nahi</div>';
    return;
  }
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
        <span style="color:${p.side==='BUY'?'var(--green)':'var(--red)'}">● ${p.side}</span>
        <span>x${p.qty}</span>
        <span>E:₹${(p.entry||0).toFixed(0)}</span>
        <span style="color:var(--cyan)">L:₹${cur.toFixed(0)}</span>
      </div>
      <div class="pos-info" style="margin-top:3px">
        <span style="color:var(--red)">SL:₹${(p.sl||0).toFixed(0)}</span>
        <span style="color:var(--green)">T:₹${(p.tgt||0).toFixed(0)}</span>
        <span style="color:${pct>=0?'var(--green)':'var(--red)'}">${pct.toFixed(2)}%</span>
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
      <td style="color:var(--yellow)">₹${(t.entry||0).toFixed(2)}</td>
      <td style="color:var(--cyan)">₹${(t.exit||0).toFixed(2)}</td>
      <td class="fw" style="color:${(t.pnl||0)>=0?'var(--green)':'var(--red)'}">₹${(t.pnl||0).toFixed(2)}</td>
      <td style="color:var(--dim)">${t.rr||'—'}</td>
      <td style="color:var(--purple);font-size:7px">${t.strategy||'—'}</td>
      <td style="color:var(--dim);font-size:7px">${t.reason||'—'}</td>
    </tr>`).join('');
}

function renderLogs(){
  if(!D.logs||!D.logs.length)return;
  document.getElementById('logBox').innerHTML=D.logs.slice(0,80).map(l=>`
    <div class="l${l.level==='ERROR'?'e':l.level==='WARNING'?'w':'i'}">[${l.time}] ${l.msg}</div>`).join('');
}

function renderRiskMeter(){
  const s=D.stats||{};const ml=D.max_loss||2000;const mp=D.max_profit||5000;
  const lossP=Math.abs(Math.min(0,s.today_pnl||0))/ml*100;
  const profP=Math.max(0,s.today_pnl||0)/mp*100;
  document.getElementById('riskMeter').innerHTML=`
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:7px;color:var(--dim);margin-bottom:3px">
        <span>LOSS RISK</span><span style="color:${lossP>80?'var(--red)':'var(--dim)'}">₹${Math.abs(Math.min(0,s.today_pnl||0)).toFixed(0)} / ₹${ml}</span>
      </div>
      <div class="prog"><div class="prog-f" style="width:${Math.min(lossP,100)}%;background:${lossP>80?'var(--red)':lossP>50?'var(--yellow)':'var(--green)'}"></div></div>
    </div>
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:7px;color:var(--dim);margin-bottom:3px">
        <span>PROFIT PROGRESS</span><span style="color:var(--green)">₹${Math.max(0,s.today_pnl||0).toFixed(0)} / ₹${mp}</span>
      </div>
      <div class="prog"><div class="prog-f" style="width:${Math.min(profP,100)}%;background:var(--green)"></div></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:8px">
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:3px;padding:5px">
        <div style="color:var(--dim);font-size:7px">Positions</div>
        <div style="color:var(--cyan);font-weight:700">${Object.keys(D.positions||{}).length} / ${D.max_trades||6}</div>
      </div>
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:3px;padding:5px">
        <div style="color:var(--dim);font-size:7px">Win Streak</div>
        <div style="color:${(s.streak||0)>=0?'var(--green)':'var(--red)'};font-weight:700">${s.streak||0}</div>
      </div>
    </div>`;
}

function renderTicker(){
  const sigs=D.signals||[];if(!sigs.length)return;
  const items=sigs.map(s=>`<span class="ticker-item"><b style="color:var(--text)">${s.sym}</b> <span style="color:var(--yellow)">₹${(s.price||0).toFixed(1)}</span> <span style="color:${(s.chg||0)>=0?'var(--green)':'var(--red)'}">${(s.chg||0)>=0?'▲':'▼'}${Math.abs(s.chg||0).toFixed(2)}%</span> <span style="color:${s.action==='BUY'?'var(--green)':s.action==='SELL'?'var(--red)':'var(--dim)'}">[${s.action} ${(s.conf||0).toFixed(0)}%]</span></span>`).join('');
  document.getElementById('tickerInner').innerHTML=items+items;
}

// AI Chat
async function askAI(){
  const inp=document.getElementById('aiInput');const msg=inp.value.trim();if(!msg)return;
  let key=orKey||localStorage.getItem('or_key');
  if(!key){alert('OpenRouter key daalo AI tab mein!');return;}
  inp.value='';
  const box=document.getElementById('aiBox');
  box.dataset.userChat='1';
  box.innerHTML+=(box.innerHTML?'<hr style="border-color:var(--border);margin:6px 0">':'')+`<div style="color:var(--cyan)">👤 ${msg}</div><div id="aiReply" style="color:#d0b0ff;margin-top:3px">⏳ Thinking...</div>`;
  box.scrollTop=box.scrollHeight;
  const ctx=`Signals:${(D.signals||[]).filter(s=>s.action!=='HOLD').slice(0,5).map(s=>`${s.sym}:${s.action}(${(s.conf||0).toFixed(0)}%)`).join(',')} PnL:₹${(D.stats||{}).today_pnl?.toFixed(0)||0} Sentiment:${D.sentiment||'NEUTRAL'}`;
  try{
    const r=await fetch('https://openrouter.ai/api/v1/chat/completions',{
      method:'POST',
      headers:{'Authorization':'Bearer '+key,'Content-Type':'application/json','HTTP-Referer':'https://dhan-quantum.onrender.com'},
      body:JSON.stringify({model:'mistralai/mistral-7b-instruct',messages:[
        {role:'system',content:'Expert NSE intraday trader. Hindi/Hinglish mein concise actionable advice.'},
        {role:'user',content:`Context: ${ctx}\nSawaal: ${msg}`}
      ],max_tokens:400})
    });
    const d=await r.json();
    const reply=d.choices?.[0]?.message?.content||'Response nahi mila.';
    const el=document.getElementById('aiReply');if(el){el.textContent=reply;el.id='';}
  }catch(e){
    const el=document.getElementById('aiReply');if(el){el.textContent='Error: '+e.message;el.id='';}
  }
  box.scrollTop=box.scrollHeight;
}
function qa(q){document.getElementById('aiInput').value=q;askAI();}

function saveOrKey(){
  const k=document.getElementById('orKeyInput').value.trim();
  if(k){localStorage.setItem('or_key',k);orKey=k;alert('OpenRouter key saved! ✅');}
}

// API Calls
async function botCmd(a){
  await fetch('/api/bot/'+a,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({strategy:document.getElementById('selStrat').value,capital:parseInt(document.getElementById('inpCap').value)||5000,max_trades:parseInt(document.getElementById('inpMax').value)||6})});
  refresh();
}
async function saveConfig(){await botCmd('config');alert('Config saved! ✅');}
async function doSq(){if(!confirm('Sab positions square off karein?'))return;await fetch('/api/squareoff',{method:'POST'});refresh();}
async function doFunds(){await fetch('/api/funds',{method:'POST'});setTimeout(refresh,2000);}
async function saveToken(){
  const c=document.getElementById('inpCid').value.trim();
  const t=document.getElementById('inpTok').value.trim();
  if(!c||!t){alert('Client ID aur Token dono required hain!');return;}
  await fetch('/api/token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:c,token:t})});
  setTimeout(refresh,1000);
}
async function checkToken(){
  await fetch('/api/token/check',{method:'POST'});
  setTimeout(refresh,2000);
}
async function saveRisk(){
  await fetch('/api/risk',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({max_loss:parseInt(document.getElementById('rMaxLoss').value)||2000,max_profit:parseInt(document.getElementById('rMaxProfit').value)||5000,risk_pct:parseFloat(document.getElementById('rRisk').value)||1.5,max_trades:parseInt(document.getElementById('rMaxPos').value)||6})});
  alert('Risk settings saved! 🛡️');
}

// Init
if(orKey)document.getElementById('orKeyInput').value='••••••••';
refresh();
setInterval(refresh,4000);
</script>
</body>
</html>"""

# ─── FLASK ROUTES ──────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(DASHBOARD)

@app.route('/ping')  # UptimeRobot ke liye — server kabhi nahi soyega
def ping():
    return 'OK', 200

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok', 'version': '7.0',
        'time': datetime.now().isoformat(),
        'running': STATE['running'],
        'token': STATE['token_status'],
        'market_open': market_open()
    })

@app.route('/api/state')
def api_state():
    return jsonify({
        'running': STATE['running'],
        'token_ok': bool(CFG['token'] and CFG['client_id'] and STATE['token_status'] == 'valid'),
        'token_status': STATE['token_status'],
        'token_expires_in': token_expires_in_str(),
        'funds': STATE['funds'],
        'stats': STATE['stats'],
        'positions': STATE['positions'],
        'trades': list(STATE['trades'])[:30],
        'logs': list(STATE['logs'])[:80],
        'signals': STATE['signals'],
        'prices': {k: {kk: vv for kk, vv in v.items() if kk not in ['closes', 'volume']}
                   for k, v in STATE['prices'].items()},
        'last_scan': STATE['last_scan'],
        'ai_analysis': STATE['ai_analysis'],
        'sentiment': STATE['market_sentiment'],
        'max_trades': CFG['max_trades'],
        'max_loss': CFG['max_loss'],
        'max_profit': CFG['max_profit'],
        'strategy': CFG['strategy'],
        'error_count': STATE['error_count'],
        'data_source': STATE['data_source'],
        'last_price_update': STATE['last_price_update'],
        'tg_set': bool(CFG['tg_token'] and CFG['tg_chat']),
        'or_set': bool(CFG['openrouter']),
    })

@app.route('/api/bot/<action>', methods=['POST'])
def api_bot(action):
    data = request.json or {}
    if action in ('start', 'config'):
        if data.get('strategy'): CFG['strategy'] = data['strategy']
        if data.get('capital'): CFG['capital'] = int(data['capital'])
        if data.get('max_trades'): CFG['max_trades'] = int(data['max_trades'])
    if action == 'start':
        if not CFG['token'] or not CFG['client_id']:
            return jsonify({'ok': False, 'error': 'Token aur Client ID pehle daalo!'})
        STATE['running'] = True
        add_log(f'🤖 BOT STARTED | {CFG["strategy"]} | ₹{CFG["capital"]} | Max:{CFG["max_trades"]}', 'INFO')
        telegram(f'🤖 <b>Dhan Quantum v7.0 STARTED!</b>\nStrategy: {CFG["strategy"]}\nCapital: ₹{CFG["capital"]}/trade\nMax Positions: {CFG["max_trades"]}')
        threading.Thread(target=fetch_dhan_ltp, daemon=True).start()
        threading.Thread(target=scan, daemon=True).start()
    elif action == 'stop':
        STATE['running'] = False
        add_log('⏹ Bot stopped by user', 'WARNING')
        telegram('⏹ Bot stopped.')
    return jsonify({'ok': True})

@app.route('/api/token', methods=['POST'])
def api_token():
    data = request.json or {}
    if data.get('token'): CFG['token'] = data['token']
    if data.get('client_id'): CFG['client_id'] = data['client_id']
    CFG['token_set_at'] = datetime.now()
    STATE['token_status'] = 'checking'
    add_log('🔑 Token updated — checking validity...', 'INFO')
    threading.Thread(target=check_token, daemon=True).start()
    threading.Thread(target=get_funds, daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/token/check', methods=['POST'])
def api_token_check():
    threading.Thread(target=check_token, daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/funds', methods=['POST'])
def api_funds():
    threading.Thread(target=get_funds, daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/squareoff', methods=['POST'])
def api_sq():
    threading.Thread(target=squareoff_all, daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/risk', methods=['POST'])
def api_risk():
    data = request.json or {}
    if data.get('max_loss'): CFG['max_loss'] = int(data['max_loss'])
    if data.get('max_profit'): CFG['max_profit'] = int(data['max_profit'])
    if data.get('risk_pct'): CFG['risk_pct'] = float(data['risk_pct'])
    if data.get('max_trades'): CFG['max_trades'] = int(data['max_trades'])
    return jsonify({'ok': True})

# ─── SCHEDULER ────────────────────────────────────────────────────
def run_scheduler():
    schedule.every().day.at('08:00').do(morning_token_reminder)
    schedule.every().day.at('09:00').do(daily_reset)
    schedule.every().day.at('09:05').do(lambda: threading.Thread(target=check_token, daemon=True).start())
    schedule.every().day.at('09:05').do(lambda: threading.Thread(target=get_funds, daemon=True).start())
    schedule.every().day.at('09:10').do(lambda: threading.Thread(target=fetch_dhan_ltp, daemon=True).start())
    schedule.every().day.at('15:15').do(squareoff_all)
    schedule.every(1).minutes.do(lambda: threading.Thread(target=scan, daemon=True).start() if STATE['running'] else None)
    schedule.every(2).minutes.do(lambda: threading.Thread(target=fetch_dhan_ltp, daemon=True).start() if market_open() and CFG['token'] else None)
    schedule.every(15).minutes.do(lambda: threading.Thread(target=get_ai_analysis, daemon=True).start())
    schedule.every(6).hours.do(lambda: threading.Thread(target=check_token, daemon=True).start())
    add_log('⏱️ Scheduler active | Morning reminder@8AM | Scan@1min | AI@15min', 'INFO')
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            add_log(f'Scheduler error: {e}', 'WARNING')
        time.sleep(15)

# ─── STARTUP ──────────────────────────────────────────────────────
if __name__ == '__main__':
    log.info('━' * 60)
    log.info('  DHAN QUANTUM TRADER v7.0 — BLOOMBERG TERMINAL')
    log.info('  Manual Token + Morning Reminder | Real-Time | AI')
    log.info('  /ping endpoint for UptimeRobot (server stays awake)')
    log.info('━' * 60)

    if CFG['token'] and CFG['client_id']:
        CFG['token_set_at'] = datetime.now()
        log.info('✅ Token found in environment variables')
        threading.Thread(target=check_token, daemon=True).start()
        threading.Thread(target=get_funds, daemon=True).start()
        threading.Thread(target=fetch_dhan_ltp, daemon=True).start()
    else:
        log.warning('⚠️  No token — Dashboard mein daalo aur Save karo')

    add_log('🚀 Dhan Quantum v7.0 LIVE!', 'INFO')
    add_log('📲 Morning reminder: 8 AM Telegram pe aayega', 'INFO')
    add_log('🌐 UptimeRobot ke liye /ping endpoint ready', 'INFO')

    threading.Thread(target=run_scheduler, daemon=True).start()
    PORT = int(os.environ.get('PORT', 5000))
    log.info(f'🌐 Dashboard: http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)

# ─── requirements.txt content (print for reference) ───────────────
REQUIREMENTS = """
flask>=3.0.0
requests>=2.31.0
numpy>=1.26.0
schedule>=1.2.0
"""
