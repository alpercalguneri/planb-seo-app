import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
from dateutil.relativedelta import relativedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO AI", layout="wide", page_icon="🅱️")

# --- CSS ---
st.markdown("""
    <style>
    .main > div {padding-top: 1rem;}
    h1 {color: #d32f2f;}
    div[data-testid="stMetricValue"] {font-size: 1.6rem;}
    </style>
    """, unsafe_allow_html=True)

# --- API VE GÜVENLİK ---
try:
    # Secrets dosyasından bilgileri al
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    DFS_LOGIN = st.secrets["DFS_LOGIN"]
    DFS_PASSWORD = st.secrets["DFS_PASSWORD"]
    
    # GSC Service Account Bilgileri (Secrets içinde JSON objesi olarak saklanacak)
    # Streamlit Cloud'da secrets toml formatında olduğu için dict olarak alırız
    gsc_info = st.secrets["gsc_service_account"]
except Exception as e:
    st.error(f"Secret hatası: {e}. Lütfen secrets.toml dosyasını yapılandırın.")
    st.stop()

# Gemini Konfigürasyonu
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- SESSION STATE ---
if 'brands' not in st.session_state:
    st.session_state.brands = {} 
if 'active_brand' not in st.session_state:
    st.session_state.active_brand = "Genel"
    st.session_state.brands["Genel"] = {
        "context": "Genel SEO", 
        "gsc_url": "", 
        "competitors": ["", "", ""],
        "brand_keywords": "" # Marka adının varyasyonları
    }
if 'messages' not in st.session_state:
    st.session_state.messages = []

# --- YARDIMCI FONKSİYONLAR (GSC) ---

@st.cache_resource
def get_gsc_service():
    """Google Search Console API Servisini Başlatır"""
    creds = service_account.Credentials.from_service_account_info(
        gsc_info, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
    )
    return build('searchconsole', 'v1', credentials=creds)

