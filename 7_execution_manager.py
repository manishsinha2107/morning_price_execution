# 7_execution_manager.py

import os
import pyotp
import base64
import requests
import math
import json
from datetime import datetime
from dotenv import load_dotenv
from fyers_apiv3 import fyersModel

# --- IMPORT CONFIGURATIONS ---
from config import MAX_CAPITAL_PER_TRADE, MAX_RISK_PCT_PER_TRADE, SLIPPAGE_TOLERANCE_PCT

load_dotenv()

# ============================================================
# 1. INITIALISATION & AUTHENTICATION
# ============================================================

URL = os.environ.get("SUPABASE_URL").rstrip('/')
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    print("❌ Error: Supabase credentials missing.")
    exit(1)

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json"
}

FY_ID = os.getenv("FYERS_USERNAME")
APP_ID = os.getenv("FYERS_APP_ID")
SECRET_ID = os.getenv("FYERS_SECRET_ID")
PIN = os.getenv("FYERS_PIN")
TOTP_KEY = os.getenv("FYERS_TOTP_KEY")
REDIRECT_URL = "https://trade.fyers.in/api-login/redirect-uri/index.html"

def get_fyers_access_token():
    """Headless Authentication Flow"""
    s = requests.Session()
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    try:
        payload1 = {"fy_id": base64.b64encode(FY_ID.encode()).decode(), "app_id": "2"}
        r1 = s.post("https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", json=payload1, headers=headers).json()
        if r1.get('s') != 'ok': return None
        req_key = r1.get('request_key')

        otp = pyotp.TOTP(TOTP_KEY).now()
        r2 = s.post("https://api-t2.fyers.in/vagator/v2/verify_otp", json={"request_key": req_key, "otp": otp}, headers=headers).json()
        if r2.get('s') != 'ok': return None
        req_key = r2.get('request_key')

        payload3 = {"request_key": req_key, "identity_type": "pin", "identifier": base64.b64encode(PIN.encode()).decode()}
        r3 = s.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2", json=payload3, headers=headers).json()
        if r3.get('s') != 'ok' or 'data' not in r3: return None
            
        token_v2 = r3['data']['access_token']
        short_app_id = APP_ID.split('-')[0]
        headers_auth = {'Authorization': f'Bearer {token_v2}', 'Content-Type': 'application/json'}
        payload4 = {
            "fyers_id": FY_ID, "app_id": short_app_id, "redirect_uri": REDIRECT_URL, 
            "appType": "100", "response_type": "code", "state": "abcdefg"
        }
        r4 = s.post("https://api-t1.fyers.in/api/v3/token", json=payload4, headers=headers_auth).json()
        
        if 'Url' in r4:
            auth_code = r4['Url'].split('auth_code=')[1].split('&')[0]
        else: return None

        session = fyersModel.SessionModel(
            client_id=APP_ID, secret_key=SECRET_ID, redirect_uri=REDIRECT_URL, 
            response_type="code", grant_type="authorization_code"
        )
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response.get("s") == "ok" and "access_token" in response:
            return response["access_token"]
        return None
    except Exception as e:
        print(f"⚠️ Auth Exception: {str(e)}")
        return None

def fetch_system_dials() -> dict:
    try:
        # We now fetch the global safety floor, not the perfect measuring stick
        r = requests.get(f"{URL}/rest/v1/system_dials?select=trade_type,global_floor_rr", headers=HEADERS)
        if r.status_code == 200:
            return {row['trade_type']: float(row['global_floor_rr']) for row in r.json()}
        return {}
    except:
        return {}

# ============================================================
# 2. CORE DUAL-EXECUTION MANAGER
# ============================================================

