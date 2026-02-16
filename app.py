import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import json
import os
from datetime import datetime, timedelta

# -----------------------------------------------------------------------------
# 1. SAYFA AYARLARI & TASARIM (DARK & NEON)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="BIST Portföy V2", layout="wide", page_icon="🚀")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .stButton>button {
        background-color: #00ff41; color: #000000; font-weight: bold;
        border: none; padding: 12px 24px; border-radius: 5px; width: 100%; font-size: 16px;
    }
    .stButton>button:hover { background-color: #00cc33; color: #fff; }
    h1, h2, h3 { color: #ffffff; }
    .stMetric { background-color: #1f2937; padding: 15px; border-radius: 10px; border: 1px solid #00ff41; }
    div[data-testid="stMetricValue"] { color: #00ff41; }
    div[data-testid="stMetricLabel"] { color: #aaaaaa; }
    .alert-box {
        background-color: #2a2a2a; border-left: 5px solid #00ff41; padding: 15px; margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. VERİ VE ANALİZ FONKSİYONLARI
# -----------------------------------------------------------------------------

def get_bist_tickers():
    # Havuzu genişlettik (BIST 50 civarı)
    return [
        "THYAO.IS", "ASELS.IS", "GARAN.IS", "AKBNK.IS", "EREGL.IS", "TUPRS.IS", 
        "SASA.IS", "KCHOL.IS", "SAHOL.IS", "BIMAS.IS", "MGROS.IS", "FROTO.IS", 
        "TOASO.IS", "TCELL.IS", "TTKOM.IS", "HEKTS.IS", "ALARK.IS", "DOHOL.IS",
        "ISCTR.IS", "YKBNK.IS", "HALKB.IS", "VAKBN.IS", "KOZAL.IS", "GLYHO.IS",
        "ENKAI.IS", "AKSA.IS", "PETKM.IS", "TTRAK.IS", "MAVI.IS", "AEFES.IS",
        "SOKM.IS", "CCOLA.IS", "ANSGR.IS", "PGSUS.IS", "ULKER.IS", "KORDS.IS",
        "TAVHL.IS", "OYAKC.IS", "ISGYO.IS", "AKFGY.IS", "EKGYO.IS", "VESBE.IS",
        "BRISA.IS", "FLO.IS", "DEVA.IS", "CELHA.IS", "MONTI.IS", "SMART.IS"
    ]

def fetch_data(ticker):
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty: return None
        # MultiIndex düzeltme
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if 'Close' not in df.columns or len(df) < 60: return None
        return df
    except: return None

def calculate_indicators(df):
    df = df.copy()
    close_col = 'Close'
    
    # RSI
    df['RSI'] = ta.rsi(df[close_col], length=14)
    
    # MACD (Güvenli)
    try:
        macd_df = ta.macd(df[close_col], fast=12, slow=26, signal=9)
        # Sütun isimlerini standartlaştır
        macd_df.columns = [str(c).lower() for c in macd_df.columns]
        # MACD ve Signal bul
        macd_c = [c for c in macd_df.columns if 'macd' in c and 'signal' not in c and 'hist' not in c]
        signal_c = [c for c in macd_df.columns if 'signal' in c or 'macds' in c]
        
        if macd_c and signal_c:
            df['MACD'] = macd_df[macd_c[0]]
            df['MACD_SIGNAL'] = macd_df[signal_c[0]]
        else:
            df['MACD'] = 0; df['MACD_SIGNAL'] = 0
    except:
        df['MACD'] = 0; df['MACD_SIGNAL'] = 0
    
    # SMA 50
    df['SMA50'] = ta.sma(df[close_col], length=50)
    return df

def get_fundamentals(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get('trailingPE', 999), info.get('priceToBook', 999), info.get('sector', 'Genel')
    except: return 999, 999, 'Genel'

def analyze_market():
    """
    ADAPTIF SİSTEM: 5 Hisse Bulana Kadar Filtreleri Gevşetir.
    """
    tickers = get_bist_tickers()
    all_candidates = []
    
    # Filtre Seviyeleri (Katı -> Esnek)
    filters = [
        {'name': '🟢 Ideal (Katı)', 'rsi': 50, 'pe': 25, 'pb': 5},
        {'name': '🟡 Orta', 'rsi': 45, 'pe': 50, 'pb': 10},
        {'name': '🟠 Esnek', 'rsi': 40, 'pe': 100, 'pb': 15},
        {'name': '🔴 Zorunlu (Sadece Momentum)', 'rsi': 30, 'pe': 999, 'pb': 999}
    ]
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    final_stocks = []
    used_filter = ""
    
    # Her seviyeyi dene
    for level in filters:
        status_text.text(f"🔍 Tarama Modu: {level['name']}")
        candidates = []
        
        for i, ticker in enumerate(tickers):
            df = fetch_data(ticker)
            if df is None: continue
            
            df = calculate_indicators(df)
            last = df.iloc[-1]
            
            if pd.isna(last['RSI']) or pd.isna(last['SMA50']): continue
            
            # Teknik Şartlar
            rsi_ok = last['RSI'] > level['rsi']
            sma_ok = last['Close'] > last['SMA50']
            macd_ok = last['MACD'] > last['MACD_SIGNAL']
            
            # Temel Şartlar (Son seviyede temel analiz yok)
            if level['name'] == '🔴 Zorunlu (Sadece Momentum)':
                fundamental_ok = True
            else:
                pe, pb, _ = get_fundamentals(ticker)
                fundamental_ok = (pe < level['pe']) and (pb < level['pb']) and (pe > 0)
            
            if rsi_ok and sma_ok and macd_ok and fundamental_ok:
                momentum = (last['Close'] / df.iloc[-30]['Close']) - 1 if len(df) >= 30 else 0
                candidates.append({
                    'Hisse': ticker,
                    'Fiyat': float(last['Close']),
                    'RSI': float(last['RSI']),
                    'F/K': float(pe) if 'pe' in locals() else 999,
                    'PD/DD': float(pb) if 'pb' in locals() else 999,
                    'Momentum': float(momentum),
                    'Filtre': level['name']
                })
            
            progress_bar.progress((i + 1) / len(tickers))
        
        # 5 Hisse Bulundu Mu?
        if len(candidates) >= 5:
            final_stocks = candidates
            used_filter = level['name']
            break
        else:
            # Bulamadıysa candidates'ı geçici hafızada tut (fallback için)
            all_candidates.extend(candidates)
    
    # Hiçbir seviye 5 hisse vermediyse, en iyi momentumlu olanları zorla seç
    if len(final_stocks) < 5:
        status_text.text("⚠️ Yeterli hisse bulunamadı, en iyi momentumlu hisseler seçiliyor...")
        if all_candidates:
            df_all = pd.DataFrame(all_candidates)
            top5 = df_all.sort_values(by='Momentum', ascending=False).head(5)
            final_stocks = top5.to_dict(orient='records')
            used_filter = "⚠️ Zorunlu Seçim (Filtre Dışı)"
        else:
            status_text.text("❌ Piyasada alınamacak hiç hisse yok.")
            return pd.DataFrame()
            
    status_text.text(f"✅ Tamamlandı: {used_filter}")
    return pd.DataFrame(final_stocks), used_filter

# -----------------------------------------------------------------------------
# 3. PORTFÖY YÖNETİMİ (KİLİT)
# -----------------------------------------------------------------------------
PORTFOLIO_FILE = 'portfoy_v2.json'

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return None
    return None

def save_portfolio(data):
    with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def delete_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        os.remove(PORTFOLIO_FILE)

# -----------------------------------------------------------------------------
# 4. ANA UYGULAMA
# -----------------------------------------------------------------------------
def main():
    st.title("🚀 BIST Portföy V2 (5 Hisse Garantili)")
    st.markdown("### 🇹🇷 Adaptif Algoritma | Otomatik Filtre Yumuşatma")
    
    # Uyarı Kutusu
    st.markdown("""
    <div class="alert-box">
        <strong>⚠️ ÖNEMLİ BİLGİ:</strong> Bu uygulama Streamlit Cloud üzerinde çalışmaktadır. 
        Ücretsiz sürümde dosya kilidi zaman zaman sıfırlanabilir. 
        Portföy oluşturduğunuzda hisseleri mutlaka bir yere not ediniz.
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    st.sidebar.header("⚙️ Kontrol Paneli")
    current_date = datetime.now()
    portfolio = load_portfolio()
    
    days_left = 0
    is_locked = False
    
    if portfolio:
        try:
            start_date = datetime.strptime(portfolio['start_date'], '%Y-%m-%d')
            end_date = start_date + timedelta(days=30)
            days_left = (end_date - current_date).days
            
            if days_left > 0:
                is_locked = True
                st.sidebar.error(f"🔒 Portföy Kilitli\n{days_left} gün kaldı.")
            else:
                st.sidebar.success("✅ Süre Doldu")
                if st.sidebar.button("Portföyü Sıfırla"):
                    delete_portfolio()
                    st.rerun()
        except:
            st.sidebar.error("Veri okuma hatası.")
            if st.sidebar.button("Veriyi Temizle"):
                delete_portfolio()
                st.rerun()
    else:
        st.sidebar.info("📭 Aktif Portföy Yok")
    
    # Üst Metrikler
    c1, c2, c3 = st.columns(3)
    c1.metric("Durum", "KİLİTLİ 🔒" if is_locked else "AÇIK ✅")
    c2.metric("Bugün", current_date.strftime("%d.%m.%Y"))
    if portfolio and 'start_date' in portfolio:
        c3.metric("Kilit Bitiş", (datetime.strptime(portfolio['start_date'], '%Y-%m-%d') + timedelta(days=30)).strftime("%d.%m.%Y"))
    else:
        c3.metric("Kilit Bitiş", "-")
    
    st.divider()
    
    # ---------------------------------------------------------------------
    # SENARYO 1: PORTFÖY OLUŞTURMA
    # ---------------------------------------------------------------------
    if not is_locked:
        st.subheader("📊 Yeni Portföy Oluştur")
        st.write("Sistem 5 hisse bulana kadar filtreleri otomatik gevşetecektir.")
        
        if st.button("🔍 5 HİSSE BUL VE KİLİTLE"):
            with st.spinner('⏳ Piyasa taranıyor (Bu işlem 1-2 dakika sürebilir)...'):
                result = analyze_market()
                
                if isinstance(result, tuple):
                    top5, filter_name = result
                else:
                    top5 = result
                    filter_name = ""
                
                if not top5.empty:
                    portfolio_data = {
                        'start_date': current_date.strftime('%Y-%m-%d'),
                        'stocks': top5.to_dict(orient='records'),
                        'filter_used': filter_name
                    }
                    save_portfolio(portfolio_data)
                    st.success(f"🎉 Portföy Oluşturuldu! (Filtre: {filter_name})")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("⚠️ Piyasada teknik olarak alınamacak hiç hisse bulunamadı.")
    
    # ---------------------------------------------------------------------
    # SENARYO 2: PORTFÖY GÖSTERİMİ
    # ---------------------------------------------------------------------
    else:
        st.subheader("🔒 Aktif Portföyünüz")
        st.write(f"Oluşturulma: **{portfolio['start_date']}** | Kalan: **{days_left} Gün**")
        if 'filter_used' in portfolio:
            st.caption(f"Seçim Filtresi: {portfolio['filter_used']}")
        
        stocks = portfolio['stocks']
        display_data = []
        total_invested = 0
        current_value = 0
        
        for stock in stocks:
            ticker = stock['Hisse']
            entry_price = float(stock['Fiyat'])
            try:
                df_now = fetch_data(ticker)
                if df_now is not None and not df_now.empty:
                    current_price = float(df_now['Close'].iloc[-1])
                else:
                    current_price = entry_price
                
                profit_pct = ((current_price - entry_price) / entry_price) * 100
                display_data.append({
                    'Hisse': ticker,
                    'Alış': f"{entry_price:.2f} ₺",
                    'Güncel': f"{current_price:.2f} ₺",
                    'Kar/Zarar': f"%{profit_pct:.2f}",
                    'Filtre': stock.get('Filtre', '-')
                })
                total_invested += 1000
                current_value += 1000 * (1 + profit_pct/100)
            except:
                display_data.append({'Hisse': ticker, 'Alış': f"{entry_price:.2f} ₺", 'Güncel': "-", 'Kar/Zarar': "-", 'Filtre': "-"})
        
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
        
        p1, p2 = st.columns(2)
        p1.metric("Toplam Yatırım", f"{total_invested:.2f} ₺")
        total_profit = current_value - total_invested
        p2.metric("Güncel Değer", f"{current_value:.2f} ₺", delta=f"{total_profit:.2f} ₺")

if __name__ == "__main__":
    main()
