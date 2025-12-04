import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO Agent", layout="wide", page_icon="🅱️")

# --- CSS VE TASARIM ---
st.markdown("""
    <style>
    .main > div {padding-top: 1rem;}
    h1 {color: #d32f2f;}
    .stTabs [data-baseweb="tab-list"] {gap: 10px;}
    .stTabs [data-baseweb="tab"] {height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 5px;}
    .stTabs [aria-selected="true"] {background-color: #d32f2f; color: white;}
    div[data-testid="stMetricValue"] {font-size: 1.4rem;}
    </style>
    """, unsafe_allow_html=True)

# --- API VE GÜVENLİK ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    DFS_LOGIN = st.secrets["DFS_LOGIN"]
    DFS_PASSWORD = st.secrets["DFS_PASSWORD"]
    gsc_info = st.secrets["gsc_service_account"]
except Exception as e:
    st.error("Secrets yapılandırması eksik! Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash') # Daha hızlı ve güncel model varsa onu kullanır

# --- SESSION STATE ---
if 'brands' not in st.session_state:
    st.session_state.brands = {} 

if 'active_brand' not in st.session_state:
    st.session_state.active_brand = "Varsayılan Proje"
    st.session_state.brands["Varsayılan Proje"] = {
        "context": "Genel SEO projesi", 
        "gsc_url": "", 
        "brand_keywords": "",
        "gsc_data": None, # GSC verisini hafızada tutmak için
        "gsc_summary": "" # Chatbot'a gidecek özet
    }

if 'messages' not in st.session_state:
    st.session_state.messages = []

# --- YARDIMCI FONKSİYONLAR ---

@st.cache_resource
def get_gsc_service():
    """GSC API Servisini başlatır"""
    creds = service_account.Credentials.from_service_account_info(
        gsc_info, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
    )
    return build('searchconsole', 'v1', credentials=creds)

def fetch_gsc_data_dynamic(site_url, start_date, end_date):
    """GSC'den veri çeker (Limit artırıldı)"""
    service = get_gsc_service()
    request = {
        'startDate': start_date.strftime("%Y-%m-%d"),
        'endDate': end_date.strftime("%Y-%m-%d"),
        'dimensions': ['query'], # Sadece Query bazlı analiz
        'rowLimit': 25000 # Daha geniş veri seti
    }
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        if rows:
            data = []
            for row in rows:
                data.append({
                    'Query': row['keys'][0],
                    'Clicks': row['clicks'],
                    'Impressions': row['impressions'],
                    'CTR': row['ctr'],
                    'Position': row['position']
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"GSC API Hatası: {e}")
        return None

def get_dataforseo_data(keyword, loc, lang):
    """Keyword Research API"""
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    payload = [{"keywords": [keyword], "location_code": loc, "language_code": lang, "limit": 700, "include_seed_keyword": True}]
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()
        if response.status_code == 200 and res.get('tasks') and res['tasks'][0]['result']:
            items = res['tasks'][0]['result'][0]['items']
            data = []
            for i in items:
                kw_info = i.get('keyword_info', {})
                data.append({
                    "Keyword": i['keyword'],
                    "Volume": kw_info.get('search_volume', 0),
                    "CPC": kw_info.get('cpc', 0),
                    "Competition": int(float(kw_info.get('competition_level', 0)) * 100)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"DFS API Hatası: {e}")
        return None

# --- SIDEBAR: SADECE MARKA SEÇİMİ ---
with st.sidebar:
    st.title("PlanB SEO")
    
    # Marka Seçimi
    brand_list = list(st.session_state.brands.keys())
    selected_brand = st.selectbox("Aktif Proje", brand_list, index=brand_list.index(st.session_state.active_brand))
    
    if selected_brand != st.session_state.active_brand:
        st.session_state.active_brand = selected_brand
        st.session_state.messages = [] # Marka değişirse chat sıfırlanır
        st.rerun()
        
    # Yeni Marka Ekle
    with st.popover("➕ Yeni Proje Ekle"):
        new_brand = st.text_input("Proje Adı")
        if st.button("Oluştur") and new_brand:
            if new_brand not in st.session_state.brands:
                st.session_state.brands[new_brand] = {"context": "", "gsc_url": "", "brand_keywords": "", "gsc_data": None}
                st.session_state.active_brand = new_brand
                st.rerun()

    st.info(f"Şu an **{st.session_state.active_brand}** projesi üzerinde çalışıyorsunuz.")

# --- ANA EKRAN ---

st.title(f"🚀 {st.session_state.active_brand} - SEO Kokpiti")

tab_kw, tab_gsc = st.tabs(["🔍 Keyword Research", "🤖 GSC Chatbot & Analiz"])

# ==========================================
# TAB 1: KEYWORD RESEARCH (Tamamen Ayrıldı)
# ==========================================
with tab_kw:
    st.subheader("Anahtar Kelime Araştırması")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        kw_input = st.text_input("Anahtar Kelime", placeholder="Örn: erkek takım elbise")
    with col2:
        country_map = {"Türkiye": 2792, "ABD": 2840, "Almanya": 2276, "İngiltere": 2826}
        country = st.selectbox("Lokasyon", list(country_map.keys()))
    with col3:
        st.write("") # Boşluk
        btn_analyze = st.button("Analiz Et", type="primary", use_container_width=True)
        
    if btn_analyze and kw_input:
        with st.spinner("DataForSEO verileri çekiliyor..."):
            lang = "tr" if country == "Türkiye" else "en"
            df_kw = get_dataforseo_data(kw_input, country_map[country], lang)
            
            if df_kw is not None and not df_kw.empty:
                # Alaka düzeyi filtresi
                df_kw = df_kw[df_kw['Keyword'].str.contains(kw_input.lower())]
                df_kw = df_kw.sort_values("Volume", ascending=False).reset_index(drop=True)
                
                # Metrikler
                m1, m2, m3 = st.columns(3)
                m1.metric("Toplam Kelime", len(df_kw))
                m2.metric("Toplam Hacim", f"{df_kw['Volume'].sum():,}")
                m3.metric("En Yüksek Hacim", f"{df_kw['Volume'].max():,}")
                
                st.dataframe(df_kw, use_container_width=True, height=400)
                
                # AI Yorumu
                if not df_kw.empty:
                    top_5 = ", ".join(df_kw.head(5)['Keyword'].tolist())
                    st.info(f"💡 **AI Önerisi:** En hacimli kelimeler ({top_5}) üzerine odaklanarak kategori ağacını genişletebilirsin.")
            else:
                st.warning("Veri bulunamadı.")

# ==========================================
# TAB 2: GSC CHATBOT (Inputlar Buraya Taşındı)
# ==========================================
with tab_gsc:
    active_data = st.session_state.brands[st.session_state.active_brand]
    
    # --- GSC AYARLARI ---
    with st.expander("⚙️ GSC Ayarları ve Veri Güncelleme", expanded=True):
        c_url, c_brand = st.columns(2)
        with c_url:
            gsc_url_val = st.text_input("GSC Mülk URL (sc-domain: veya https://)", 
                                      value=active_data.get("gsc_url", ""), 
                                      placeholder="sc-domain:example.com")
        with c_brand:
            brand_kws_val = st.text_input("Marka Kelimeleri (Virgülle ayır)", 
                                        value=active_data.get("brand_keywords", ""), 
                                        placeholder="marka adı, markaadi, brandname")
        
        c_date1, c_date2 = st.columns(2)
        today = datetime.date.today()
        last_30 = today - datetime.timedelta(days=30)
        
        with c_date1:
            start_date = st.date_input("Başlangıç Tarihi", value=last_30)
        with c_date2:
            end_date = st.date_input("Bitiş Tarihi", value=today)
            
        btn_gsc_fetch = st.button("Verileri Getir & Analiz Et", type="primary")

    # Ayarları kaydet
    if gsc_url_val:
        st.session_state.brands[st.session_state.active_brand]["gsc_url"] = gsc_url_val
        st.session_state.brands[st.session_state.active_brand]["brand_keywords"] = brand_kws_val

    # --- VERİ ÇEKME VE İŞLEME ---
    if btn_gsc_fetch:
        if not gsc_url_val:
            st.error("Lütfen GSC URL'sini girin.")
        else:
            with st.spinner("GSC verileri çekiliyor ve sınıflandırılıyor..."):
                df_gsc = fetch_gsc_data_dynamic(gsc_url_val, start_date, end_date)
                
                if df_gsc is not None and not df_gsc.empty:
                    # 1. Brand / Non-Brand Sınıflandırma (Gelişmiş)
                    brand_tokens = [b.strip().lower() for b in brand_kws_val.split(',') if b.strip()]
                    
                    def classify_brand(query):
                        q_str = str(query).lower()
                        if not brand_tokens: return "Belirsiz" # Marka kelimesi girilmemişse
                        # Token'lardan herhangi biri sorgunun içinde geçiyor mu?
                        if any(token in q_str for token in brand_tokens):
                            return "Brand"
                        return "Non-Brand"

                    df_gsc['Type'] = df_gsc['Query'].apply(classify_brand)
                    
                    # Veriyi Session State'e kaydet
                    st.session_state.brands[st.session_state.active_brand]["gsc_data"] = df_gsc
                    
                    # 2. İstatistik Hazırlama (AI için Context)
                    total_clicks = df_gsc['Clicks'].sum()
                    total_imp = df_gsc['Impressions'].sum()
                    
                    # Brand vs Non-Brand
                    brand_df = df_gsc[df_gsc['Type'] == 'Brand']
                    nonbrand_df = df_gsc[df_gsc['Type'] == 'Non-Brand']
                    
                    brand_clicks = brand_df['Clicks'].sum()
                    nonbrand_clicks = nonbrand_df['Clicks'].sum()
                    
                    top_queries = df_gsc.nlargest(20, 'Clicks')[['Query', 'Clicks', 'Type']].to_string(index=False)
                    
                    summary_text = f"""
                    ANALİZ DÖNEMİ: {start_date} - {end_date}
                    
                    GENEL PERFORMANS:
                    - Toplam Tıklama: {total_clicks:,}
                    - Toplam Gösterim: {total_imp:,}
                    
                    MARKA TRAFİĞİ ANALİZİ (Brand vs Non-Brand):
                    - Brand Trafiği (Tıklama): {brand_clicks:,} (Oran: %{round(brand_clicks/total_clicks*100, 1) if total_clicks>0 else 0})
                    - Non-Brand Trafiği (Tıklama): {nonbrand_clicks:,}
                    
                    EN ÇOK TRAFİK GETİREN 20 SORGU:
                    {top_queries}
                    """
                    st.session_state.brands[st.session_state.active_brand]["gsc_summary"] = summary_text
                    st.success("Veriler başarıyla güncellendi! Aşağıdaki Chatbot'u kullanabilirsiniz.")
                else:
                    st.warning("Seçilen tarih aralığında veri bulunamadı veya yetki hatası.")

    # --- CHATBOT ARAYÜZÜ ---
    st.divider()
    st.subheader("💬 AI Asistan")
    
    # Hafızadaki veriyi kontrol et
    current_df = st.session_state.brands[st.session_state.active_brand].get("gsc_data")
    summary_context = st.session_state.brands[st.session_state.active_brand].get("gsc_summary")

    if current_df is None:
        st.info("Lütfen yukarıdan 'Verileri Getir' butonuna basarak analizi başlatın.")
    else:
        # Chat Geçmişini Göster
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

        # Yeni Mesaj Girişi
        if prompt := st.chat_input("Örn: Brand trafiğim toplamın yüzde kaçı? En iyi kelimelerim neler?"):
            st.chat_message("user").write(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Gemini'ye Context ile Gönder
            full_prompt = f"""
            Sen uzman bir SEO Analistisin. Aşağıdaki Google Search Console verilerini analiz ederek kullanıcının sorusunu yanıtla.
            
            VERİ ÖZETİ:
            {summary_context}
            
            KULLANICI SORUSU:
            {prompt}
            
            YÖNERGELER:
            1. Cevapların net ve veriye dayalı olsun.
            2. Yüzdelik hesaplamalar yap.
            3. Brand ve Non-Brand ayrımına dikkat et.
            4. Eğer veri özetinde bilgi yoksa (örn: spesifik tek bir kelime), "Elimdeki özet veride bu detay yok ama genel tabloya göre..." şeklinde cevapla.
            """
            
            with st.spinner("AI düşünüyor..."):
                try:
                    response = model.generate_content(full_prompt)
                    ai_reply = response.text
                    st.chat_message("assistant").write(ai_reply)
                    st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                except Exception as e:
                    st.error(f"AI Hatası: {e}")

        # Veri Tablosunu Gösterme Opsiyonu (Debug için)
        with st.expander("📊 Ham Veriyi İncele"):
            st.dataframe(current_df, use_container_width=True)
