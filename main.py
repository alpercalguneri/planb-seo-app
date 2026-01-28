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
    .stChatInput {position: fixed; bottom: 3rem; z-index: 100;}
    .block-container {padding-bottom: 7rem;}
    h1 {color: #d32f2f;}
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 10px;
        border: 1px solid #e0e0e0;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# --- API BİLGİLERİ VE KURULUM ---
# Hata yönetimi ile secrets kontrolü
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

# AI Model Konfigürasyonu
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # Güncel ve hızlı model

# --- YARDIMCI FONKSİYONLAR ---

def classify_intent(keyword):
    """Kelime niyetini basit kurallarla sınıflandırır."""
    k = keyword.lower()
    if any(x in k for x in ['satın al', 'fiyat', 'ucuz', 'sipariş', 'kiralık', 'buy', 'price']):
        return "Transactional (İşlem)"
    elif any(x in k for x in ['en iyi', 'karşılaştırma', 'yorum', 'inceleme', 'vs', 'best', 'review']):
        return "Commercial (Ticari)"
    elif any(x in k for x in ['nedir', 'nasıl', 'ne demek', 'kimdir', 'tarifi', 'rehberi', 'what is', 'how to']):
        return "Informational (Bilgi)"
    else:
        return "Navigational/General"

@st.cache_data(ttl=3600, show_spinner=False)
def extract_date_range_from_prompt(user_prompt):
    """Kullanıcı girdisinden tarih aralığını AI ile çıkarır."""
    today = datetime.date.today()
    prompt = f"""
    Bugünün tarihi: {today}
    Kullanıcı Girdisi: "{user_prompt}"
    GÖREV: Tarih aralığını çıkar. Eğer kullanıcı spesifik tarih vermediyse 'son 28 gün' varsay.
    ÇIKTI FORMATI: Sadece "YYYY-MM-DD|YYYY-MM-DD" döndür. Başka metin yazma.
    """
    try:
        response = model.generate_content(prompt)
        dates = response.text.strip().split('|')
        if len(dates) == 2:
            return dates[0].strip(), dates[1].strip()
    except:
        pass
    
    # Fallback (Hata durumunda son 28 gün)
    start = today - datetime.timedelta(days=28)
    return str(start), str(today)

@st.cache_data(ttl=3600) # 1 Saatlik Önbellekleme
def get_gsc_raw_data(site_url, start_date, end_date):
    """Google Search Console verilerini çeker."""
    try:
        creds = service_account.Credentials.from_service_account_info(
            GSC_CREDENTIALS, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        service = build('searchconsole', 'v1', credentials=creds)
        request = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['query', 'page'], 
            'rowLimit': 2000 # Limit artırıldı
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
        # Hata detayını return etmiyoruz, UI tarafında handle edilecek
        print(f"GSC Error: {e}")
        return None

@st.cache_data(ttl=86400) # 24 Saatlik Önbellekleme (Veri sık değişmez)
def get_dfs_data(keyword, loc, lang):
    """DataForSEO API'den kelime verilerini çeker."""
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
        
        if response.status_code == 200:
            if res.get('tasks') and res['tasks'][0]['result']:
                items = res['tasks'][0]['result'][0]['items']
                data = []
                for i in items:
                    kw_info = i.get('keyword_info', {})
                    if kw_info is None: continue # Nadir durum kontrolü
                    
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
            else:
                return pd.DataFrame() # Sonuç yoksa boş DF
        else:
            return None # API hatası
    except Exception as e:
        st.error(f"API Bağlantı Hatası: {e}")
        return None

# --- SIDEBAR ---
with st.sidebar:
    st.title("🅱️ PlanB SEO Tools")
    st.markdown("---")
    app_mode = st.radio("Mod Seçimi", ["🔍 Keyword Research (Pro)", "🤖 GSC AI Chatbot"])
    st.markdown("---")
    st.info("💡 **İpucu:** GSC Modu için chat kısmına 'Geçen hafta en çok düşen kelimeler neler?' gibi sorular sorabilirsiniz.")
    st.caption("In-House Tool v2.4")

# ======================================================
# MOD 1: KEYWORD RESEARCH (PRO)
# ======================================================
if app_mode == "🔍 Keyword Research (Pro)":
    st.title("🔍 Keyword Magic Tool")
    
    # Session State Initialization
    if "df_search_results" not in st.session_state:
        st.session_state.df_search_results = None
    if "analyzed_keyword" not in st.session_state:
        st.session_state.analyzed_keyword = ""

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        keyword_input = st.text_input("Anahtar Kelime", placeholder="Örn: elektrikli süpürge")
    with col2:
        country_map = {"Türkiye": 2792, "ABD": 2840, "İngiltere": 2826}
        country = st.selectbox("Lokasyon", list(country_map.keys()))
    with col3:
        match_type = st.selectbox("Eşleme Türü", ["Geniş Eşleme (Broad)", "Tam Eşleme (Phrase)"])
    
    with st.expander("⚔️ Hedef Site & Rakip Analizi", expanded=True):
        st.caption("Strateji önerisi için doldurunuz:")
        target_website = st.text_input("Hedef Web Sitesi", placeholder="https://markam.com")
        
        rc1, rc2, rc3 = st.columns(3)
        comp1 = rc1.text_input("Rakip 1", placeholder="rakip1.com")
        comp2 = rc2.text_input("Rakip 2", placeholder="rakip2.com")
        comp3 = rc3.text_input("Rakip 3", placeholder="rakip3.com")
    
    # --- ANALİZ BUTONU ---
    if st.button("Analizi Başlat", type="primary"):
        if keyword_input:
            with st.spinner(f"'{keyword_input}' taranıyor..."):
                lang = "tr" if country == "Türkiye" else "en"
                # Cacheli fonksiyon çağrısı
                raw_df = get_dfs_data(keyword_input, country_map[country], lang)
                
                if raw_df is not None and not raw_df.empty:
                    if match_type == "Tam Eşleme (Phrase)":
                        raw_df = raw_df[raw_df['Keyword'].str.contains(keyword_input.lower())]
                    
                    raw_df = raw_df.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                    st.session_state.df_search_results = raw_df
                    st.session_state.analyzed_keyword = keyword_input
                    st.rerun() # Veri geldiğinde sayfayı yenile
                elif raw_df is None:
                    st.error("API yanıt vermedi. Lütfen tekrar deneyin.")
                else:
                    st.warning("Bu kelime için veri bulunamadı.")
        else:
            st.warning("Lütfen bir anahtar kelime girin.")

    # --- SONUÇLAR ---
    if st.session_state.df_search_results is not None and not st.session_state.df_search_results.empty:
        df = st.session_state.df_search_results
        
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Kelime Sayısı", len(df))
        m2.metric("Toplam Hacim", f"{df['Volume'].sum():,}")
        m3.metric("Ort. KD %", round(df['KD %'].mean(), 1))
        # Potansiyel trafik tahmini: Toplam hacim * ortalama CTR (0.3 varsayım)
        m4.metric("Potansiyel Trafik", f"{(df['Volume'].sum() * 0.3):,.0f}")
        
        # Grafik
        chart_data = df.head(100) # Performans için limit
        scatter = alt.Chart(chart_data).mark_circle().encode(
            x=alt.X('KD %', title='Keyword Difficulty'),
            y=alt.Y('Volume', title='Search Volume'),
            size='CPC',
            color=alt.Color('Intent', scale=alt.Scale(scheme='category10')),
            tooltip=['Keyword', 'Volume', 'KD %', 'CPC', 'Intent']
        ).properties(height=400, title="Keyword Landscape").interactive()
        
        st.altair_chart(scatter, use_container_width=True)
        
        # Tablo
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
        
        # --- AI STRATEJİ ALANI ---
        st.divider()
        st.subheader("💡 AI Content Strategy")
        
        if st.button("🚀 Fikirleri Getir"):
            competitors_list = ", ".join([c for c in [comp1, comp2, comp3] if c])
            if not competitors_list: competitors_list = "Belirtilmedi"

            top_keywords = df.head(25)[['Keyword', 'Volume', 'KD %']].to_csv(index=False)
            
            prompt = f"""
            Sen Kıdemli bir SEO Stratejistisin. Yanıtın çok kısa, net ve listelenmiş olmalı.
            
            BAĞLAM:
            - Ana Kelime: {st.session_state.analyzed_keyword}
            - Bizim Site: {target_website}
            - Rakipler: {competitors_list}
            
            KELİME VERİLERİ (Hacim ve Zorluk):
            {top_keywords}
            
            GÖREV:
            Bu verilere bakarak, trafiği artıracak ve rakiplerden pay alacak tam olarak 5 adet İçerik Fikri öner.
            Giriş, gelişme, sonuç metni YAZMA. Sadece aşağıdaki formatta 5 madde yaz.
            
            İSTENEN FORMAT:
            1. **[Önerilen H1 Başlığı]**
               👉 *Neden?*: [Hangi kelimeyi hedefliyor? Hangi rakip eksiğini kapatıyor? (Max 2 cümle)]
            """
            
            with st.spinner("Strateji oluşturuluyor..."):
                try:
                    response = model.generate_content(prompt)
                    st.success("Strateji Hazır!")
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"AI Hatası: {e}")

# ======================================================
# MOD 2: GSC AI CHATBOT
# ======================================================
elif app_mode == "🤖 GSC AI Chatbot":
    st.title("🤖 GSC AI Data Analyst")
    
    # Input area
    col_gsc1, col_gsc2 = st.columns([3, 1])
    with col_gsc1:
        gsc_property = st.text_input("GSC Mülk URL'si", placeholder="sc-domain:markam.com")
    with col_gsc2:
        if st.button("Sohbeti Temizle"):
            st.session_state.messages = []
            st.session_state.current_gsc_data_range = None
            st.rerun()
    
    if "messages" not in st.session_state: st.session_state.messages = []
    if "current_gsc_data_range" not in st.session_state: st.session_state.current_gsc_data_range = None
    if "gsc_dataframe" not in st.session_state: st.session_state.gsc_dataframe = None

    # Mesajları göster
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat Input
    if prompt := st.chat_input("Verilerinle ilgili soru sor... (Örn: Geçen ay en çok tıklanan sayfalarım hangileri?)"):
        if not gsc_property:
            st.error("Lütfen önce GSC Mülk adresini girin.")
        else:
            # Kullanıcı mesajını ekle
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)

            with st.spinner("Veriler analiz ediliyor..."):
                # Tarih aralığını belirle
                start_date, end_date = extract_date_range_from_prompt(prompt)
                current_range_key = f"{gsc_property}|{start_date}|{end_date}"
                
                # Veri daha önce çekilmediyse veya tarih değiştiyse çek
                if st.session_state.current_gsc_data_range != current_range_key:
                    df_gsc = get_gsc_raw_data(gsc_property, start_date, end_date)
                    
                    if df_gsc is not None and not df_gsc.empty:
                        st.session_state.gsc_dataframe = df_gsc
                        st.session_state.current_gsc_data_range = current_range_key
                        system_msg = f"✅ **{start_date}** ile **{end_date}** arasındaki veriler yüklendi. Analize başlıyorum."
                        st.session_state.messages.append({"role": "assistant", "content": system_msg})
                        with st.chat_message("assistant"): st.markdown(system_msg)
                    else:
                        err_msg = "❌ Belirtilen tarih veya mülk için veri bulunamadı. Yetkileri kontrol edin."
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
                        with st.chat_message("assistant"): st.error(err_msg)
                        st.stop()
                
                # AI Analizi
                if st.session_state.gsc_dataframe is not None:
                    df = st.session_state.gsc_dataframe
                    
                    # Token limitini aşmamak için veriyi özetleyerek gönderiyoruz
                    summary_stats = f"""
                    Toplam Tıklama: {df['Clicks'].sum()}
                    Toplam Gösterim: {df['Impressions'].sum()}
                    Ortalama CTR: {df['CTR'].mean():.2f}%
                    Ortalama Pozisyon: {df['Position'].mean():.1f}
                    """
                    
                    top_queries = df.nlargest(40, 'Clicks')[['Query', 'Clicks', 'Impressions', 'Position']].to_markdown(index=False)
                    top_pages = df.groupby('Page').sum(numeric_only=True).nlargest(20, 'Clicks')[['Clicks']].to_markdown()
                    
                    ai_ctx = f"""
                    SENARYO: Sen uzman bir SEO Analistisin. Aşağıdaki GSC verisine göre kullanıcının sorusunu yanıtla.
                    DÖNEM: {start_date} - {end_date}
                    
                    GENEL İSTATİSTİKLER:
                    {summary_stats}
                    
                    EN ÇOK TIKLANAN KELİMELER:
                    {top_queries}
                    
                    EN ÇOK TIKLANAN SAYFALAR (Özet):
                    {top_pages}
                    
                    SORU: {prompt}
                    """
                    
                    try:
                        res = model.generate_content(ai_ctx)
                        st.session_state.messages.append({"role": "assistant", "content": res.text})
                        with st.chat_message("assistant"): st.markdown(res.text)
                    except Exception as e:
                        st.error(f"AI Yanıt Üretme Hatası: {e}")







