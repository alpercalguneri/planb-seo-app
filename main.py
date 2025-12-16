import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
from dateutil.relativedelta import relativedelta # Tarih hesaplama için

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
model = genai.GenerativeModel('gemini-2.5-flash') # Hız ve mantık için 1.5 Flash ideal

# --- FONKSİYONLAR ---

def extract_date_range_from_prompt(user_prompt):
    """
    Kullanıcının doğal dille yazdığı (örn: 'Geçen ay', 'Son 3 ay') ifadeyi
    YYYY-MM-DD formatında başlangıç ve bitiş tarihine çevirir.
    """
    today = datetime.date.today()
    
    prompt = f"""
    Bugünün tarihi: {today}
    Kullanıcı Girdisi: "{user_prompt}"
    
    GÖREV: Kullanıcının cümlesinden analiz etmek istediği TARİH ARALIĞINI çıkar.
    
    KURALLAR:
    1. Eğer kullanıcı belirli bir tarih belirtmişse (örn: "Ekim 2023", "Geçen hafta") o tarihleri hesapla.
    2. Eğer kullanıcı tarih belirtmemişse (örn: "En çok tıklanan kelimelerim ne?"), varsayılan olarak SON 28 GÜNÜ al.
    3. Çıktı formatı SADECE şu olmalı: "YYYY-MM-DD|YYYY-MM-DD" (Başlangıç|Bitiş).
    4. Başka hiçbir metin yazma.
    """
    
    try:
        response = model.generate_content(prompt)
        dates = response.text.strip().split('|')
        if len(dates) == 2:
            return dates[0], dates[1]
    except:
        pass
    
    # Hata olursa veya tarih yoksa son 28 günü döndür (Fallback)
    start = today - datetime.timedelta(days=28)
    return str(start), str(today)

def get_gsc_raw_data(site_url, start_date, end_date):
    """Chatbot için belirli tarih aralığında GSC verisini çeker."""
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
        return pd.DataFrame() # Boş veri
    except Exception as e:
        return None # Hata durumu

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
    try:
        st.image("logo.png", width=120) 
    except:
        st.write("🅱️")
        
    st.title("PlanB AI Tools")
    app_mode = st.radio("Mod Seçiniz", ["🔍 Keyword Research Agent", "🤖 GSC AI Chatbot"])
    st.divider()
    st.caption("v13.0 - Intelligent Date Selection")

