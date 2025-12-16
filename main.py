import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO AI", layout="wide", page_icon="🅱️")

# --- CSS VE TASARIM ---
st.markdown("""
    <style>
    .main > div {padding-top: 2rem;}
    .stChatInput {position: fixed; bottom: 3rem;}
    .block-container {padding-bottom: 5rem;}
    h1 {color: #d32f2f;}
    </style>
    """, unsafe_allow_html=True)

# --- API BİLGİLERİ ---
try:
    # 1. Google Gemini
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    # 2. DataForSEO
    DFS_LOGIN = st.secrets["DFS_LOGIN"]
    DFS_PASSWORD = st.secrets["DFS_PASSWORD"]
    # 3. GSC Credentials
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
model = genai.GenerativeModel('gemini-2.5-flash')

# --- FONKSİYONLAR ---

def get_gsc_raw_data(site_url, days=30):
    """Chatbot için ham GSC verisini çeker."""
    try:
        creds = service_account.Credentials.from_service_account_info(
            GSC_CREDENTIALS, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        service = build('searchconsole', 'v1', credentials=creds)
        
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)
        
        request = {
            'startDate': start_date.isoformat(),
            'endDate': end_date.isoformat(),
            'dimensions': ['query', 'page'], 
            'rowLimit': 1000  # AI'a beslemek için en önemli 1000 satır
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
                    "CTR": f"%{round(row['ctr'] * 100, 2)}",
                    "Position": round(row['position'], 1)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"GSC Erişim Hatası: {e}")
        return None

def get_dfs_data(keyword, loc, lang):
    """DataForSEO API'den veri çeker."""
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
                    "Competition": kw_info.get('competition_level', 0)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except:
        return None

def strict_filter(df, seed_keyword):
    """Alakasız kelimeleri eler."""
    if df.empty: return df
    return df[df['Keyword'].str.contains(seed_keyword.lower(), na=False)]

# --- ANA UYGULAMA YAPISI ---

# Sol Menü Navigasyon
with st.sidebar:
    st.image("logo.png", width=120) # Logo varsa gösterir
    st.title("PlanB AI Tools")
    
    app_mode = st.radio("Mod Seçiniz", ["🔍 Keyword Research Agent", "🤖 GSC AI Chatbot"])
    
    st.divider()
    st.caption("v12.0 - PlanB Media")

# ======================================================
# MOD 1: KEYWORD RESEARCH AGENT
# ======================================================
if app_mode == "🔍 Keyword Research Agent":
    st.title("🔍 Keyword Research & Content Gap")
    st.caption("DataForSEO verileri ile pazar araştırması ve rekabet analizi.")
    
    # Girdiler (Sadeleştirilmiş)
    col1, col2 = st.columns(2)
    with col1:
        keyword_input = st.text_input("Anahtar Kelime", placeholder="Örn: takım elbise")
        target_website = st.text_input("Hedef Web Sitesi", placeholder="https://markam.com")
    with col2:
        country_map = {"Türkiye": 2792, "ABD": 2840}
        country = st.selectbox("Pazar / Ülke", list(country_map.keys()))
    
    with st.expander("⚔️ Rakip Markalar (Content Gap İçin)", expanded=True):
        c1, c2, c3 = st.columns(3)
        comp1 = c1.text_input("Rakip 1", placeholder="Rakip A")
        comp2 = c2.text_input("Rakip 2", placeholder="Rakip B")
        comp3 = c3.text_input("Rakip 3", placeholder="Rakip C")
        
    btn_analyze = st.button("Analizi Başlat", type="primary")
    
    if btn_analyze and keyword_input:
        with st.spinner("Pazar verileri taranıyor..."):
            # 1. Veri Çekme
            raw_df = get_dfs_data(keyword_input, country_map[country], "tr" if country=="Türkiye" else "en")
            
            if raw_df is not None and not raw_df.empty:
                # 2. Filtreleme
                df_filtered = strict_filter(raw_df, keyword_input)
                df_filtered = df_filtered.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                
                if not df_filtered.empty:
                    # Metrikler
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Toplam Kelime", len(df_filtered))
                    m2.metric("Toplam Hacim", f"{df_filtered['Volume'].sum():,}")
                    m3.metric("En Popüler", df_filtered.iloc[0]['Keyword'])
                    
                    st.divider()
                    
                    # Tablo
                    st.subheader("📋 Kelime Listesi")
                    st.dataframe(
                        df_filtered, 
                        use_container_width=True,
                        column_config={
                            "Volume": st.column_config.NumberColumn("Hacim", format="%d"),
                            "CPC": st.column_config.NumberColumn("CPC", format="$%.2f")
                        }
                    )
                    
                    # AI Strateji (Content Gap)
                    st.divider()
                    st.subheader("🧠 Content Gap & Strateji")
                    
                    competitors = ", ".join([c for c in [comp1, comp2, comp3] if c])
                    top_kw_list = ", ".join(df_filtered.head(10)['Keyword'].tolist())
                    
                    prompt = f"""
                    Sen Kıdemli bir SEO Stratejistisin.
                    
                    DURUM:
                    - Markamızın Sitesi: {target_website}
                    - Rakiplerimiz: {competitors if competitors else "Belirtilmedi"}
                    - Odak Konu: {keyword_input}
                    - Pazardaki En Hacimli Kelimeler: {top_kw_list}
                    
                    GÖREV:
                    Rakiplerin muhtemelen domine ettiği ama bizim henüz tam kapsamadığımızı düşündüğün
                    3 adet 'Killer' İçerik Fikri öner. Her öneri için nedenini açıkla.
                    """
                    
                    try:
                        with st.spinner("Yapay zeka stratejiyi oluşturuyor..."):
                            response = model.generate_content(prompt)
                            st.markdown(response.text)
                    except:
                        st.warning("AI şu an meşgul.")
                else:
                    st.warning("Strict filtre sonrası veri kalmadı.")
            else:
                st.warning("Veri bulunamadı.")

