import streamlit as st
import pandas as pd
from dhanhq import dhanhq
from datetime import datetime
import time
import yfinance as yf

# --- 1. SETUP ---
client_id = str(st.secrets["client_id"])
access_token = str(st.secrets["access_token"])

st.set_page_config(layout="wide")
st.title("🎯 Ultimate Options Decoding Dashboard")

top_col1, top_col2 = st.columns([3, 1])
with top_col1:
    current_time = datetime.now().strftime("%I:%M:%S %p")
    st.write(f"🟢 **Live Market Data** | Last Updated: {current_time}")
with top_col2:
    auto_refresh = st.toggle("🔄 Live Auto-Refresh (30s)", value=True)

st.divider()

# --- 2. GLOBAL MACRO TICKER TAPE ---
@st.cache_data(ttl=25)
def fetch_global_prices():
    symbols = {
        "Nifty 50": "^NSEI", 
        "Bank Nifty": "^NSEBANK", 
        "Crude Oil": "CL=F", 
        "USD/INR": "INR=X", 
        "Dow Futures": "YM=F"
    }
    results = {}
    for name, ticker in symbols.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="5d") 
            if len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current = hist['Close'].iloc[-1]
                change = current - prev_close
                results[name] = {"price": current, "change": change}
            else:
                results[name] = {"price": 0.0, "change": 0.0}
        except:
            results[name] = {"price": 0.0, "change": 0.0}
    return results

prices = fetch_global_prices()
nifty_spot = prices['Nifty 50']['price'] 

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Nifty 50", f"{nifty_spot:,.2f}", f"{prices['Nifty 50']['change']:.2f}")
m2.metric("Bank Nifty", f"{prices['Bank Nifty']['price']:,.2f}", f"{prices['Bank Nifty']['change']:.2f}")
m3.metric("Crude Oil (WTI)", f"${prices['Crude Oil']['price']:.2f}", f"{prices['Crude Oil']['change']:.2f}")
m4.metric("USD / INR", f"₹{prices['USD/INR']['price']:.3f}", f"{prices['USD/INR']['change']:.3f}")
m5.metric("Dow Futures", f"{prices['Dow Futures']['price']:,.2f}", f"{prices['Dow Futures']['change']:.2f}")

st.divider()

# --- 3. OPTIONS DATA FETCH ---
dhan = dhanhq(client_id, access_token)
nifty_id = 13
segment = "IDX_I"

expiry_response = dhan.expiry_list(under_security_id=nifty_id, under_exchange_segment=segment)

