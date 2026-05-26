import google.generativeai as genai
import streamlit as st
import pandas as pd
from dhanhq import DhanContext, dhanhq
from datetime import datetime
import time
import yfinance as yf
import plotly.graph_objects as go

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
        "Sensex": "^BSESN", 
        "Crude Oil": "CL=F", 
        "USD/INR": "INR=X"
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

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Nifty 50", f"{prices['Nifty 50']['price']:,.2f}", f"{prices['Nifty 50']['change']:.2f}")
m2.metric("Bank Nifty", f"{prices['Bank Nifty']['price']:,.2f}", f"{prices['Bank Nifty']['change']:.2f}")
m3.metric("Sensex", f"{prices['Sensex']['price']:,.2f}", f"{prices['Sensex']['change']:.2f}")
m4.metric("Crude Oil (WTI)", f"${prices['Crude Oil']['price']:.2f}", f"{prices['Crude Oil']['change']:.2f}")
m5.metric("USD / INR", f"₹{prices['USD/INR']['price']:.3f}", f"{prices['USD/INR']['change']:.3f}")

st.divider()

# --- 4. OPTIONS DATA FETCH (3-WAY TOGGLE) ---
st.write("### ⚙️ Select Trading Index")
index_choice = st.radio("Target Index:", ["Nifty 50", "Bank Nifty", "Sensex"], horizontal=True)

dhan_context = DhanContext(client_id, access_token)
dhan = dhanhq(dhan_context)

if index_choice == "Nifty 50":
    target_id = 13
    segment = "IDX_I"
    target_spot = prices['Nifty 50']['price']
    yf_ticker = "^NSEI"
elif index_choice == "Bank Nifty":
    target_id = 25
    segment = "IDX_I"
    target_spot = prices['Bank Nifty']['price']
    yf_ticker = "^NSEBANK"
else:
    target_id = 51  
    segment = "IDX_I"  
    target_spot = prices['Sensex']['price']
    yf_ticker = "^BSESN"

expiry_response = dhan.expiry_list(under_security_id=target_id, under_exchange_segment=segment)

