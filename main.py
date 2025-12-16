import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO Agent", layout="wide", page_icon="🅱️")

# --- CSS ---
st.markdown("""
    <style>
    .main > div {padding-top: 1rem;}
    h1 {color: #d32f2f;}
    .stMetric {background-color: #f8f9fa; border:1px solid #dee2e6; border-radius:5px; padding:10px;}
    </style>
    """, unsafe_allow_html=True)

# --- API BİLGİLERİ ---
try:
    # Google AI
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    # DataForSEO
    DFS_LOGIN = st.secrets["DFS_LOGIN"]
    DFS_PASSWORD = st.secrets["DFS_PASSWORD"]
    # GSC Credentials (JSON içeriği)
    GSC_CREDENTIALS = {
        "type": "service_account",
        "project_id": st.secrets["GSC_PROJECT_ID"],
        "private_key_id": "optional", # Gerekli değil
        "private_key": st.secrets["GSC_PRIVATE_KEY"].replace('\\n', '\n'), # Newline düzeltmesi
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

genai.configure(api_key=GOOGLE_API_KEY)
# Kullanıcı isteği üzerine 2.5-flash kullanıyoruz
model = genai.GenerativeModel('gemini-2.5-flash')

# --- SESSION STATE ---
if 'brands' not in st.session_state:
    st.session_state.brands = {} 
if 'active_brand' not in st.session_state:
    st.session_state.active_brand = "Genel"
    st.session_state.brands["Genel"] = {"context": "", "competitors": ["", "", ""], "gsc_url": ""}

# --- FONKSİYONLAR: GSC ---

def get_gsc_data(site_url, days=30):
    """Google Search Console API'den veri çeker."""
    try:
        # Yetkilendirme
        creds = service_account.Credentials.from_service_account_info(
            GSC_CREDENTIALS, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
        )
        service = build('searchconsole', 'v1', credentials=creds)
        
        # Tarih Aralığı
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)
        
        # API İsteği
        request = {
            'startDate': start_date.isoformat(),
            'endDate': end_date.isoformat(),
            'dimensions': ['query', 'page'], # Hem kelime hem sayfa bazlı
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
        else:
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"GSC Hatası: {e}. Lütfen GSC ayarlarından '{GSC_CREDENTIALS['client_email']}' adresine yetki verdiğinizden emin olun.")
        return None

# --- FONKSİYONLAR: DATAFORSEO ---

def get_dataforseo_data(keyword, loc, lang):
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
                    "Competition": round(kw_info.get('competition_level', 0) * 100)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except:
        return None

def strict_filter(df, seed_keyword):
    if df.empty: return df
    return df[df['Keyword'].str.contains(seed_keyword.lower(), na=False)]

# --- SIDEBAR ---
with st.sidebar:
    st.header("🏢 Marka & Veri Kaynağı")
    
    # Marka Yönetimi
    brand_list = list(st.session_state.brands.keys())
    selected_brand = st.selectbox("Marka Seç", brand_list, index=brand_list.index(st.session_state.active_brand))
    
    # Yeni Marka
    with st.expander("Yeni Marka Ekle"):
        new_brand = st.text_input("Marka Adı")
        if st.button("Ekle"):
            if new_brand:
                st.session_state.brands[new_brand] = {"context": "", "competitors": ["", "", ""], "gsc_url": ""}
                st.session_state.active_brand = new_brand
                st.rerun()

    if selected_brand != st.session_state.active_brand:
        st.session_state.active_brand = selected_brand
        st.rerun()
        
    st.divider()
    
    # Mod Seçimi (GSC mi Keyword Research mü?)
    analysis_mode = st.radio("Analiz Modu", ["🔍 Keyword Research (Pazar)", "📈 GSC Performance (Site Verisi)"])
    
    st.divider()
    
    active_data = st.session_state.brands[st.session_state.active_brand]
    
    if analysis_mode == "📈 GSC Performance (Site Verisi)":
        st.info("Bu modda Google Search Console verileri çekilir.")
        gsc_url_input = st.text_input("GSC Mülk URL'si (sc-domain: veya https://)", value=active_data.get("gsc_url", ""), placeholder="https://planb.media/")
        # URL'i kaydet
        st.session_state.brands[st.session_state.active_brand]["gsc_url"] = gsc_url_input
        
    else:
        # Keyword Research Ayarları
        if 'keyword_input_val' not in st.session_state: st.session_state.keyword_input_val = "takım elbise"
        keyword_input = st.text_input("Anahtar Kelime", key="keyword_input_val")
        country_map = {"Türkiye": 2792, "ABD": 2840}
        country = st.selectbox("Ülke", list(country_map.keys()))

    # Marka Bilgileri
    with st.expander("Marka Detayları & Rakipler"):
        brand_context = st.text_area("Marka Tanımı", value=active_data["context"])
        c1 = st.text_input("Rakip 1", value=active_data["competitors"][0])
        c2 = st.text_input("Rakip 2", value=active_data["competitors"][1])
        c3 = st.text_input("Rakip 3", value=active_data["competitors"][2])
        st.session_state.brands[st.session_state.active_brand]["context"] = brand_context
        st.session_state.brands[st.session_state.active_brand]["competitors"] = [c1, c2, c3]

    btn_analyze = st.button("Analizi Başlat", type="primary")

# --- ANA EKRAN ---
col_logo, col_header = st.columns([1, 5])
with col_logo:
    try: st.image("logo.png", width=150)
    except: st.write("🅱️")
