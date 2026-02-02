import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import altair as alt
import time
from google.api_core import exceptions
import json

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO AI", layout="wide", page_icon="🅱️")

# --- CSS VE TASARIM ---
st.markdown("""
    <style>
    .main > div {padding-top: 2rem;}
    .stChatInput {position: fixed; bottom: 3rem; z-index: 100;}
    .block-container {padding-bottom: 7rem;}
    h1 {color: #d32f2f;}
    
    /* Metric Kutusu */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    div[data-testid="stMetric"] label { color: #31333F !important; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #d32f2f !important;
        font-weight: 700 !important;
    }
    
    /* Butonlar */
    div.stButton > button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        font-weight: 600;
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
    st.error(f"🚨 Secret Hatası: {e}. Lütfen .streamlit/secrets.toml dosyasını kontrol edin.")
    st.stop()

# AI Model
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- YARDIMCI FONKSİYONLAR ---

def generate_safe(prompt_input):
    """API 429 Hata Yönetimi"""
    try:
        return model.generate_content(prompt_input)
    except exceptions.ResourceExhausted:
        st.toast("⏳ API yoğun, 5 saniye bekleniyor...", icon="🤖")
        time.sleep(5)
        try:
            return model.generate_content(prompt_input)
        except Exception as e:
            st.error(f"Hata: {e}")
            return None
    except Exception as e:
        st.error(f"Beklenmedik Hata: {e}")
        return None

def classify_intent(keyword):
    k = keyword.lower()
    if any(x in k for x in ['satın al', 'fiyat', 'ucuz', 'sipariş', 'kiralık', 'buy', 'price']):
        return "Transactional"
    elif any(x in k for x in ['en iyi', 'karşılaştırma', 'yorum', 'inceleme', 'vs', 'best', 'review']):
        return "Commercial"
    elif any(x in k for x in ['nedir', 'nasıl', 'ne demek', 'kimdir', 'tarifi', 'rehberi', 'what is', 'how to']):
        return "Informational"
    else:
        return "Navigational/General"

@st.cache_data(ttl=3600, show_spinner=False)
def extract_date_range_from_prompt(user_prompt):
    today = datetime.date.today()
    prompt = f"""
    Bugünün tarihi: {today}
    Kullanıcı Girdisi: "{user_prompt}"
    GÖREV: Girdide YENİ bir tarih aralığı isteği var mı?
    VARSA FORMATI: "YYYY-MM-DD|YYYY-MM-DD"
    YOKSA: "NONE"
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "NONE" in text: return None
        dates = text.split('|')
        if len(dates) == 2: return dates[0].strip(), dates[1].strip()
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_gsc_raw_data(site_url, start_date, end_date):
    try:
        creds = service_account.Credentials.from_service_account_info(
            GSC_CREDENTIALS, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        service = build('searchconsole', 'v1', credentials=creds)
        request = {
            'startDate': start_date, 'endDate': end_date,
            'dimensions': ['query', 'page'], 'rowLimit': 2000 
        }
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        if 'rows' in response:
            data = []
            for row in response['rows']:
                data.append({
                    "Query": row['keys'][0], "Page": row['keys'][1],
                    "Clicks": row['clicks'], "Impressions": row['impressions'],
                    "CTR": round(row['ctr'] * 100, 2), "Position": round(row['position'], 1)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        print(f"GSC Error: {e}")
        return None

@st.cache_data(ttl=86400)
def get_dfs_data(keyword, loc, lang):
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    payload = [{
        "keywords": [keyword], "location_code": loc, "language_code": lang,
        "limit": 700, "include_seed_keyword": True, "include_serp_info": False 
    }]
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()
        if response.status_code == 200 and res.get('tasks') and res['tasks'][0]['result']:
            items = res['tasks'][0]['result'][0]['items']
            data = []
            for i in items:
                kw_info = i.get('keyword_info', {})
                if kw_info is None: continue 
                kd = i.get('keyword_properties', {}).get('keyword_difficulty', kw_info.get('competition_index', 0))
                data.append({
                    "Keyword": i['keyword'], "Volume": kw_info.get('search_volume', 0),
                    "CPC": kw_info.get('cpc', 0), "KD %": kd, 
                    "Competition": kw_info.get('competition_level', 'Unknown')
                })
            df = pd.DataFrame(data)
            if not df.empty: df['Intent'] = df['Keyword'].apply(classify_intent)
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"API Bağlantı Hatası: {e}")
        return None

def semantic_filter_keywords(df, target_site, competitors):
    keywords_list = df['Keyword'].head(50).tolist()
    prompt = f"""
    Sen uzman bir SEO editörüsün. Aşağıdaki kelime listesini temizlemen gerekiyor.
    BAĞLAM: Hedef Site: {target_site}, Rakipler: {competitors}
    GÖREV: Bu alanla ALAKASIZ olan kelimeleri çıkar. Sadece alakalı olanları JSON listesi olarak döndür.
    LİSTE: {keywords_list}
    ÇIKTI: ["kelime1", "kelime2"]
    """
    try:
        res = generate_safe(prompt)
        if res:
            clean_text = res.text.replace("```json", "").replace("```", "").strip()
            kept_keywords = json.loads(clean_text)
            return df[df['Keyword'].isin(kept_keywords)]
    except: return df
    return df

# --- SIDEBAR ---
with st.sidebar:
    st.title("🅱️ PlanB SEO Tools")
    st.markdown("---")
    app_mode = st.radio("Mod Seçimi", ["🔍 Keyword Research (Pro)", "🤖 GSC AI Chatbot"])
    st.markdown("---")
    st.info("💡 **İpucu:** GSC, Genel Sorular ve Strateji. Hepsi bir arada.")
    st.caption("In-House Tool v3.1 (Hybrid Mode)")

# ======================================================
# MOD 1: KEYWORD RESEARCH (PRO)
# ======================================================
if app_mode == "🔍 Keyword Research (Pro)":
    st.title("🔍 Keyword Magic Tool")
    
    if "df_search_results" not in st.session_state: st.session_state.df_search_results = None
    if "analyzed_keyword" not in st.session_state: st.session_state.analyzed_keyword = ""

    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        keyword_input = st.text_input("Anahtar Kelime", placeholder="Örn: elektrikli süpürge")
    with col2:
        loc_map = {"Türkiye": 2792, "ABD": 2840, "İngiltere": 2826, "Almanya": 2276, "Fransa": 2250, "İspanya": 2724}
        country = st.selectbox("Lokasyon", list(loc_map.keys()))
    with col3:
        lang_map = {"Türkçe": "tr", "İngilizce": "en", "Almanca": "de", "Fransızca": "fr", "İspanyolca": "es"}
        selected_lang = st.selectbox("Dil", list(lang_map.keys()))
    with col4:
        match_type = st.selectbox("Eşleme", ["Geniş", "Tam (Phrase)"])
    
    with st.expander("⚔️ Semantic Bağlam Ayarları", expanded=True):
        st.info("AI'nın doğru kelimeleri önermesi için hedef ve rakipleri girin.")
        target_website = st.text_input("Hedef Web Sitesi", placeholder="https://markam.com")
        rc1, rc2 = st.columns(2)
        comp1 = rc1.text_input("Rakip 1", placeholder="rakip1.com")
        comp2 = rc2.text_input("Rakip 2", placeholder="rakip2.com")
    
    if st.button("Analizi Başlat", type="primary"):
        if keyword_input and target_website:
            with st.spinner(f"'{keyword_input}' taranıyor ve anlamsal olarak filtreleniyor..."):
                lang_code = lang_map[selected_lang]
                loc_code = loc_map[country]
                raw_df = get_dfs_data(keyword_input, loc_code, lang_code)
                
                if raw_df is not None and not raw_df.empty:
                    if match_type == "Tam (Phrase)":
                        raw_df = raw_df[raw_df['Keyword'].str.contains(keyword_input.lower())]
                    
                    competitors = ", ".join([c for c in [comp1, comp2] if c])
                    filtered_df = semantic_filter_keywords(raw_df, target_website, competitors)
                    filtered_df = filtered_df.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                    st.session_state.df_search_results = filtered_df
                    st.session_state.analyzed_keyword = keyword_input
                    st.rerun()
                else:
                    st.error("Veri bulunamadı veya API hatası.")
        else:
            st.warning("Lütfen zorunlu alanları doldurun.")

    if st.session_state.df_search_results is not None and not st.session_state.df_search_results.empty:
        df = st.session_state.df_search_results
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Alakalı Kelime", len(df))
        m2.metric("Toplam Hacim", f"{df['Volume'].sum():,}")
        m3.metric("Ort. KD %", round(df['KD %'].mean(), 1))
        m4.metric("Tahmini Trafik", f"{(df['Volume'].sum() * 0.3):,.0f}")
        
        chart_data = df.head(100)
        scatter = alt.Chart(chart_data).mark_circle().encode(
            x=alt.X('KD %', title='Keyword Difficulty'),
            y=alt.Y('Volume', title='Search Volume'),
            size='CPC',
            color=alt.Color('Intent', scale=alt.Scale(scheme='category10')),
            tooltip=['Keyword', 'Volume', 'KD %', 'CPC', 'Intent']
        ).properties(height=400, title="Semantic Keyword Landscape").interactive()
        st.altair_chart(scatter, use_container_width=True)
        
        st.dataframe(df[['Keyword', 'Intent', 'Volume', 'KD %', 'CPC', 'Competition']], use_container_width=True, height=400)
        
        st.divider()
        st.subheader("💡 AI Content Strategy")
        if st.button("🚀 Strateji Oluştur"):
            comps = ", ".join([c for c in [comp1, comp2] if c])
            top_kw = df.head(20)[['Keyword', 'Volume', 'KD %']].to_csv(index=False)
            prompt = f"Sen Kıdemli bir SEO Stratejistisin. Site: {target_website}, Rakipler: {comps}, Kelimeler: {top_kw}. Görev: 3 adet 'Content Cluster' öner."
            with st.spinner("Strateji kurgulanıyor..."):
                res = generate_safe(prompt)
                if res: st.markdown(res.text)

# ======================================================
# MOD 2: GSC AI CHATBOT (HYBRID MODE UPDATE)
# ======================================================
elif app_mode == "🤖 GSC AI Chatbot":
    st.title("🤖 GSC AI Data Analyst")

    if "target_gsc_url" not in st.session_state:
        st.session_state.target_gsc_url = ""

    st.caption("Marka Seçimi:")
    b_col1, b_col2, b_col3 = st.columns([1, 1, 2])
    
    with b_col1:
        if st.button("👔 Brooks Brothers"):
            st.session_state.target_gsc_url = "https://www.brooksbrothers.com.tr/"
            st.session_state.messages = []
            st.session_state.gsc_dataframe = None
            st.rerun()

    with b_col2:
        if st.button("🌿 Mellow Rush"):
            st.session_state.target_gsc_url = "sc-domain:mellowrush.me"
            st.session_state.messages = []
            st.session_state.gsc_dataframe = None
            st.rerun()

    with b_col3:
        if st.button("🗑️ Temizle", type="secondary"):
            st.session_state.messages = []
            st.session_state.target_gsc_url = ""
            st.rerun()

    gsc_property = st.text_input(
        "GSC Mülk URL'si", 
        value=st.session_state.target_gsc_url,
        placeholder="sc-domain:markam.com veya https://markam.com"
    )
    
    if gsc_property != st.session_state.target_gsc_url:
        st.session_state.target_gsc_url = gsc_property

    if "messages" not in st.session_state: st.session_state.messages = []
    if "gsc_dataframe" not in st.session_state: st.session_state.gsc_dataframe = None
    if "active_date_range" not in st.session_state: 
        end = datetime.date.today()
        start = end - datetime.timedelta(days=28)
        st.session_state.active_date_range = (str(start), str(end))

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Soru sor... (GSC Verisi veya Genel Konular)"):
        if not gsc_property:
            st.error("Lütfen önce marka seçin.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)

            with st.spinner("Düşünüyor..."):
                new_dates = extract_date_range_from_prompt(prompt)
                if new_dates:
                    start_date, end_date = new_dates
                    st.session_state.active_date_range = (start_date, end_date)
                    date_info_msg = f"📅 Analiz Dönemi: **{start_date} / {end_date}**"
                else:
                    start_date, end_date = st.session_state.active_date_range
                    date_info_msg = None

                current_key = f"{gsc_property}|{start_date}|{end_date}"
                last_key = st.session_state.get("last_fetched_key", "")

                if current_key != last_key or st.session_state.gsc_dataframe is None:
                    df_gsc = get_gsc_raw_data(gsc_property, start_date, end_date)
                    if df_gsc is not None and not df_gsc.empty:
                        st.session_state.gsc_dataframe = df_gsc
                        st.session_state.last_fetched_key = current_key
                        if date_info_msg:
                             st.session_state.messages.append({"role": "assistant", "content": date_info_msg})
                             with st.chat_message("assistant"): st.info(date_info_msg)
                    else:
                        st.error("Veri bulunamadı.")
                        st.stop()

                if st.session_state.gsc_dataframe is not None:
                    df = st.session_state.gsc_dataframe
                    summary_stats = f"Dönem: {start_date} - {end_date} | Toplam Tık: {df['Clicks'].sum()} | Ort. Poz: {df['Position'].mean():.1f}"
                    top_queries = df.nlargest(60, 'Clicks')[['Query', 'Clicks', 'Impressions', 'Position']].to_markdown(index=False)
                    losers = df.sort_values(by='Position', ascending=False).head(10)[['Query', 'Position']].to_markdown(index=False)
                    
                    chat_history_text = ""
                    for m in st.session_state.messages[-4:]: 
                        role_name = "Kullanıcı" if m['role'] == 'user' else "AI"
                        chat_history_text += f"{role_name}: {m['content']}\n"

                    # --- HYBRID SYSTEM PROMPT ---
                    ai_prompt = f"""
                    Sen gelişmiş bir Yapay Zeka Asistanısın. Şu anda bir SEO analiz aracının içindesin.
                    
                    ELİNDEKİ VERİ SETİ (GSC):
                    {summary_stats}
                    EN İYİ KELİMELER:
                    {top_queries}
                    DÜŞÜK PERFORMANSLILAR:
                    {losers}
                    
                    GÖREVİN: Kullanıcının sorusuna göre MODUNU SEÇ:
                    
                    MOD 1: VERİ ODAKLI SORU (GSC, SEO, Trafik)
                    Eğer soru yukarıdaki veri setiyle ilgiliyse:
                    - Bir SEO Stratejisti gibi davran.
                    - Eğer soru basitse (Örn: "Kaç tıklama?") -> Kısa cevap ver.
                    - Eğer soru analiz istiyorsa (Örn: "Neden düştük?") -> Analiz, İçgörü, Aksiyon formatını kullan.
                    
                    MOD 2: GENEL SORU (Kodlama, Genel Kültür, Metin Yazarlığı)
                    Eğer soru elindeki verilerle alakasızsa (Örn: "Python nedir?", "Bana şiir yaz", "Canonical nedir?"):
                    - Veri setini görmezden gel.
                    - Standart bir Gemini asistanı gibi, kendi genel bilginle cevap ver.
                    - ASLA "Veri setimde bu bilgi yok" diyerek reddetme.
                    
                    SOHBET GEÇMİŞİ:
                    {chat_history_text}
                    SORU: {prompt}
                    """
                    
                    res = generate_safe(ai_prompt) 
                    if res:
                        st.session_state.messages.append({"role": "assistant", "content": res.text})
                        with st.chat_message("assistant"): st.markdown(res.text)

