import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import altair as alt # Görselleştirme için eklendi

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO AI", layout="wide", page_icon="🅱️")

# --- CSS VE TASARIM ---
st.markdown("""
    <style>
    .main > div {padding-top: 2rem;}
    .stChatInput {position: fixed; bottom: 3rem;}
    .block-container {padding-bottom: 5rem;}
    h1 {color: #d32f2f;}
    /* Metrik kutularını güzelleştir */
    div[data-testid="stMetric"] {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- API BİLGİLERİ ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    DFS_LOGIN = st.secrets["DFS_LOGIN"]
    DFS_PASSWORD = st.secrets["DFS_PASSWORD"]
    GSC_CREDENTIALS = {
        "type": "service_account",
        "project_id": st.secrets["GSC_PROJECT_ID"],
        "private_key_id": "optional",
        "private_key": st.secrets["GSC_PRIVATE_KEY"].replace('\\n', '\n'),
        "client_email": st.secrets["GSC_CLIENT_EMAIL"],
        "client_id": "optional",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{st.secrets['GSC_CLIENT_EMAIL']}"
    }
except Exception as e:
    st.error(f"Secret Hatası: {e}. Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()

# AI Modelini Başlat
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash') # Güncel ve hızlı model

# --- YARDIMCI FONKSİYONLAR ---

def classify_intent(keyword):
    """
    Basit kural tabanlı Search Intent (Niyet) analizi.
    Bunu AI ile yapmak daha maliyetli olacağı için kural tabanlı hızlı çözüm.
    """
    k = keyword.lower()
    if any(x in k for x in ['satın al', 'fiyat', 'ucuz', 'sipariş', 'kiralık', 'buy', 'price']):
        return "Transactional (İşlem)"
    elif any(x in k for x in ['en iyi', 'karşılaştırma', 'yorum', 'inceleme', 'vs', 'best', 'review']):
        return "Commercial (Ticari)"
    elif any(x in k for x in ['nedir', 'nasıl', 'ne demek', 'kimdir', 'tarifi', 'rehberi', 'what is', 'how to']):
        return "Informational (Bilgi)"
    else:
        return "Navigational/General"

def extract_date_range_from_prompt(user_prompt):
    today = datetime.date.today()
    prompt = f"""
    Bugünün tarihi: {today}
    Kullanıcı Girdisi: "{user_prompt}"
    GÖREV: Kullanıcının cümlesinden analiz etmek istediği TARİH ARALIĞINI çıkar.
    KURALLAR:
    1. Belirli bir tarih varsa (örn: "Ekim 2023") o tarihleri hesapla.
    2. Tarih yoksa (örn: "Düşüş var mı?"), varsayılan olarak SON 28 GÜNÜ al.
    3. Çıktı formatı SADECE: "YYYY-MM-DD|YYYY-MM-DD". Başka metin yazma.
    """
    try:
        response = model.generate_content(prompt)
        dates = response.text.strip().split('|')
        if len(dates) == 2:
            return dates[0], dates[1]
    except:
        pass
    start = today - datetime.timedelta(days=28)
    return str(start), str(today)

def get_gsc_raw_data(site_url, start_date, end_date):
    try:
        creds = service_account.Credentials.from_service_account_info(
            GSC_CREDENTIALS, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        service = build('searchconsole', 'v1', credentials=creds)
        request = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['query', 'page'], 
            'rowLimit': 1000 
        }
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        if 'rows' in response:
            data = []
            for row in response['rows']:
                data.append({
                    "Query": row['keys'][0],
                    "Page": row['keys'][1],
                    "Clicks": row['clicks'],
                    "Impressions": row['impressions'],
                    "CTR": round(row['ctr'] * 100, 2),
                    "Position": round(row['position'], 1)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        return None

def get_dfs_data(keyword, loc, lang):
    """
    DataForSEO API: 'related_keywords' endpoint'i daha zengin sonuçlar verebilir 
    ancak şimdilik 'keyword_ideas' üzerinden KD ve detayları alacağız.
    """
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    # limit'i biraz artırdık
    payload = [{
        "keywords": [keyword], 
        "location_code": loc, 
        "language_code": lang, 
        "limit": 600, 
        "include_seed_keyword": True,
        "include_serp_info": False # Hız için kapalı, detay gerekirse açılabilir
    }]
    
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()
        
        if response.status_code == 200 and res.get('tasks') and res['tasks'][0]['result']:
            items = res['tasks'][0]['result'][0]['items']
            data = []
            for i in items:
                kw_info = i.get('keyword_info', {})
                
                # Semrush/Ahrefs KD (Keyword Difficulty) mantığı
                # DataForSEO 'competition_index' verir (0-100). 
                kd = i.get('keyword_properties', {}).get('keyword_difficulty', kw_info.get('competition_index', 0))
                
                data.append({
                    "Keyword": i['keyword'],
                    "Volume": kw_info.get('search_volume', 0),
                    "CPC": kw_info.get('cpc', 0),
                    "KD %": kd, # Keyword Difficulty
                    "Competition": kw_info.get('competition_level', 'Unknown'),
                    "Trend": kw_info.get('monthly_searches', []) # Opsiyonel: Trend grafiği için
                })
            
            df = pd.DataFrame(data)
            # Intent Kolonu Ekle
            df['Intent'] = df['Keyword'].apply(classify_intent)
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"API Hatası: {e}")
        return None

# --- ANA UYGULAMA YAPISI ---

with st.sidebar:
    st.title("🅱️ PlanB SEO Tools")
    st.markdown("---")
    app_mode = st.radio("Araç Seçimi", ["🔍 Keyword Research (Pro)", "🤖 GSC AI Chatbot"])
    st.markdown("---")
    st.caption("v2.0 - Enhanced Metrics")

# ======================================================
# MOD 1: KEYWORD RESEARCH (PRO)
# ======================================================
if app_mode == "🔍 Keyword Research (Pro)":
    st.title("🔍 Keyword Magic Tool (DataForSEO Entegre)")
    st.markdown("Semrush/Ahrefs benzeri veri analizi ve içerik stratejisi.")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        keyword_input = st.text_input("Anahtar Kelime", placeholder="Örn: elektrikli süpürge")
    with col2:
        country_map = {"Türkiye": 2792, "ABD": 2840, "İngiltere": 2826}
        country = st.selectbox("Lokasyon", list(country_map.keys()))
    with col3:
        match_type = st.selectbox("Eşleme Türü", ["Geniş Eşleme (Broad)", "Tam Eşleme (Phrase)"])
    
    with st.expander("⚙️ Gelişmiş Filtreler & Rakipler", expanded=False):
        c1, c2 = st.columns(2)
        min_vol = c1.number_input("Min. Hacim", value=100, step=100)
        max_kd = c2.number_input("Maks. KD % (Zorluk)", value=80, step=5)
        target_website = st.text_input("Hedef Site (Opsiyonel)", placeholder="https://markam.com")
    
    if st.button("Analiz Et", type="primary") and keyword_input:
        with st.spinner(f"'{keyword_input}' için pazar verileri çekiliyor..."):
            
            # 1. Veriyi Çek
            lang = "tr" if country == "Türkiye" else "en"
            df = get_dfs_data(keyword_input, country_map[country], lang)
            
            if df is not None and not df.empty:
                # 2. Filtreleme Mantığı
                if match_type == "Tam Eşleme (Phrase)":
                    df = df[df['Keyword'].str.contains(keyword_input.lower())]
                
                # Sayısal Filtreler
                df = df[df['Volume'] >= min_vol]
                df = df[df['KD %'] <= max_kd]
                
                # Sıralama (Hacim ve KD öncelikli)
                df = df.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                
                if df.empty:
                    st.warning("Filtreleme kriterlerine uygun kelime bulunamadı. Filtreleri gevşetin.")
                else:
                    # --- ÜST METRİKLER ---
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Bulunan Kelime", len(df))
                    m1.caption("Filtrelenmiş")
                    m2.metric("Toplam Hacim", f"{df['Volume'].sum():,}")
                    m3.metric("Ort. KD %", round(df['KD %'].mean(), 1))
                    m4.metric("Potansiyel Tıklama", f"{(df['Volume'].sum() * 0.45):,.0f}") # Tahmini
                    
                    st.markdown("---")
                    
                    # --- GRAFİK (AHREFS TARZI BUBBLE CHART) ---
                    st.subheader("📊 Keyword Landscape")
                    
                    chart_data = df.head(50) # Grafik şişmesin diye top 50
                    
                    scatter = alt.Chart(chart_data).mark_circle().encode(
                        x=alt.X('KD %', title='Keyword Difficulty (Zorluk)'),
                        y=alt.Y('Volume', title='Search Volume (Hacim)'),
                        size=alt.Size('CPC', title='CPC', scale=alt.Scale(range=[50, 1000])),
                        color=alt.Color('Intent', legend=alt.Legend(title="Niyet")),
                        tooltip=['Keyword', 'Volume', 'KD %', 'CPC', 'Intent']
                    ).properties(height=400).interactive()
                    
                    st.altair_chart(scatter, use_container_width=True)
                    
                    # --- TABLO ---
                    st.subheader("📋 Kelime Listesi")
                    
                    # Dataframe'i daha şık gösterelim
                    st.dataframe(
                        df[['Keyword', 'Intent', 'Volume', 'KD %', 'CPC', 'Competition']],
                        use_container_width=True,
                        column_config={
                            "Volume": st.column_config.NumberColumn("Hacim", format="%d"),
                            "KD %": st.column_config.ProgressColumn("Zorluk", min_value=0, max_value=100, format="%d%%"),
                            "CPC": st.column_config.NumberColumn("CPC ($)", format="$%.2f"),
                        },
                        height=400
                    )
                    
                    # --- STRATEJİ ALANI (AI) ---
                    st.markdown("---")
                    st.subheader("🧠 AI Content Strategy")
                    
                    # AI'ya daha zengin veri gönderelim
                    top_keywords = df.head(15).to_csv(index=False)
                    intent_dist = df['Intent'].value_counts().to_string()
                    
                    prompt = f"""
                    Sen Kıdemli bir SEO Stratejistisin.
                    
                    ANALİZ VERİSİ:
                    - Konu: {keyword_input}
                    - Hedef Site: {target_website}
                    - Niyet Dağılımı: {intent_dist}
                    - En Hacimli Kelimeler (CSV):
                    {top_keywords}
                    
                    GÖREV:
                    1. Bu verisetine göre 3 adet 'Düşük Rekabet - Yüksek Hacim' (Low Hanging Fruit) fırsatını belirle.
                    2. Hangi içerik türüne (Blog, Kategori, Ürün sayfası) odaklanmalıyız?
                    3. Tablodaki verilere dayanarak kısa bir içerik briefi oluştur.
                    """
                    
                    if st.button("🚀 AI Strateji Oluştur"):
                        with st.spinner("Gemini verileri yorumluyor..."):
                            response = model.generate_content(prompt)
                            st.markdown(response.text)
            
            else:
                st.error("API'den veri alınamadı veya limit aşımı.")

# ======================================================
# MOD 2: GSC AI CHATBOT
# ======================================================
elif app_mode == "🤖 GSC AI Chatbot":
    st.title("🤖 GSC AI Data Analyst")
    st.caption("Veri aralığını kendi belirleyen akıllı asistan.")
    
    gsc_property = st.text_input("GSC Mülk URL'si", placeholder="sc-domain:markam.com veya https://markam.com/")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_gsc_data_range" not in st.session_state:
        st.session_state.current_gsc_data_range = None
    if "gsc_dataframe" not in st.session_state:
        st.session_state.gsc_dataframe = None

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Soru sor... (Örn: Geçen ay en çok düşen sayfalar?)"):
        
        if not gsc_property:
            st.error("Lütfen önce GSC Mülk adresini girin.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("Analiz yapılıyor..."):
                start_date, end_date = extract_date_range_from_prompt(prompt)
                current_range = f"{start_date}|{end_date}"
                
                # Veri yeni mi çekilmeli?
                if st.session_state.current_gsc_data_range != current_range:
                    df_gsc = get_gsc_raw_data(gsc_property, start_date, end_date)
                    
                    if df_gsc is not None and not df_gsc.empty:
                        st.session_state.gsc_dataframe = df_gsc
                        st.session_state.current_gsc_data_range = current_range
                        system_msg = f"📅 **{start_date}** - **{end_date}** verisi yüklendi ({len(df_gsc)} satır)."
                        st.session_state.messages.append({"role": "assistant", "content": system_msg})
                        st.markdown(f"*{system_msg}*")
                    else:
                        err_msg = "Veri bulunamadı veya API hatası."
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
                        st.markdown(err_msg)
                        st.stop()
                
                # AI Yanıtı
                if st.session_state.gsc_dataframe is not None:
                    df = st.session_state.gsc_dataframe
                    
                    # Veriyi küçültüp AI'ya özet geçiyoruz
                    total_clicks = df['Clicks'].sum()
                    top_queries = df.nlargest(30, 'Clicks')[['Query', 'Clicks', 'Position']].to_markdown()
                    top_pages = df.groupby('Page')['Clicks'].sum().nlargest(10).to_markdown()
                    
                    ai_context = f"""
                    DÖNEM: {start_date} ile {end_date} arası.
                    TOPLAM TIKLAMA: {total_clicks}
                    
                    EN İYİ SORGULAR:
                    {top_queries}
                    
                    EN İYİ SAYFALAR:
                    {top_pages}
                    """
                    
                    full_prompt = f"""
                    Sen SEO Analistisin. Veri seti:
                    {ai_context}
                    
                    Soru: "{prompt}"
                    
                    Yanıtında mutlaka sayısal verileri kullan. Kısa ve net ol.
                    """
                    
                    try:
                        response = model.generate_content(full_prompt)
                        ai_reply = response.text
                        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                        with st.chat_message("assistant"):
                            st.markdown(ai_reply)
                    except Exception as e:
                        st.error(f"AI Hatası: {e}")