# ======================================================
# MOD 2: GSC AI CHATBOT
# ======================================================
elif app_mode == "🤖 GSC AI Chatbot":
    st.title("🤖 GSC AI Data Analyst")
    st.caption("Google Search Console verilerinizle sohbet edin.")
    
    # 1. BAĞLANTI ALANI
    with st.container():
        col_input, col_btn = st.columns([4, 1])
        with col_input:
            gsc_property = st.text_input("GSC Mülk URL'si", placeholder="https://markam.com veya sc-domain:markam.com")
        with col_btn:
            # Buton hizalaması için boşluk
            st.write("") 
            st.write("")
            load_btn = st.button("Veriyi Yükle", type="primary")

    # Session State Başlatma (Chat Geçmişi ve Veri Contexti)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "gsc_context_data" not in st.session_state:
        st.session_state.gsc_context_data = None
    
    # Veri Yükleme İşlemi
    if load_btn and gsc_property:
        with st.spinner("Son 30 günlük GSC verileri çekiliyor ve AI için işleniyor..."):
            df_gsc = get_gsc_raw_data(gsc_property, days=30)
            
            if df_gsc is not None and not df_gsc.empty:
                # Veriyi özetle (AI'a hepsini gönderemeyiz, en önemli kısımları alıyoruz)
                # En çok tıklanan 50 kelime
                top_queries = df_gsc.groupby("Query")[['Clicks', 'Impressions', 'Position']].sum().sort_values("Clicks", ascending=False).head(50).to_markdown()
                # En çok tıklanan 20 sayfa
                top_pages = df_gsc.groupby("Page")[['Clicks', 'Impressions']].sum().sort_values("Clicks", ascending=False).head(20).to_markdown()
                # Genel metrikler
                total_clicks = df_gsc['Clicks'].sum()
                
                # Context oluştur
                st.session_state.gsc_context_data = f"""
                ANALİZ EDİLEN MÜLK: {gsc_property}
                TOPLAM TIKLAMA (Son 30 Gün): {total_clicks}
                
                EN ÇOK TRAFİK GETİREN KELİMELER (ÖZET):
                {top_queries}
                
                EN ÇOK TRAFİK ALAN SAYFALAR (ÖZET):
                {top_pages}
                """
                
                st.success(f"✅ Veri yüklendi! Toplam {len(df_gsc)} satır veri analiz edildi. Şimdi sorunuzu sorabilirsiniz.")
                # Mesaj geçmişini temizle (yeni mülk yüklendiği için)
                st.session_state.messages = []
            else:
                st.error("Veri çekilemedi. Yetki veya URL hatası olabilir.")

    # 2. CHAT ALANI
    # Geçmiş mesajları göster
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Kullanıcı Girdisi
    if prompt := st.chat_input("GSC verileriniz hakkında bir soru sorun... (Örn: En çok tıklanan kelimem hangisi?)"):
        
        # Veri yüklü mü kontrolü
        if not st.session_state.gsc_context_data:
            st.error("Lütfen önce yukarıdan bir mülk girip 'Veriyi Yükle' butonuna basın.")
        else:
            # Kullanıcı mesajını ekle
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # AI Cevabı
            with st.chat_message("assistant"):
                with st.spinner("Veriler analiz ediliyor..."):
                    
                    full_prompt = f"""
                    Sen uzman bir SEO Veri Analistisin. Aşağıdaki Google Search Console verilerini incele ve kullanıcının sorusunu yanıtla.
                    
                    VERİ SETİ:
                    {st.session_state.gsc_context_data}
                    
                    KULLANICI SORUSU:
                    {prompt}
                    
                    Yanıt verirken sayısal verilere atıfta bulun ve stratejik öneriler ekle.
                    """
                    
                    try:
                        response = model.generate_content(full_prompt)
                        ai_reply = response.text
                        st.markdown(ai_reply)
                        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                    except Exception as e:
                        st.error(f"AI Hatası: {e}")
