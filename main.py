import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import altair as alt

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO AI", layout="wide", page_icon="🅱️")

# --- CSS VE TASARIM ---
st.markdown("""
    <style>
    .main > div {padding-top: 2rem;}
    .stChatInput {position: fixed; bottom: 3rem;}
    .block-container {padding-bottom: 5rem;}
    h1 {color: #d32f2f;}
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 10px;
        border: 1px solid #e0e0e0;
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
    st.error(f"Secret Hatası: {e}. Lütfen .streamlit/secrets.toml dosyasını kontrol edin.")
    st.stop()

# AI Model
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# --- YARDIMCI FONKSİYONLAR ---

def classify_intent(keyword):
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
    GÖREV: Tarih aralığını çıkar.
    ÇIKTI FORMATI: "YYYY-MM-DD|YYYY-MM-DD"
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
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    payload = [{
        "keywords": [keyword], 
        "location_code": loc, 
        "language_code": lang, 
        "limit": 700, 
        "include_seed_keyword": True,
        "include_serp_info": False 
    }]
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()
        if response.status_code == 200 and res.get('tasks') and res['tasks'][0]['result']:
            items = res['tasks'][0]['result'][0]['items']
            data = []
            for i in items:
                kw_info = i.get('keyword_info', {})
                kd = i.get('keyword_properties', {}).get('keyword_difficulty', kw_info.get('competition_index', 0))
                data.append({
                    "Keyword": i['keyword'],
                    "Volume": kw_info.get('search_volume', 0),
                    "CPC": kw_info.get('cpc', 0),
                    "KD %": kd, 
                    "Competition": kw_info.get('competition_level', 'Unknown')
                })
            df = pd.DataFrame(data)
            if not df.empty:
                df['Intent'] = df['Keyword'].apply(classify_intent)
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"API Hatası: {e}")
        return None

# --- SIDEBAR ---
with st.sidebar:
    st.title("🅱️ PlanB SEO Tools")
    st.markdown("---")
    app_mode = st.radio("Mod Seçimi", ["🔍 Keyword Research (Pro)", "🤖 GSC AI Chatbot"])
    st.markdown("---")
    st.caption("In-House Tool v2.2")

# ======================================================
# MOD 1: KEYWORD RESEARCH (PRO) - GÜNCELLENMİŞ
# ======================================================
if app_mode == "🔍 Keyword Research (Pro)":
    st.title("🔍 Keyword Magic Tool")
    st.markdown("Semrush/Ahrefs benzeri veri analizi ve içerik stratejisi.")
    
    # Session State
    if "df_search_results" not in st.session_state:
        st.session_state.df_search_results = None
    if "analyzed_keyword" not in st.session_state:
        st.session_state.analyzed_keyword = ""

    # Üst Girdiler
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        keyword_input = st.text_input("Anahtar Kelime", placeholder="Örn: elektrikli süpürge")
    with col2:
        country_map = {"Türkiye": 2792, "ABD": 2840, "İngiltere": 2826}
        country = st.selectbox("Lokasyon", list(country_map.keys()))
    with col3:
        match_type = st.selectbox("Eşleme Türü", ["Geniş Eşleme (Broad)", "Tam Eşleme (Phrase)"])
    
    # --- YENİLENEN AYARLAR ALANI ---
    with st.expander("⚔️ Hedef Site & Rakip Analizi", expanded=True):
        st.caption("AI Stratejisi için aşağıdaki bilgileri doldurun:")
        target_website = st.text_input("Hedef Web Sitesi (Sizin Siteniz)", placeholder="https://markam.com")
        
        st.markdown("**Rakip Web Siteleri (Opsiyonel):**")
        rc1, rc2, rc3 = st.columns(3)
        comp1 = rc1.text_input("Rakip 1", placeholder="rakip1.com")
        comp2 = rc2.text_input("Rakip 2", placeholder="rakip2.com")
        comp3 = rc3.text_input("Rakip 3", placeholder="rakip3.com")
    
    # --- ANALİZ BUTONU ---
    if st.button("Analizi Başlat", type="primary"):
        if keyword_input:
            with st.spinner(f"'{keyword_input}' için veriler taranıyor..."):
                lang = "tr" if country == "Türkiye" else "en"
                raw_df = get_dfs_data(keyword_input, country_map[country], lang)
                
                if raw_df is not None and not raw_df.empty:
                    # Sadece Eşleme Türü Filtresi (Diğerleri kalktı)
                    if match_type == "Tam Eşleme (Phrase)":
                        raw_df = raw_df[raw_df['Keyword'].str.contains(keyword_input.lower())]
                    
                    # Sıralama
                    raw_df = raw_df.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                    
                    # Hafızaya Kaydet
                    st.session_state.df_search_results = raw_df
                    st.session_state.analyzed_keyword = keyword_input
                else:
                    st.error("Veri bulunamadı.")
        else:
            st.warning("Lütfen bir anahtar kelime girin.")

    # --- SONUÇLAR ---
    if st.session_state.df_search_results is not None and not st.session_state.df_search_results.empty:
        df = st.session_state.df_search_results
        
        st.divider()
        st.success(f"✅ '{st.session_state.analyzed_keyword}' analiz sonuçları:")
        
        # Metrikler
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Bulunan Kelime", len(df))
        m2.metric("Toplam Hacim", f"{df['Volume'].sum():,}")
        m3.metric("Ort. KD %", round(df['KD %'].mean(), 1))
        m4.metric("Potansiyel Trafik", f"{(df['Volume'].sum() * 0.45):,.0f}")
        
        # Grafik
        st.subheader("📊 Keyword Landscape")
        chart_data = df.head(50)
        scatter = alt.Chart(chart_data).mark_circle().encode(
            x=alt.X('KD %', title='Keyword Difficulty (Zorluk)'),
            y=alt.Y('Volume', title='Search Volume (Hacim)'),
            size=alt.Size('CPC', title='CPC', scale=alt.Scale(range=[50, 1000])),
            color=alt.Color('Intent', legend=alt.Legend(title="Niyet")),
            tooltip=['Keyword', 'Volume', 'KD %', 'CPC', 'Intent']
        ).properties(height=400).interactive()
        st.altair_chart(scatter, use_container_width=True)
        
        # Tablo
        st.subheader("📋 Kelime Listesi")
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
        
        # --- AI STRATEJİ (GÜNCELLENMİŞ) ---
        st.divider()
        st.subheader("🧠 Competitor-Aware AI Strategy")
        
        if st.button("🚀 Rakip Odaklı Strateji Oluştur"):
            # Rakipleri listeye çevir
            competitors_list = ", ".join([c for c in [comp1, comp2, comp3] if c])
            if not competitors_list:
                competitors_list = "Belirtilmedi (Genel pazar analizi yap)"

            top_keywords = df.head(20).to_csv(index=False)
            intent_dist = df['Intent'].value_counts().to_string()
            
            prompt = f"""
            Sen Kıdemli bir SEO Stratejistisin.
            
            ANALİZ BAĞLAMI:
            - Odak Konu: {st.session_state.analyzed_keyword}
            - Hedef Site: {target_website}
            - RAKİPLER: {competitors_list}
            
            PAZAR VERİSİ (Kelime Listesi):
            {top_keywords}
            
            GÖREV:
            Rakipleri ({competitors_list}) de göz önünde bulundurarak:
            1. 'Content Gap' analizi yap: Rakiplerin muhtemelen zayıf olduğu veya bizim öne geçebileceğimiz 3 fırsat konusu belirle.
            2. Bu kelimeler için nasıl bir içerik yapısı (Blog, Landing Page, Kategori) önerirsin?
            3. Rakiplerden farklılaşmak için içerikte neleri öne çıkarmalıyız? (Tone of voice, format vb.)
            """
            
            with st.spinner("Gemini rakipleri analiz ediyor ve strateji kurguluyor..."):
                try:
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"AI Hatası: {e}")

# ======================================================
# MOD 2: GSC AI CHATBOT
# ======================================================
elif app_mode == "🤖 GSC AI Chatbot":
    st.title("🤖 GSC AI Data Analyst")
    
    gsc_property = st.text_input("GSC Mülk URL'si", placeholder="sc-domain:markam.com")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_gsc_data_range" not in st.session_state:
        st.session_state.current_gsc_data_range = None
    if "gsc_dataframe" not in st.session_state:
        st.session_state.gsc_dataframe = None

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Soru sor..."):
        if not gsc_property:
            st.error("Lütfen önce GSC Mülk adresini girin.")
        else:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("Analiz yapılıyor..."):
                start_date, end_date = extract_date_range_from_prompt(prompt)
                current_range = f"{start_date}|{end_date}"
                
                if st.session_state.current_gsc_data_range != current_range:
                    df_gsc = get_gsc_raw_data(gsc_property, start_date, end_date)
                    if df_gsc is not None and not df_gsc.empty:
                        st.session_state.gsc_dataframe = df_gsc
                        st.session_state.current_gsc_data_range = current_range
                        msg = f"📅 **{start_date}** - **{end_date}** verisi yüklendi."
                        st.session_state.messages.append({"role": "assistant", "content": msg})
                        st.markdown(f"*{msg}*")
                    else:
                        st.error("Veri yok.")
                        st.stop()
                
                if st.session_state.gsc_dataframe is not None:
                    df = st.session_state.gsc_dataframe
                    total_clicks = df['Clicks'].sum()
                    top_queries = df.nlargest(30, 'Clicks')[['Query', 'Clicks', 'Position']].to_markdown()
                    top_pages = df.groupby('Page')['Clicks'].sum().nlargest(10).to_markdown()
                    
                    ai_ctx = f"Dönem: {start_date}-{end_date}. Toplam Tık: {total_clicks}\nKelimeler:\n{top_queries}\nSayfalar:\n{top_pages}"
                    full_prompt = f"Sen SEO uzmanısın. Veri:\n{ai_ctx}\nSoru: {prompt}"
                    
                    try:
                        res = model.generate_content(full_prompt)
                        st.session_state.messages.append({"role": "assistant", "content": res.text})
                        with st.chat_message("assistant"):
                            st.markdown(res.text)
                    except Exception as e:
                        st.error(f"Hata: {e}")