if expiry_response.get("status") == "success":
    try:
        nearest_expiry = expiry_response['data']['data'][0]
    except KeyError:
        nearest_expiry = expiry_response['data'][0] 
        
    chain_response = dhan.option_chain(under_security_id=nifty_id, under_exchange_segment=segment, expiry=nearest_expiry)
    
    if chain_response.get("status") == "success":
        data_block = chain_response.get('data', {})
        if 'oc' in data_block:
            options_data = data_block['oc']
        elif 'data' in data_block and 'oc' in data_block['data']:
            options_data = data_block['data']['oc']
        else:
            options_data = {}
            
        if options_data:
            clean_data = []
            
            def decode_oi(price_change, oi_change):
                if price_change > 0 and oi_change > 0: return "Long Buildup 🟢"
                if price_change < 0 and oi_change > 0: return "Short Buildup 🔴"
                if price_change > 0 and oi_change < 0: return "Short Covering 🔵"
                if price_change < 0 and oi_change < 0: return "Long Unwinding 🟡"
                return "Neutral ⚪"

            for strike, values in options_data.items():
                ce_data = values.get('ce', {})
                ce_oi = ce_data.get('oi', 0)
                ce_prev_oi = ce_data.get('previous_oi', 0) 
                ce_ltp = ce_data.get('last_price', 0) 
                ce_prev_ltp = ce_data.get('previous_close_price', 0) 
                ce_oi_chg = ce_oi - ce_prev_oi
                ce_ltp_chg = ce_ltp - ce_prev_ltp
                
                pe_data = values.get('pe', {})
                pe_oi = pe_data.get('oi', 0)
                pe_prev_oi = pe_data.get('previous_oi', 0)
                pe_ltp = pe_data.get('last_price', 0)
                pe_prev_ltp = pe_data.get('previous_close_price', 0)
                pe_oi_chg = pe_oi - pe_prev_oi
                pe_ltp_chg = pe_ltp - pe_prev_ltp
                
                clean_data.append({
                    "Strike Price": float(strike),
                    "Call OI (Resistance)": ce_oi,
                    "Call Trend": decode_oi(ce_ltp_chg, ce_oi_chg),
                    "Put OI (Support)": pe_oi,
                    "Put Trend": decode_oi(pe_ltp_chg, pe_oi_chg)
                })
                
            df = pd.DataFrame(clean_data)
            df = df.sort_values('Strike Price').reset_index(drop=True)
            
            # THE FIX: Resetting the row index numbers so the camera aims perfectly
            df = df[(df['Call OI (Resistance)'] > 0) | (df['Put OI (Support)'] > 0)].reset_index(drop=True)
            
            total_call_oi = df['Call OI (Resistance)'].sum()
            total_put_oi = df['Put OI (Support)'].sum()
            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
            
            resistance_strike = df.loc[df['Call OI (Resistance)'].idxmax()]['Strike Price']
            support_strike = df.loc[df['Put OI (Support)'].idxmax()]['Strike Price']

            # --- 4. THE AI LOGIC ENGINE ---
            if 'history' not in st.session_state:
                st.session_state.history = []

            current_snapshot = {'time': time.time(), 'pcr': pcr, 'price': nifty_spot}
            st.session_state.history.append(current_snapshot)

            if len(st.session_state.history) > 120:
                st.session_state.history.pop(0)

            past_snapshot = None
            for snap in reversed(st.session_state.history):
                if current_snapshot['time'] - snap['time'] >= 900: 
                    past_snapshot = snap
                    break
            
            if not past_snapshot and len(st.session_state.history) > 2:
                past_snapshot = st.session_state.history[0]

            ai_verdict = "Analyzing Market Structure... ⚪"
            ai_reason = "The Memory Bank is filling up. Waiting for momentum to establish."

            if past_snapshot:
                if 'price' in past_snapshot:
                    pcr_change = pcr - past_snapshot['pcr']
                    price_change = nifty_spot - past_snapshot['price']
                    
                    if price_change > 10 and pcr_change > 0.02:
                        ai_verdict = "Aggressive Bullish (Buy Breakouts) 🟢"
                        ai_reason = f"Price is rising (+{int(price_change)} pts) AND Put writers are aggressively supporting the move. Classic uptrend."
                    elif price_change > 10 and pcr_change < -0.02:
                        ai_verdict = "Bearish Divergence (BULL TRAP!) 🚨"
                        ai_reason = f"Price is rising (+{int(price_change)} pts) BUT Call writers are heavily selling the top. Smart money is fading this rally. Watch for a sharp reversal downward."
                    elif price_change < -10 and pcr_change < -0.02:
                        ai_verdict = "Aggressive Bearish (Sell Breakdowns) 🔴"
                        ai_reason = f"Price is dropping ({int(price_change)} pts) AND Call writers are pushing it down further. Classic downtrend."
                    elif price_change < -10 and pcr_change > 0.02:
                        ai_verdict = "Bullish Divergence (BEAR TRAP!) 🚨"
                        ai_reason = f"Price is dropping ({int(price_change)} pts) BUT Put writers are aggressively defending the bottom. Smart money is buying this dip. Watch for a violent bounce."
                    elif abs(price_change) <= 10:
                        ai_verdict = "No Trade Zone (Chop/Sideways) 🟡"
                        ai_reason = "Price is flat. Options writers are eating premium (Theta Decay). Highly dangerous for option buying right now."
                else:
                    st.session_state.history = []

            market_insight = ""
            if resistance_strike == support_strike:
                market_insight = f"🚨 **SMART MONEY PIN:** Massive Short Straddle detected at {int(resistance_strike)}. Institutional sellers are capping both sides to crush premium. Wait for one side to break."
            else:
                market_insight = f"🔍 **Market Structure:** Normal trading range established with a {int(resistance_strike - support_strike)} point spread."

            st.info(f"### 🧠 AI Analyst: {ai_verdict}\n**Market Thesis:** {ai_reason}\n\n{market_insight}\n\n* **Strongest Support:** {int(support_strike)}\n* **Strongest Resistance:** {int(resistance_strike)}")
            st.divider()

            # --- 5. THE CHARTS (YAHOO SPOT TARGETING) ---
            if nifty_spot > 10000:
                atm_index = (df['Strike Price'] - nifty_spot).abs().idxmin()
            else:
                df['Total OI'] = df['Call OI (Resistance)'] + df['Put OI (Support)']
                atm_index = df['Total OI'].idxmax()
                
            df_filtered = df.iloc[max(0, atm_index-10) : atm_index+11]
            
            st.write(f"### Nifty 50 Expiry: {nearest_expiry}")
            
            col1, col2 = st.columns(2)
            col1.metric("Live Put-Call Ratio (PCR)", round(pcr, 2))
            
            sentiment = "Neutral 🟡"
            if pcr > 1.2: sentiment = "Overbought (Bearish Reversal Possible) 🔴"
            elif pcr < 0.7: sentiment = "Oversold (Bullish Reversal Possible) 🟢"
            col2.metric("Overall Daily Sentiment", sentiment)

            st.write("### Open Interest Build-up (Active Strikes)")
            st.bar_chart(df_filtered.set_index("Strike Price")[["Call OI (Resistance)", "Put OI (Support)"]], color=["#ff4b4b", "#00ff00"])
            
            st.write("### 🔬 Advanced Option Chain Decoder")
            if 'Total OI' in df_filtered.columns:
                st.dataframe(df_filtered.drop(columns=['Total OI']), width='stretch')
            else:
                st.dataframe(df_filtered, width='stretch')
            
        else:
            st.error("Option chain data is empty.")
    else:
        st.error("Failed to fetch Option Chain.")
else:
    st.error("Failed to fetch Expiry Dates.")

# --- 6. THE AUTO-REFRESH ENGINE ---
if auto_refresh:
    time.sleep(30)
    st.rerun()
