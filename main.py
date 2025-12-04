import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import json
import re

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="PlanB Media SEO AI", layout="wide", page_icon="🅱️")

# --- CSS ---
st.markdown("""
    <style>
    .main > div {padding-top: 1rem;}
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
# Date parser için daha hızlı bir model, analiz için daha zeki model kullanılabilir
model = genai.GenerativeModel('gemini-2.0-flash') 

# --- SESSION STATE ---
if 'brands' not in st.session_state:
    st.session_state.brands = {} 
    # Varsayılan bir demo proje
    st.session_state.brands["Demo Proje"] = {"gsc_url": "", "context": ""}

if 'active_brand' not in st.session_state:
    st.session_state.active_brand = "Demo Proje"

if 'messages' not in st.session_state:
    st.session_state.messages = []

# --- YARDIMCI FONKSİYONLAR ---

@st.cache_resource
def get_gsc_service():
    creds = service_account.Credentials.from_service_account_info(
        gsc_info, scopes=['https://www.googleapis.com/auth/webmasters.readonly']
    )
    return build('searchconsole', 'v1', credentials=creds)

def fetch_gsc_data(site_url, start_date, end_date):
    """GSC API'den veri çeker"""
    service = get_gsc_service()
    request = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['query'],
        'rowLimit': 25000
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
        return None

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
                    "Competition": int(float(kw_info.get('competition_level', 0)) * 100)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except:
        return None

def extract_dates_from_prompt(user_prompt):
    """
    Kullanıcının yazdığı metinden tarih aralığını anlayan AI fonksiyonu.
    Örn: "Geçen hafta" -> start: 2023-10-01, end: 2023-10-07
    """
    today = datetime.date.today()
    
    system_prompt = f"""
    Bugünün tarihi: {today}.
    Kullanıcı bir GSC veri analizi isteyecek. Metinden kastedilen tarih aralığını çıkar.
    Eğer kullanıcı tarih belirtmezse varsayılan olarak "son 28 günü" al.
    
    Çıktıyı SADECE şu JSON formatında ver, başka hiçbir şey yazma:
    {{
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD"
    }}
    
    Kullanıcı Metni: "{user_prompt}"
    """
    try:
        response = model.generate_content(system_prompt)
        # JSON temizleme (Bazen markdown ```json ... ``` dönebilir)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        dates = json.loads(clean_text)
        return dates['start_date'], dates['end_date']
    except:
        # Hata olursa son 28 günü dön
        end = today
        start = today - datetime.timedelta(days=28)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

# --- ARAYÜZ ---
st.title("PlanB Media SEO Agent v2.0")

tab_kw, tab_gsc = st.tabs(["🔍 Keyword Research & Proje", "🤖 GSC Chatbot"])

# ==========================================
# TAB 1: KEYWORD RESEARCH VE PROJE YÖNETİMİ
# ==========================================
with tab_kw:
    # --- PROJE YÖNETİM ALANI ---
    st.markdown("### 📁 Proje Yönetimi")
    p_col1, p_col2, p_col3 = st.columns([2, 2, 2])
    
    with p_col1:
        # Mevcut markaları listele
        brand_list = list(st.session_state.brands.keys())
        selected_brand = st.selectbox("Çalışılan Proje", brand_list, index=brand_list.index(st.session_state.active_brand))
        
        # Seçim değişirse güncelle
        if selected_brand != st.session_state.active_brand:
            st.session_state.active_brand = selected_brand
            st.session_state.messages = [] # Sohbeti temizle
            st.rerun()

    with p_col2:
        new_brand_name = st.text_input("Yeni Proje Oluştur", placeholder="Marka Adı (Örn: Altınyıldız)")
    
    with p_col3:
        st.write("") # Hizalama boşluğu
        if st.button("➕ Projeyi Kaydet"):
            if new_brand_name and new_brand_name not in st.session_state.brands:
                st.session_state.brands[new_brand_name] = {"gsc_url": "", "context": ""}
                st.session_state.active_brand = new_brand_name
                st.success(f"{new_brand_name} oluşturuldu!")
                st.rerun()

    st.divider()
    
    # --- GSC URL KAYDI ---
    # Her proje için GSC URL'si burada tanımlanır, hafızada kalır
    st.markdown(f"**{st.session_state.active_brand}** İçin Ayarlar")
    current_gsc = st.session_state.brands[st.session_state.active_brand].get("gsc_url", "")
    new_gsc = st.text_input("GSC Mülk URL (sc-domain: veya https://)", value=current_gsc)
    if new_gsc != current_gsc:
        st.session_state.brands[st.session_state.active_brand]["gsc_url"] = new_gsc
        st.toast("GSC URL Kaydedildi!")

    st.divider()

    # --- KEYWORD RESEARCH TOOL ---
    st.subheader("Anahtar Kelime Analizi")
    kw_col1, kw_col2, kw_col3 = st.columns([3, 1, 1])
    with kw_col1:
        kw_input = st.text_input("Kelime Girin", placeholder="takım elbise")
    with kw_col2:
        country_map = {"Türkiye": 2792, "ABD": 2840}
        country = st.selectbox("Ülke", list(country_map.keys()))
    with kw_col3:
        st.write("")
        analyze_click = st.button("Analiz Et", type="primary", use_container_width=True)

    if analyze_click and kw_input:
        with st.spinner("Analiz ediliyor..."):
            df_kw = get_dataforseo_data(kw_input, country_map[country], "tr" if country=="Türkiye" else "en")
            if df_kw is not None and not df_kw.empty:
                df_kw = df_kw[df_kw['Keyword'].str.contains(kw_input.lower())]
                st.dataframe(df_kw.sort_values("Volume", ascending=False), use_container_width=True)
            else:
                st.warning("Veri bulunamadı.")

# ==========================================
# TAB 2: GSC CHATBOT (AI AGENT)
# ==========================================
with tab_gsc:
    active_gsc_url = st.session_state.brands[st.session_state.active_brand].get("gsc_url")
    
    if not active_gsc_url:
        st.warning(f"⚠️ **{st.session_state.active_brand}** projesi için GSC URL tanımlanmamış. Lütfen 'Keyword Research & Proje' sekmesinden ekleyin.")
    else:
        st.info(f"🤖 **{st.session_state.active_brand}** Asistanı devrede. Tarih belirtmeden soru sorabilirsiniz (Varsayılan: Son 28 gün).")

        # Chat Geçmişi
        for msg in st.session_state.messages:
            st.chat_message(msg["role"]).write(msg["content"])

        # Kullanıcı Girdisi
        if user_prompt := st.chat_input("Örn: Geçen ayki brand trafiğim nasıldı? En çok tıklanan kelimeler neler?"):
            st.chat_message("user").write(user_prompt)
            st.session_state.messages.append({"role": "user", "content": user_prompt})
            
            with st.spinner("Tarih algılanıyor ve veri çekiliyor..."):
                # 1. Adım: Tarih Aralığını AI ile Belirle
                start_d, end_d = extract_dates_from_prompt(user_prompt)
                
                # 2. Adım: Veriyi Çek
                df_gsc = fetch_gsc_data(active_gsc_url, start_d, end_d)
                
                if df_gsc is not None and not df_gsc.empty:
                    # 3. Adım: Brand / Non-Brand Otomatik Algılama
                    # Proje adını parçala (Örn: "PlanB Media" -> ["planb", "media"])
                    brand_name_tokens = st.session_state.active_brand.lower().split()
                    
                    def auto_classify(query):
                        q = str(query).lower()
                        # Eğer proje adındaki kelimelerden biri sorguda geçiyorsa Brand'dir
                        for token in brand_name_tokens:
                            if len(token) > 2 and token in q: # 2 harften kısa kelimeleri (ve, ile vs) yoksay
                                return "Brand"
                        return "Non-Brand"
                    
                    df_gsc['Type'] = df_gsc['Query'].apply(auto_classify)
                    
                    # 4. Adım: İstatistik Özeti Oluştur
                    total_clicks = df_gsc['Clicks'].sum()
                    brand_clicks = df_gsc[df_gsc['Type']=='Brand']['Clicks'].sum()
                    non_brand_clicks = df_gsc[df_gsc['Type']=='Non-Brand']['Clicks'].sum()
                    top_queries = df_gsc.nlargest(15, 'Clicks')[['Query', 'Clicks', 'Type']].to_string(index=False)
                    
                    context_summary = f"""
                    RAPOR TARİH ARALIĞI: {start_d} ile {end_d}
                    TOPLAM TIKLAMA: {total_clicks}
                    MARKA (BRAND) TIKLAMA: {brand_clicks}
                    MARKA DIŞI (NON-BRAND) TIKLAMA: {non_brand_clicks}
                    
                    EN İYİ 15 SORGU:
                    {top_queries}
                    """
                    
                    # 5. Adım: AI'dan Cevap Al
                    final_prompt = f"""
                    Sen bir SEO uzmanısın. Kullanıcının sorusunu aşağıdaki verilere dayanarak cevapla.
                    Marka Adı: {st.session_state.active_brand}
                    
                    VERİLER:
                    {context_summary}
                    
                    KULLANICI SORUSU: "{user_prompt}"
                    
                    Analitik konuş, rakam ver. Brand ve Non-brand ayrımına dikkat et.
                    """
                    
                    try:
                        ai_response = model.generate_content(final_prompt)
                        reply_text = ai_response.text
                    except Exception as e:
                        reply_text = f"AI Hatası: {e}"
                        
                else:
                    reply_text = f"Belirtilen tarihlerde ({start_d} - {end_d}) veri bulunamadı veya GSC erişim hatası."

            # Cevabı yazdır
            st.chat_message("assistant").write(reply_text)
            st.session_state.messages.append({"role": "assistant", "content": reply_text})