def run_dual_execution_manager():
    print(f"⚡ [{datetime.now().strftime('%H:%M:%S')}] Waking up Master Execution Node...")

    # ============================================================
    # 0. ALWAYS AUTHENTICATE FIRST (Feeds the UI Terminal)
    # ============================================================
    print("🔑 Authenticating with Fyers...")
    access_token = get_fyers_access_token()
    if not access_token:
        print("❌ Critical: Could not authenticate with Fyers broker. Aborting execution.")
        exit(1)

    # --- NEW: SECURE TOKEN DEPOSIT ---
    try:
        requests.patch(
            f"{URL}/rest/v1/broker_sessions?id=eq.1", 
            headers=HEADERS, 
            json={"fyers_access_token": access_token, "updated_at": datetime.now().isoformat()}
        )
        print("   ✅ Live token securely deposited into Supabase Vault.")
    except Exception as e:
        print(f"   ⚠️ Vault deposit failed. UI will remain static today: {e}")
    # ============================================================

    # 1. The Dual-Queue Fetch
    try:
        print("📡 Fetching PENDING setups from Daily & Sniper Ledgers...")
        daily_req = requests.get(f"{URL}/rest/v1/trade_signals?status=eq.AWAITING%20EXECUTION&select=*", headers=HEADERS)
        daily_trades = daily_req.json() if daily_req.status_code == 200 else []
        
        sniper_req = requests.get(f"{URL}/rest/v1/sniper_trade_signals?status=eq.AWAITING%20EXECUTION&select=*", headers=HEADERS)
        sniper_trades = sniper_req.json() if sniper_req.status_code == 200 else []
    except Exception as e:
        print(f"❌ Critical: Could not fetch pending trades: {e}")
        return

    if not daily_trades and not sniper_trades:
        print("ℹ️ No PENDING trades found in any queue. Sleeping.")
        return

    # Tag trades with their origin table so the engine knows where to send the update
    for t in daily_trades: t['source_table'] = 'trade_signals'
    for t in sniper_trades: t['source_table'] = 'sniper_trade_signals'
    
    all_pending = daily_trades + sniper_trades
    print(f"🔍 Consolidated {len(daily_trades)} Daily and {len(sniper_trades)} Sniper targets.")

    # 2. Fetch Live Dials & Initialize Fyers Model
    dials = fetch_system_dials()
    fyers = fyersModel.FyersModel(client_id=APP_ID, token=access_token, is_async=False, log_path="")

    # 3. Format symbols into a Unified Roster and fetch high-speed quotes
    symbol_map = {}
    for t in all_pending:
        fyers_sym = f"NSE:{t['symbol'].upper()}-EQ"
        if fyers_sym not in symbol_map:
            symbol_map[fyers_sym] = []
        symbol_map[fyers_sym].append(t)
        
    fyers_query_string = ",".join(symbol_map.keys())
    
    print(f"📡 API Strike: Fetching live open prices for {len(symbol_map)} unique assets...")
    try:
        quote_res = fyers.quotes({"symbols": fyers_query_string})
    except Exception as e:
        print(f"❌ Critical: Fyers Quotes API failed: {e}")
        exit(1)

    if quote_res.get("s") != "ok":
        print(f"❌ Broker Error: {quote_res.get('message')}")
        exit(1)

    # 4. The Parallel Routing & Recalculation Engine
    live_data = quote_res.get("d", [])
    
    for item in live_data:
        fyers_sym = item['n']
        live_open = float(item['v']['open_price'])
        
        # --- THE INTUITIVE HOLIDAY BLOCKER ---
        # Extract the Last Traded Time (tt) Unix epoch and convert to date
        last_traded_epoch = int(item['v'].get('tt', 0))
        if last_traded_epoch > 0:
            last_traded_date = datetime.fromtimestamp(last_traded_epoch).date()
            today_date = datetime.now().date()
            
            # If the quote is from yesterday (or older), the market is closed today.
            if last_traded_date < today_date:
                print(f"   ⏸️ {fyers_sym} is returning stale data from {last_traded_date.strftime('%d-%b-%Y')}. Market is closed today.")
                continue # Skip execution, leave it PENDING
        # -------------------------------------
        
        trades_list = symbol_map.get(fyers_sym)
        if not trades_list: continue
        
        for trade in trades_list:
            sym = trade['symbol']
            t_type = trade['trade_type']
            trade_id = trade['id']
            source = trade['source_table']
            prefix = "[SNIPER]" if source == 'sniper_trade_signals' else "[DAILY]"
            
            # Technical levels (Option A: Rigid Target and SL)
            stop_loss = float(trade['stop_loss'])
            target_price = float(trade['target_price'])
            planned_entry = float(trade['entry_price'])
            
            # --- NEW: DIFFERENTIATED EXECUTION PRICE ---
            if source == 'sniper_trade_signals':
                # Sniper defends its discount. Use the Limit Price (unless live open is even cheaper)
                exec_price = min(live_open, planned_entry)
            else:
                # Daily strategy enters at the live open price
                exec_price = live_open
            
            new_risk_per_share = exec_price - stop_loss
            new_reward_per_share = target_price - exec_price
            
            # Scenario 1: Gap Down hit Stop Loss immediately
            if new_risk_per_share <= 0:
                print(f"   ❌ {prefix} {sym} ({t_type}): CANCELLED. Gap down instantly violated stop loss level.")
                payload = {"status": "CANCELLED", "exit_reason": "GAP_CRUSHED_STOP"}
                requests.patch(f"{URL}/rest/v1/{source}?id=eq.{trade_id}", headers=HEADERS, json=payload)
                continue

            # Scenario 2: Calculate new buffered R/R
            new_rr = new_reward_per_share / new_risk_per_share
            
            # --- STRICT TQS AUDIT CHECK (NO FALLBACKS) ---
            try:
                tqs_data = trade.get('tqs_audit', {})
                if isinstance(tqs_data, str):
                    tqs_data = json.loads(tqs_data)
                
                # Fetch the exact RR floor used during the AI's discovery scan
                required_rr = float(tqs_data['circuit_breakers']['req_rr'])
            except (KeyError, TypeError, json.JSONDecodeError):
                print(f"   ❌ {prefix} {sym} ({t_type}): CANCELLED. Critical Error: Missing or Corrupt TQS Audit data. Cannot verify R/R floor.")
                payload = {"status": "CANCELLED", "exit_reason": "MISSING_TQS_AUDIT"}
                requests.patch(f"{URL}/rest/v1/{source}?id=eq.{trade_id}", headers=HEADERS, json=payload)
                continue

            buffered_rr_limit = required_rr * (1 - (SLIPPAGE_TOLERANCE_PCT / 100.0))

            if new_rr < buffered_rr_limit:
                print(f"   ❌ {prefix} {sym} ({t_type}): CANCELLED. Live R/R ({new_rr:.2f}) < Minimum ({buffered_rr_limit:.2f}).")
                payload = {"status": "CANCELLED", "exit_reason": "GAP_CRUSHED_RR"}
                requests.patch(f"{URL}/rest/v1/{source}?id=eq.{trade_id}", headers=HEADERS, json=payload)
                continue

            # Scenario 3: Passed. Recalculate strict capital limits based on new entry.
            max_cap = MAX_CAPITAL_PER_TRADE.get(t_type, 0)
            max_risk_amount = max_cap * (MAX_RISK_PCT_PER_TRADE.get(t_type, 0) / 100.0)
            
            # Use exec_price instead of live_open
            capital_shares = math.floor(max_cap / exec_price)
            risk_shares = math.floor(max_risk_amount / new_risk_per_share)
            final_quantity = min(capital_shares, risk_shares)

            if final_quantity <= 0:
                print(f"   ❌ {prefix} {sym} ({t_type}): CANCELLED. Gap altered risk to prevent minimum 1 lot size.")
                payload = {"status": "CANCELLED", "exit_reason": "GAP_CRUSHED_CAPITAL"}
                requests.patch(f"{URL}/rest/v1/{source}?id=eq.{trade_id}", headers=HEADERS, json=payload)
                continue

            # 5. The Execution Push (Routed to the correct database table)
            try:
                # Strictly format the date as YYYY-MM-DD for Supabase DATE columns
                exec_date_str = datetime.now().strftime('%Y-%m-%d')
                
                payload = {
                    "entry_price": round(exec_price, 2), 
                    "quantity": final_quantity,
                    "status": "ACTIVE",
                    "execution_date": exec_date_str
                }
                
                # Capture the response to verify actual database success
                res = requests.patch(f"{URL}/rest/v1/{source}?id=eq.{trade_id}", headers=HEADERS, json=payload)
                
                if res.status_code in [200, 204]:
                    print(f"   ✅ {prefix} {sym} ({t_type}) EXECUTED: Status -> ACTIVE | Entry: ₹{exec_price:.2f} | Exec Date: {exec_date_str}")
                else:
                    print(f"   ⚠️ DB Reject for {sym}: [{res.status_code}] {res.text}")
            
            except Exception as e:
                print(f"   ⚠️ Network Update failed for {sym} ({t_type}) in {source}: {e}")

    print("\n" + "="*80)
    print(f"{'DUAL EXECUTION MANAGER RUN COMPLETED':^80}")
    print("="*80)

if __name__ == "__main__":
    try:
        run_dual_execution_manager()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Fatal Error: {str(e)[:100]}")
        exit(1)