if expiry_response.get("status") == "success":
    try:
        nearest_expiry = expiry_response['data']['data'][0]
    except KeyError:
        nearest_expiry = expiry_response['data'][0] 
        
    chain_response = dhan.option_chain(under_security_id=target_id, under_exchange_segment=segment, expiry=nearest_expiry)
    
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

            if 'oi_baseline' not in st.session_state:
                st.session_state.oi_baseline = None
                st.session_state.baseline_time = None

            if st.session_state.oi_baseline is not None:
                try:
                    df['15m Call Change'] = df['Call OI (Resistance)'] - st.session_state.oi_baseline['Call OI (Resistance)']
                    df['15m Put Change'] = df['Put OI (Support)'] - st.session_state.oi_baseline['Put OI (Support)']
                except Exception:
                    pass 

            total_call_oi = df['Call OI (Resistance)'].sum()
            total_put_oi = df['Put OI (Support)'].sum()
            pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
            
            resistance_strike = df.loc[df['Call OI (Resistance)'].idxmax()]['Strike Price']
            support_strike = df.loc[df['Put OI (Support)'].idxmax()]['Strike Price']

            if 'history' not in st.session_state:
                st.session_state.history = []

            current_snapshot = {'time': time.time(), 'pcr': pcr, 'price': target_spot}
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
                    price_change = target_spot - past_snapshot['price']
                    
                    if price_change > 10 and pcr_change > 0.02:
                        ai_verdict = "Aggressive Bullish (Buy Breakouts) 🟢"
                        ai_reason = f"Price is rising AND Put writers are aggressively supporting the move."
                    elif price_change > 10 and pcr_change < -0.02:
                        ai_verdict = "Bearish Divergence (BULL TRAP!) 🚨"
                        ai_reason = f"Price is rising BUT Call writers are heavily selling the top."
                    elif price_change < -10 and pcr_change < -0.02:
                        ai_verdict = "Aggressive Bearish (Sell Breakdowns) 🔴"
                        ai_reason = f"Price is dropping AND Call writers are pushing it down."
                    elif price_change < -10 and pcr_change > 0.02:
                        ai_verdict = "Bullish Divergence (BEAR TRAP!) 🚨"
                        ai_reason = f"Price is dropping BUT Put writers are aggressively defending the bottom."
                    elif abs(price_change) <= 10:
                        ai_verdict = "No Trade Zone (Chop/Sideways) 🟡"
                        ai_reason = "Price is flat. Options writers are eating premium (Theta Decay)."
                else:
                    st.session_state.history = []

            st.info(f"### ⚙️ Trend Logic Engine: {ai_verdict}\n**Market Thesis:** {ai_reason}\n\n* **Strongest Support:** {int(support_strike)}\n* **Strongest Resistance:** {int(resistance_strike)}")
            
            # --- 5. THE SNIPER SCOPE (PRICE ACTION + OI WALLS) ---
            st.divider()
            st.subheader(f"📊 {index_choice} Live Price Action vs Institutional Walls")
            
            try:
                # Fetch 5-minute Intraday Data
                hist_data = yf.Ticker(yf_ticker).history(period="1d", interval="5m")
                
                if not hist_data.empty:
                    fig = go.Figure(data=[go.Candlestick(
                        x=hist_data.index,
                        open=hist_data['Open'],
                        high=hist_data['High'],
                        low=hist_data['Low'],
                        close=hist_data['Close'],
                        name="Price Action"
                    )])
                    
                    # Draw the OI Walls directly on the chart
                    fig.add_hline(y=resistance_strike, line_dash="dash", line_color="red", 
                                  annotation_text=f"Massive Call Wall: {int(resistance_strike)}", 
                                  annotation_position="bottom right", annotation_font_color="red")
                    
                    fig.add_hline(y=support_strike, line_dash="dash", line_color="green", 
                                  annotation_text=f"Massive Put Wall: {int(support_strike)}", 
                                  annotation_position="top right", annotation_font_color="green")
                    
                    fig.update_layout(
                        height=500, 
                        margin=dict(l=0, r=0, t=30, b=0), 
                        template="plotly_dark", 
                        xaxis_rangeslider_visible=False,
                        yaxis_title="Spot Price"
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Waiting for market to open to generate live candles.")
            except Exception as e:
                st.warning(f"Could not load chart data: {e}")
                
            st.divider()

            # --- 6. FILTER TARGET STRIKES & DATA TABLE ---
            if target_spot > 10000:
                atm_index = (df['Strike Price'] - target_spot).abs().idxmin()
            else:
                df['Total OI'] = df['Call OI (Resistance)'] + df['Put OI (Support)']
                atm_index = df['Total OI'].idxmax()
                
            df_filtered = df.iloc[max(0, atm_index-10) : atm_index+11]
            
            st.write(f"### {index_choice} Expiry: {nearest_expiry}")
            
            col1, col2 = st.columns(2)
            col1.metric("Live Put-Call Ratio (PCR)", round(pcr, 2))
            
            sentiment = "Neutral 🟡"
            if pcr > 1.2: sentiment = "Overbought (Bearish Reversal Possible) 🔴"
            elif pcr < 0.7: sentiment = "Oversold (Bullish Reversal Possible) 🟢"
            col2.metric("Overall Daily Sentiment", sentiment)

            st.write("### 🔬 Advanced Option Chain & Intraday Tracker")
            
            colA, colB = st.columns([1, 3])
            with colA:
                if st.button("📸 Capture 15m Baseline"):
                    st.session_state.oi_baseline = df.copy()
                    st.session_state.baseline_time = datetime.now().strftime("%I:%M:%S %p")
                    st.rerun()
                if st.button("🧹 Clear Baseline"):
                    st.session_state.oi_baseline = None
                    st.rerun()

            def highlight_danger_zone(row):
                max_call_oi = df_filtered['Call OI (Resistance)'].max()
                max_put_oi = df_filtered['Put OI (Support)'].max()

                if row['Call OI (Resistance)'] == max_call_oi: return ['background-color: #3b0000'] * len(row)
                elif row['Put OI (Support)'] == max_put_oi: return ['background-color: #003b05'] * len(row)
                else: return [''] * len(row)

            with colB:
                if st.session_state.oi_baseline is not None:
                    st.success(f"Tracking institutional footprints since: {st.session_state.baseline_time}. (Clear baseline if switching index!)")
                    if '15m Call Change' in df_filtered.columns:
                        display_cols = ['Strike Price', 'Call OI (Resistance)', '15m Call Change', 'Call Trend', 'Put OI (Support)', '15m Put Change', 'Put Trend']
                        display_df = df_filtered[display_cols]
                    else:
                        display_df = df_filtered
                else:
                    st.warning("Click the camera button to start tracking 15-minute institutional shifts.")
                    display_df = df_filtered

            if 'Total OI' in display_df.columns:
                display_df = display_df.drop(columns=['Total OI'])

            st.dataframe(display_df.style.apply(highlight_danger_zone, axis=1), width='stretch')
            
            # --- 7. THE GEMINI AI NEURAL NETWORK & CHATBOT ---
            st.divider()
            st.subheader(f"🧠 Live AI Quant & Interactive Chat ({index_choice})")
            
            ai_context = display_df.copy()
            if 'Total OI' in ai_context.columns:
                ai_context = ai_context.drop(columns=['Total OI'])
            
            data_string = ai_context.to_csv(index=False)
            
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []
                
            if st.button("Generate Comprehensive Market Thesis 🔮"):
                with st.spinner("Analyzing Macro Walls, Daily Trends, and Intraday Momentum..."):
                    try:
                        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                        model = genai.GenerativeModel('gemini-2.5-flash') 
                        
                        system_prompt = f"""
                        You are my elite quantitative trading partner and mentor. We are hunting institutional traps in the Indian options market.
                        Here is the live Option Chain data for {index_choice} (Macro, Daily Trends, and 15m Momentum):
                        {data_string}
                        
                        Do NOT just read the numbers back to me like a calculator. I can already see the data on my screen. 
                        I need your BRAIN. Read the psychology of the market makers. 
                        
                        Give me a strategic breakdown in plain, conversational English:
                        1. The Trap: Where is the Smart Money setting the ceiling and the floor to crush retail premium?
                        2. The Panic: Based on the trends (unwinding/buildup), who is currently surrendering?
                        3. The Execution: As an option buyer, what is the exact trigger I should wait for before deploying capital?
                        
                        Talk to me like a real human trader sitting next to me on the desk. Be direct, candid, and highly strategic.
                        """
                        
                        response = model.generate_content(system_prompt)
                        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                    except Exception as e:
                        st.error(f"AI Connection Error: {e}")

            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            if user_question := st.chat_input("Ask your AI Quant a specific question about the data..."):
                
                st.chat_message("user").markdown(user_question)
                st.session_state.chat_history.append({"role": "user", "content": user_question})
                
                with st.spinner("Decoding data..."):
                    try:
                        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                        model = genai.GenerativeModel('gemini-2.5-flash') 
                        
                        chat_prompt = f"""
                        You are my elite quantitative trading partner and mentor. We are hunting institutional traps in the {index_choice} options market.
                        
                        Live Market Data Context:
                        {data_string}
                        
                        The user (your trading partner) asks: "{user_question}"
                        
                        CRITICAL INSTRUCTIONS:
                        - Do NOT just summarize the data. I can read the numbers myself.
                        - Think like a market maker. Where is the trap? Who is surrendering? 
                        - Decode the psychology.
                        - Speak to me conversationally, exactly like a human trading mentor sitting next to me at the desk. Be sharp, direct, and insightful. 
                        - Answer the specific question asked, but always tie it back to the overarching institutional thesis.
                        """
                        
                        response = model.generate_content(chat_prompt)
                        
                        st.chat_message("assistant").markdown(response.text)
                        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                    except Exception as e:
                        st.error(f"Chat failed: {e}")

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