with col_header:
    st.title("PlanB Media SEO Agent V11.0")
    st.caption(f"Aktif Marka: **{st.session_state.active_brand}** | Mod: **{analysis_mode}**")

if btn_analyze:
    
    # --- MOD 1: GSC PERFORMANS ANALİZİ ---
    if analysis_mode == "📈 GSC Performance (Site Verisi)":
        target_url = active_data.get("gsc_url")
        if not target_url:
            st.error("Lütfen bir GSC URL'si girin.")
        else:
            with st.spinner("Google Search Console verileri çekiliyor..."):
                df_gsc = get_gsc_data(target_url, days=30)
                
                if df_gsc is not None and not df_gsc.empty:
                    # GSC Özet Metrikleri
                    total_clicks = df_gsc['Clicks'].sum()
                    total_imp = df_gsc['Impressions'].sum()
                    avg_ctr = round(df_gsc['CTR'].mean(), 2)
                    avg_pos = round(df_gsc['Position'].mean(), 1)
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Toplam Tıklama (30 Gün)", f"{total_clicks:,}")
                    c2.metric("Toplam Gösterim", f"{total_imp:,}")
                    c3.metric("Ortalama CTR", f"%{avg_ctr}")
                    c4.metric("Ortalama Pozisyon", avg_pos)
                    
                    st.divider()
                    
                    # Tablolar
                    tab1, tab2 = st.tabs(["🔥 En İyi Kelimeler", "📄 En İyi Sayfalar"])
                    
                    with tab1:
                        # Query bazlı gruplama
                        df_query = df_gsc.groupby("Query").agg({'Clicks':'sum', 'Impressions':'sum', 'CTR':'mean', 'Position':'mean'}).reset_index()
                        df_query = df_query.sort_values("Clicks", ascending=False).head(50)
                        st.dataframe(df_query, use_container_width=True, hide_index=True)
                        
                    with tab2:
                        # Sayfa bazlı gruplama
                        df_page = df_gsc.groupby("Page").agg({'Clicks':'sum', 'Impressions':'sum', 'CTR':'mean', 'Position':'mean'}).reset_index()
                        df_page = df_page.sort_values("Clicks", ascending=False).head(50)
                        st.dataframe(df_page, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    
                    # AI GSC Analizi
                    st.subheader("🤖 PlanB GSC Insights")
                    
                    # Analiz için veri hazırlığı (En çok gösterim alıp az tıklananlar - Fırsatlar)
                    df_opp = df_query[df_query['Position'] > 3].sort_values("Impressions", ascending=False).head(10)
                    opp_txt = df_opp[['Query', 'Position', 'CTR']].to_string(index=False)
                    
                    prompt = f"""
                    Sen Kıdemli bir SEO Analistisin.
                    Marka: {st.session_state.active_brand}
                    Context: {active_data['context']}
                    
                    Son 30 günlük Google Search Console verilerini analiz ettik.
                    
                    DURUM 1: POTANSİYEL FIRSATLAR (Yüksek Gösterim, Düşük Sıralama/CTR)
                    Aşağıdaki kelimeler çok aranıyor ama biz gerideyiz veya az tıklanıyoruz:
                    {opp_txt}
                    
                    GÖREV:
                    Bu verilere bakarak site trafiğini artırmak için 3 adet somut "Quick Win" (Hızlı Kazanım) önerisi ver.
                    Hangi kelimeye odaklanalım? Mevcut sayfayı mı güncelleyelim yoksa yeni mi yazalım?
                    """
                    
                    try:
                        response = model.generate_content(prompt)
                        st.markdown(response.text)
                    except Exception as e:
                        st.warning(f"AI Analizi yapılamadı: {e}")
                
                elif df_gsc is not None and df_gsc.empty:
                    st.warning("GSC verisi boş döndü. Tarih aralığında veri olmayabilir veya mülk URL'si yanlış.")

    # --- MOD 2: KEYWORD RESEARCH (ESKİ MOD) ---
    else:
        with st.spinner("Pazar araştırması yapılıyor..."):
            raw_df = get_dataforseo_data(keyword_input, country_map[country], "tr" if country=="Türkiye" else "en")
            if raw_df is not None and not raw_df.empty:
                df_filtered = strict_filter(raw_df, keyword_input)
                df_filtered = df_filtered.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                
                if df_filtered.empty:
                    st.warning("Strict filtre sonrası veri kalmadı.")
                else:
                    c1, c2 = st.columns(2)
                    c1.metric("Toplam Hacim", f"{df_filtered['Volume'].sum():,}")
                    c2.metric("Kelime Sayısı", len(df_filtered))
                    
                    st.dataframe(df_filtered, use_container_width=True)
                    
                    # Keyword Research AI Stratejisi
                    st.divider()
                    st.subheader("🧠 İçerik Planlayıcısı")
                    top_kws = ", ".join(df_filtered.head(10)['Keyword'].tolist())
                    
                    prompt = f"""
                    Marka: {active_data['context']}
                    Rakipler: {active_data['competitors']}
                    Konu: {keyword_input}
                    Kelimeler: {top_kws}
                    
                    Rakipleri ve markayı düşünerek 3 adet Blog İçerik Fikri öner.
                    """
                    try:
                        response = model.generate_content(prompt)
                        st.markdown(response.text)
                    except:
                        st.warning("AI meşgul.")
            else:
                st.warning("Veri bulunamadı.")
