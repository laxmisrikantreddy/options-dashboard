import google.generativeai as genai
import streamlit as st
import pandas as pd
from dhanhq import DhanContext, dhanhq
from datetime import datetime
import time
import yfinance as yf

st.set_page_config(layout="wide", page_title="Ultimate Options Dashboard")

# --- 1. THE LOGIN SCREEN ---
client_id = str(st.secrets["client_id"])

if 'daily_token' not in st.session_state:
    st.session_state.daily_token = None

if st.session_state.daily_token is None:
    st.title("🔒 Terminal Locked")
    st.info("SEBI regulations require a fresh API token every 24 hours.")
    
    new_token = st.text_input("Paste Today's Dhan Access Token:", type="password")
    
    if st.button("Start Engine 🚀"):
        if new_token:
            st.session_state.daily_token = new_token
            st.rerun() 
        else:
            st.error("Token cannot be empty.")
            
    st.stop() 

# --- 2. MAIN DASHBOARD ---
access_token = st.session_state.daily_token
st.title("🎯 Ultimate Options Decoding Dashboard")

top_col1, top_col2 = st.columns([3, 1])
with top_col1:
    current_time = datetime.now().strftime("%I:%M:%S %p")
    st.write(f"🟢 **Live Market Data** | Last Updated: {current_time}")
with top_col2:
    auto_refresh = st.toggle("🔄 Live Auto-Refresh (30s)", value=True)

st.divider()

# --- 3. GLOBAL MACRO TICKER TAPE ---
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

# --- 4. OPTIONS DATA FETCH ---
dhan_context = DhanContext(client_id, access_token)
dhan = dhanhq(dhan_context)
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
            df = df[(df['Call OI (Resistance)'] > 0) | (df['Put OI (Support)'] > 0)].reset_index(drop=True)

            # --- THE TIME MACHINE: BACKGROUND CALCULATION ---
            if 'oi_baseline' not in st.session_state:
                st.session_state.oi_baseline = None
                st.session_state.baseline_time = None

            if st.session_state.oi_baseline is not None:
                try:
                    df['15m Call Change'] = df['Call OI (Resistance)'] - st.session_state.oi_baseline['Call OI (Resistance)']
                    df['15m Put Change'] = df['Put OI (Support)'] - st.session_state.oi_baseline['Put OI (Support)']
                except Exception:
                    pass # Wait for user to resync if data shifts

            # --- HEURISTIC AI & METRICS ---
            total_call_oi = df['Call OI (Resistance)'].sum()
            total_put_oi = df['Put OI (Support)'].sum()
            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
            
            resistance_strike = df.loc[df['Call OI (Resistance)'].idxmax()]['Strike Price']
            support_strike = df.loc[df['Put OI (Support)'].idxmax()]['Strike Price']

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

            st.info(f"### ⚙️ Trend Logic Engine: {ai_verdict}\n**Market Thesis:** {ai_reason}\n\n{market_insight}\n\n* **Strongest Support:** {int(support_strike)}\n* **Strongest Resistance:** {int(resistance_strike)}")
            st.divider()

            # --- FILTER TARGET STRIKES ---
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
            
            # --- ADVANCED OPTION CHAIN (TIME MACHINE UI) ---
            st.divider()
            st.write("### 🔬 Advanced Option Chain & Intraday Tracker")
            
            colA, colB = st.columns([1, 3])
            with colA:
                if st.button("📸 Capture 15m Baseline"):
                    st.session_state.oi_baseline = df.copy()
                    st.session_state.baseline_time = datetime.now().strftime("%I:%M:%S %p")
                    st.rerun()

            def highlight_danger_zone(row):
                max_call_oi = df_filtered['Call OI (Resistance)'].max()
                max_put_oi = df_filtered['Put OI (Support)'].max()

                if row['Call OI (Resistance)'] == max_call_oi: return ['background-color: #3b0000'] * len(row)
                elif row['Put OI (Support)'] == max_put_oi: return ['background-color: #003b05'] * len(row)
                else: return [''] * len(row)

            with colB:
                if st.session_state.oi_baseline is not None:
                    st.success(f"Tracking institutional footprints since: {st.session_state.baseline_time}")
                    if '15m Call Change' in df_filtered.columns:
                        display_cols = ['Strike Price', 'Call OI (Resistance)', '15m Call Change', 'Call Trend', 'Put OI (Support)', '15m Put Change', 'Put Trend']
                        display_df = df_filtered[display_cols]
                    else:
                        display_df = df_filtered
                else:
                    st.warning("Click the camera button to start tracking 15-minute institutional shifts.")
                    display_df = df_filtered

            # Drop 'Total OI' if it exists before display to keep UI clean
            if 'Total OI' in display_df.columns:
                display_df = display_df.drop(columns=['Total OI'])

            st.dataframe(display_df.style.apply(highlight_danger_zone, axis=1), width='stretch')
            
            # --- LIVE AI DECODER (GEMINI) ---
            st.divider()
            st.subheader("🔮 Gemini Neural Network: Trap Decoder")
            
            if st.session_state.oi_baseline is not None and '15m Call Change' in display_df.columns:
                if st.button("Generate Institutional Thesis"):
                    with st.spinner("Connecting to Google AI Studio..."):
                        try:
                            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                            model = genai.GenerativeModel('gemini-pro')
                            
                            # Prepare exact context for the model
                            ai_context = display_df[['Strike Price', 'Call OI (Resistance)', '15m Call Change', 'Put OI (Support)', '15m Put Change']].dropna()
                            ai_context = ai_context.sort_values(by='Call OI (Resistance)', ascending=False).head(10)
                            data_string = ai_context.to_csv(index=False)
                            
                            prompt = f"""
                            You are a ruthless, expert quantitative options trader. Look at this live snapshot of Nifty Option Chain Open Interest (OI).
                            
                            Data Columns: Strike Price, Total Call OI, 15m Call Change, Total Put OI, 15m Put Change.
                            
                            Here is the data:
                            {data_string}
                            
                            Decode the market for an intraday option buyer in exactly 3 short paragraphs:
                            1. The Mega-Walls: Where is the absolute macro ceiling and floor?
                            2. The Active Battlefield: Based on the 15m changes, where are institutions aggressively deploying capital right now?
                            3. The Verdict: Is there a trap being set? Who is surrendering? Give me a final trade thesis (e.g., Wait for Put surrender at X, or Buy Call breakouts).
                            
                            Be direct, analytical, and do not use generic fluff.
                            """
                            
                            response = model.generate_content(prompt)
                            st.info(response.text)
                            
                        except Exception as e:
                            st.error(f"Brain connection failed: Check your GEMINI_API_KEY in Streamlit Secrets. Error: {e}")
            else:
                st.warning("Capture a baseline first so the AI has 15-minute intraday data to decode.")

        else:
            st.error("Option chain data is empty.")
    else:
        st.error("Failed to fetch Option Chain.")
else:
    st.error("Failed to fetch Expiry Dates.")

# --- AUTO-REFRESH ENGINE ---
if auto_refresh:
    time.sleep(30)
    st.rerun()