@st.cache_data(ttl=3600)
def fetch_gsc_data(site_url, start_date, end_date):
    """Belirli tarih aralığında GSC verisi çeker"""
    service = get_gsc_service()
    request = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['query', 'date'],
        'rowLimit': 5000
    }
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        if rows:
            data = []
            for row in rows:
                data.append({
                    'Date': row['keys'][1],
                    'Query': row['keys'][0],
                    'Clicks': row['clicks'],
                    'Impressions': row['impressions'],
                    'CTR': row['ctr'],
                    'Position': row['position']
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        return None

# --- YARDIMCI FONKSİYONLAR (DataForSEO) ---
def get_dataforseo_data(keyword, loc, lang):
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    payload = [{"keywords": [keyword], "location_code": loc, "language_code": lang, "limit": 800, "include_seed_keyword": True}]
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
        return None

# --- SIDEBAR: MARKA YÖNETİMİ ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2702/2702602.png", width=50)
    st.header("🏢 Marka Paneli")
    
    brand_list = list(st.session_state.brands.keys())
    selected_brand = st.selectbox("Seçili Marka", brand_list, index=brand_list.index(st.session_state.active_brand))
    
    # Marka Değişimi Kontrolü
    if selected_brand != st.session_state.active_brand:
        st.session_state.active_brand = selected_brand
        st.session_state.messages = [] # Chat geçmişini temizle
        st.rerun()

    # Yeni Marka Ekleme
    new_brand_name = st.text_input("➕ Yeni Marka Ekle")
    if st.button("Ekle"):
        if new_brand_name and new_brand_name not in st.session_state.brands:
            st.session_state.brands[new_brand_name] = {
                "context": "", "gsc_url": "", "competitors": ["", "", ""], "brand_keywords": ""
            }
            st.session_state.active_brand = new_brand_name
            st.rerun()
            
    st.divider()
    
    # Aktif Marka Ayarları
    active_data = st.session_state.brands[st.session_state.active_brand]
    st.subheader(f"⚙️ {st.session_state.active_brand} Ayarları")
    
    gsc_url_input = st.text_input("GSC Mülk URL (sc-domain: veya https://)", value=active_data["gsc_url"], placeholder="sc-domain:altinyildiz.com")
    brand_kws_input = st.text_input("Marka Kelimeleri (Virgülle ayır)", value=active_data["brand_keywords"], placeholder="altınyıldız, classics")
    brand_context_input = st.text_area("Marka Özeti", value=active_data["context"])
    
    # Kaydet
    st.session_state.brands[st.session_state.active_brand]["gsc_url"] = gsc_url_input
    st.session_state.brands[st.session_state.active_brand]["brand_keywords"] = brand_kws_input
    st.session_state.brands[st.session_state.active_brand]["context"] = brand_context_input


# --- ANA EKRAN ---
st.title(f"PlanB Media SEO Agent - {st.session_state.active_brand}")

tab1, tab2 = st.tabs(["🔍 Keyword Research", "🤖 GSC Chatbot"])

# --- TAB 1: KEYWORD RESEARCH ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        keyword_input = st.text_input("Anahtar Kelime Ara", "takım elbise")
    with col2:
        country_map = {"Türkiye": 2792, "ABD": 2840}
        country = st.selectbox("Hedef Ülke", list(country_map.keys()))
        
    if st.button("Analiz Et", type="primary"):
        with st.spinner("Veriler çekiliyor..."):
            df = get_dataforseo_data(keyword_input, country_map[country], "tr" if country=="Türkiye" else "en")
            if df is not None and not df.empty:
                # Basit filtre
                df = df[df['Keyword'].str.contains(keyword_input.lower())]
                st.dataframe(df.sort_values("Volume", ascending=False), use_container_width=True)
                
                # Gemini Önerisi
                top_kw = ", ".join(df.head(5)['Keyword'].tolist())
                prompt = f"Anahtar kelimeler: {top_kw}. Marka: {st.session_state.active_brand}. Konsept: {active_data['context']}. Bana 3 tane blog başlığı öner."
                res = model.generate_content(prompt)
                st.info(res.text)
            else:
                st.warning("Veri bulunamadı.")

# --- TAB 2: GSC CHATBOT ---
with tab2:
    if not active_data["gsc_url"]:
        st.warning("⚠️ Lütfen sol menüden GSC Mülk URL'sini girin.")
    else:
        st.subheader("📊 Canlı GSC Analizi & Asistan")
        
        # Otomatik Veri Hazırlığı (Son 30 gün vs Geçen Yıl)
        # Bunu önbelleğe alıp Gemini'ye context olarak vereceğiz.
        
        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        
        # Geçen sene aynı dönem
        last_year_start = (today - datetime.timedelta(days=395)).strftime("%Y-%m-%d")
        last_year_end = (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d")

        with st.spinner("GSC verileri analiz ediliyor... (Bu işlem birkaç saniye sürebilir)"):
            df_current = fetch_gsc_data(active_data["gsc_url"], start_date, end_date)
            df_last_year = fetch_gsc_data(active_data["gsc_url"], last_year_start, last_year_end)
        
        if df_current is not None and not df_current.empty:
            # Marka / Marka Dışı Ayrımı Hesaplama
            brand_kws = [k.strip().lower() for k in active_data["brand_keywords"].split(",") if k.strip()]
            
            def classify_brand(query):
                if not brand_kws: return "Genel"
                return "Marka" if any(b in str(query).lower() for b in brand_kws) else "Marka Dışı"

            df_current['Type'] = df_current['Query'].apply(classify_brand)
            if df_last_year is not None and not df_last_year.empty:
                df_last_year['Type'] = df_last_year['Query'].apply(classify_brand)
            
            # Özet İstatistikler (Gemini Context İçin)
            total_clicks = df_current['Clicks'].sum()
            brand_clicks = df_current[df_current['Type']=="Marka"]['Clicks'].sum()
            
            ly_clicks = df_last_year['Clicks'].sum() if df_last_year is not None else 0
            ly_brand_clicks = df_last_year[df_last_year['Type']=="Marka"]['Clicks'].sum() if df_last_year is not None else 0
            
            # Veri Özeti Metni
            data_summary = f"""
            GSC VERİ ÖZETİ ({start_date} - {end_date}):
            - Toplam Tıklama: {total_clicks} (Geçen sene aynı dönem: {ly_clicks})
            - Marka (Brand) Trafiği: {brand_clicks} (Geçen sene: {ly_brand_clicks})
            - Marka Dışı (Non-Brand) Trafiği: {total_clicks - brand_clicks}
            - En çok trafik getiren 5 kelime: {', '.join(df_current.groupby('Query')['Clicks'].sum().nlargest(5).index.tolist())}
            """
            
            # Chat Arayüzü
            for msg in st.session_state.messages:
                st.chat_message(msg["role"]).write(msg["content"])

            if user_input := st.chat_input("GSC verileri hakkında soru sor (Örn: Geçen seneye göre marka trafiğim nasıl?)"):
                st.chat_message("user").write(user_input)
                st.session_state.messages.append({"role": "user", "content": user_input})
                
                # Gemini Prompt
                full_prompt = f"""
                Sen bir SEO uzmanısın. Aşağıdaki veri özetini kullanarak kullanıcının sorusunu cevapla.
                Marka: {st.session_state.active_brand}
                
                VERİLER:
                {data_summary}
                
                KULLANICI SORUSU:
                {user_input}
                
                Yorum yaparken profesyonel ol, yüzdelik değişimleri hesapla ve stratejik öneri ver.
                """
                
                try:
                    ai_response = model.generate_content(full_prompt)
                    st.chat_message("assistant").write(ai_response.text)
                    st.session_state.messages.append({"role": "assistant", "content": ai_response.text})
                except Exception as e:
                    st.error("AI yanıt veremedi.")
        else:
            st.error("GSC verisi çekilemedi. Yetkileri ve URL'i kontrol edin.")