# ======================================================
# MOD 1: KEYWORD RESEARCH AGENT (SADELEŞTİRİLMİŞ)
# ======================================================
if app_mode == "🔍 Keyword Research Agent":
    st.title("🔍 Keyword Research & Content Gap")
    
    col1, col2 = st.columns(2)
    with col1:
        keyword_input = st.text_input("Anahtar Kelime", placeholder="Örn: takım elbise")
        target_website = st.text_input("Hedef Web Sitesi", placeholder="https://markam.com")
    with col2:
        country_map = {"Türkiye": 2792, "ABD": 2840}
        country = st.selectbox("Pazar / Ülke", list(country_map.keys()))
    
    with st.expander("⚔️ Rakip Markalar", expanded=True):
        c1, c2, c3 = st.columns(3)
        comp1 = c1.text_input("Rakip 1")
        comp2 = c2.text_input("Rakip 2")
        comp3 = c3.text_input("Rakip 3")
        
    btn_analyze = st.button("Analizi Başlat", type="primary")
    
    if btn_analyze and keyword_input:
        with st.spinner("Pazar verileri taranıyor..."):
            raw_df = get_dfs_data(keyword_input, country_map[country], "tr" if country=="Türkiye" else "en")
            
            if raw_df is not None and not raw_df.empty:
                df_filtered = strict_filter(raw_df, keyword_input)
                df_filtered = df_filtered.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                
                if not df_filtered.empty:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Toplam Kelime", len(df_filtered))
                    m2.metric("Toplam Hacim", f"{df_filtered['Volume'].sum():,}")
                    m3.metric("En Popüler", df_filtered.iloc[0]['Keyword'])
                    
                    st.dataframe(df_filtered, use_container_width=True)
                    
                    st.divider()
                    st.subheader("🧠 Content Gap & Strateji")
                    
                    competitors = ", ".join([c for c in [comp1, comp2, comp3] if c])
                    top_kw_list = ", ".join(df_filtered.head(10)['Keyword'].tolist())
                    
                    prompt = f"""
                    Sen Kıdemli bir SEO Stratejistisin.
                    Site: {target_website} | Rakipler: {competitors} | Konu: {keyword_input}
                    Kelimeler: {top_kw_list}
                    
                    Rakiplerin muhtemelen domine ettiği ama bizim eksik kaldığımız 3 adet 'Killer' İçerik Fikri öner.
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
# MOD 2: GSC AI CHATBOT (AKILLI TARİH SEÇİMİ)
# ======================================================
elif app_mode == "🤖 GSC AI Chatbot":
    st.title("🤖 GSC AI Data Analyst")
    st.caption("Veri aralığını kendi belirleyen akıllı asistan.")
    
    # URL GİRİŞİ (SABİT)
    gsc_property = st.text_input("GSC Mülk URL'si", placeholder="sc-domain:markam.com veya https://markam.com/")
    
    # Session State (Geçmiş ve Veri)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_gsc_data_range" not in st.session_state:
        st.session_state.current_gsc_data_range = None # Hangi tarih aralığı yüklü?
    if "gsc_dataframe" not in st.session_state:
        st.session_state.gsc_dataframe = None

    # Mesaj Geçmişini Göster
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # KULLANICI GİRDİSİ VE OTOMATİK İŞLEM
    if prompt := st.chat_input("Örn: Geçen ay en çok düşen sayfalarım hangileri?"):
        
        if not gsc_property:
            st.error("Lütfen önce yukarıya GSC Mülk adresini girin.")
        else:
            # 1. Kullanıcı Mesajını Göster
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # 2. Tarih Niyetini Anla
            with st.spinner("Tarih aralığı belirleniyor ve veri çekiliyor..."):
                start_date, end_date = extract_date_range_from_prompt(prompt)
                current_range = f"{start_date}|{end_date}"
                
                # Eğer yeni bir tarih aralığı istendiyse veya hiç veri yoksa API'yi çağır
                if st.session_state.current_gsc_data_range != current_range:
                    
                    df_gsc = get_gsc_raw_data(gsc_property, start_date, end_date)
                    
                    if df_gsc is not None and not df_gsc.empty:
                        st.session_state.gsc_dataframe = df_gsc
                        st.session_state.current_gsc_data_range = current_range
                        
                        # Kullanıcıya bilgi ver (Sistem mesajı olarak)
                        system_msg = f"📅 **{start_date}** ile **{end_date}** arasındaki veriler çekildi. Analiz yapılıyor..."
                        st.session_state.messages.append({"role": "assistant", "content": system_msg})
                        with st.chat_message("assistant"):
                            st.markdown(system_msg)
                    else:
                        st.error("Belirtilen tarihler için GSC verisi bulunamadı veya yetki hatası.")
                        st.stop()
                
                # 3. Analiz Yap (Hafızadaki veri ile)
                if st.session_state.gsc_dataframe is not None:
                    df = st.session_state.gsc_dataframe
                    
                    # Veri Özeti (AI'a beslemek için)
                    total_clicks = df['Clicks'].sum()
                    top_queries = df.groupby("Query")[['Clicks', 'Impressions', 'Position']].sum().sort_values("Clicks", ascending=False).head(40).to_markdown()
                    top_pages = df.groupby("Page")[['Clicks', 'Impressions']].sum().sort_values("Clicks", ascending=False).head(15).to_markdown()
                    
                    ai_context = f"""
                    ANALİZ DÖNEMİ: {start_date} - {end_date}
                    TOPLAM TIKLAMA: {total_clicks}
                    EN İYİ KELİMELER:
                    {top_queries}
                    EN İYİ SAYFALAR:
                    {top_pages}
                    """
                    
                    full_prompt = f"""
                    Sen Profesyonel bir SEO Analistisin.
                    
                    VERİ SETİ:
                    {ai_context}
                    
                    KULLANICI SORUSU:
                    "{prompt}"
                    
                    GÖREV:
                    Bu verilere dayanarak kullanıcının sorusunu yanıtla. 
                    - Kesinlikle tarih aralığından bahset.
                    - Sayısal veriler kullan.
                    - Eğer düşüş veya fırsat soruluyorsa yorum yap.
                    """
                    
                    try:
                        response = model.generate_content(full_prompt)
                        ai_reply = response.text
                        st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                        with st.chat_message("assistant"):
                            st.markdown(ai_reply)
                    except Exception as e:
                        st.error(f"AI Analiz Hatası: {e}")

