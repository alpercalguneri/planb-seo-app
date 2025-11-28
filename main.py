import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="PlanB Media Keyword Research Tool", 
    layout="wide", 
    page_icon="🅱️"
)

# --- CSS AYARLARI ---
st.markdown("""
    <style>
    .main > div {padding-top: 1rem;}
    h1 {color: #333333;}
    .stMetric {background-color: #f9f9f9; padding: 10px; border-radius: 10px; border: 1px solid #eee;}
    </style>
    """, unsafe_allow_html=True)

# --- API BİLGİLERİ (SECRETS) ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    DFS_LOGIN = st.secrets["DFS_LOGIN"]
    DFS_PASSWORD = st.secrets["DFS_PASSWORD"]
except:
    st.error("Lütfen API anahtarlarınızı secrets.toml dosyasına ekleyin.")
    st.stop()

# Gemini Başlat
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- ÜLKE VE DİL KONFİGÜRASYONU ---
# Her ülkenin kodu, dili ve o dile ait soru kalıpları
COUNTRY_CONFIG = {
    "Türkiye": {
        "loc": 2792, "lang": "tr", "lang_name": "Turkish",
        "questions": ["nasıl", "nedir", "ne kadar", "nerede", "kim", "hangi", "kaç", "mı", "mi", "neden", "niye"]
    },
    "ABD": {
        "loc": 2840, "lang": "en", "lang_name": "English",
        "questions": ["how", "what", "where", "who", "which", "why", "when", "can", "is", "do"]
    },
    "İngiltere": {
        "loc": 2826, "lang": "en", "lang_name": "English",
        "questions": ["how", "what", "where", "who", "which", "why", "when", "can", "is", "do"]
    },
    "Almanya": {
        "loc": 2276, "lang": "de", "lang_name": "German",
        "questions": ["wie", "was", "wo", "wer", "warum", "wann", "welche", "kann", "ist"]
    }
}

# --- FONKSİYONLAR ---

def get_dataforseo_data(keyword, loc, lang):
    """
    DataForSEO'dan veri çeker.
    """
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    
    payload = [{
        "keywords": [keyword], 
        "location_code": loc, 
        "language_code": lang, 
        "limit": 700, 
        "include_seed_keyword": True
    }]
    
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()

        if response.status_code == 200 and res.get('tasks') and res['tasks'][0]['result']:
            items = res['tasks'][0]['result'][0]['items']
            data = []
            
            for i in items:
                # KD'yi artık çeksek de tabloda göstermeyeceğiz, ama filtre için tutabiliriz
                kw_info = i.get('keyword_info', {})
                
                data.append({
                    "Keyword": i['keyword'],
                    "Volume": kw_info.get('search_volume', 0),
                    "CPC": kw_info.get('cpc', 0),
                    # KD'yi kaldırdık
                })
            
            df = pd.DataFrame(data)
            return df
        else:
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"API Hatası: {e}")
        return None

def filter_keywords(df, match_type, seed_keyword, question_list):
    """
    Filtreleme Mantığı (Dinamik Soru Listesi ile)
    """
    if df.empty:
        return df
        
    seed_lower = seed_keyword.lower()
    
    if match_type == "Phrase Match (Sıralı)":
        return df[df['Keyword'].str.contains(seed_lower, na=False)]
        
    elif match_type == "Exact Match (Tam)":
        return df[df['Keyword'] == seed_lower]
        
    elif match_type == "Questions (Sorular)":
        # Sadece seçilen ülkenin soru kalıplarını ve ana kelimeyi içerenleri getir
        # Örn: "iphone fiyatı nedir" (Hem iphone hem nedir içermeli ki alakalı olsun)
        
        # 1. Adım: Soru kelimelerinden en az biri geçmeli
        mask_questions = df['Keyword'].str.contains('|'.join(question_list), na=False, case=False)
        
        # 2. Adım: Anahtar kelime de içinde geçmeli (Alaka düzeyi için)
        mask_seed = df['Keyword'].str.contains(seed_lower, na=False)
        
        return df[mask_questions & mask_seed]
        
    else: # Broad Match
        return df

# --- ARAYÜZ ---

# 1. LOGO YERLEŞİMİ
# 'logo.png' dosyasının main.py ile aynı klasörde olması lazım.
col_logo, col_title = st.columns([1, 4])
with col_logo:
    try:
        st.image("logo.png", width=180) 
    except:
        st.warning("logo.png bulunamadı.") # Dosya yoksa uyarı verir ama çökmez

with col_title:
    st.title("Keyword Research Tool (V1.0)")
    st.markdown("Powered by **DataForSEO** & **Gemini AI**")

st.divider()

# Sidebar
with st.sidebar:
    st.header("Analiz Parametreleri")
    
    keyword_input = st.text_input("Anahtar Kelime", "iphone 15")
    url_input = st.text_input("Hedef URL (Opsiyonel)", "")
    
    # Ülke Seçimi
    country_selected = st.selectbox("Hedef Ülke", list(COUNTRY_CONFIG.keys()))
    
    # Seçilen ülkenin ayarlarını al
    settings = COUNTRY_CONFIG[country_selected]
    
    st.divider()
    
    # Match Type Seçici
    match_type = st.radio(
        "Eşleme Türü (Filtre)",
        ["Broad Match (Geniş)", "Phrase Match (Sıralı)", "Exact Match (Tam)", "Questions (Sorular)"],
        index=0,
        help="Questions: Sadece seçilen dildeki soru kalıplarını (örn: nedir, how, wie) içeren kelimeleri getirir."
    )
    
    btn_analyze = st.button("Analizi Başlat", type="primary")

# Ana Akış
if btn_analyze:
    if not DFS_PASSWORD or "BURAYA" in DFS_PASSWORD:
        st.error("API Şifreleri girilmemiş.")
    else:
        with st.spinner(f"🚀 {country_selected} verileri taranıyor..."):
            
            # 1. Veriyi Çek
            raw_df = get_dataforseo_data(keyword_input, settings["loc"], settings["lang"])
            
            if raw_df is not None and not raw_df.empty:
                # 2. Filtrele (Dinamik soru listesini gönderiyoruz)
                df_filtered = filter_keywords(raw_df, match_type, keyword_input, settings["questions"])
                
                # Sıralama
                df_filtered = df_filtered.sort_values(by="Volume", ascending=False).reset_index(drop=True)
                
                if df_filtered.empty:
                    st.warning(f"'{match_type}' kriterine uygun kelime bulunamadı.")
                else:
                    # 3. Metrikler
                    c1, c2, c3 = st.columns(3)
                    
                    c1.metric("Listelenen Kelime", len(df_filtered))
                    c1.markdown(f"<small>Dil: {settings['lang_name']} | Filtre: {match_type}</small>", unsafe_allow_html=True)
                    
                    c2.metric("Toplam Hacim", f"{df_filtered['Volume'].sum():,}")
                    
                    top_kw = df_filtered.iloc[0]['Keyword']
                    c3.metric("En Popüler", top_kw)
                    
                    st.divider()
                    
                    # 4. Tablo (KD Çıkarıldı)
                    st.subheader("📋 Anahtar Kelime Listesi")
                    
                    st.dataframe(
                        df_filtered,
                        use_container_width=True,
                        column_config={
                            "Keyword": "Anahtar Kelime",
                            "Volume": st.column_config.NumberColumn("Hacim", format="%d"),
                            "CPC": st.column_config.NumberColumn("CPC ($)", format="$%.2f")
                        },
                        height=500
                    )
                    
                    # CSV İndirme
                    csv = df_filtered.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Listeyi CSV Olarak İndir",
                        data=csv,
                        file_name=f"planb_{keyword_input}_{settings['lang']}.csv",
                        mime="text/csv"
                    )
                    
                    # 5. AI Analizi (GELİŞMİŞ PROMPT)
                    st.divider()
                    st.subheader(f"🤖 PlanB AI Stratejisi ({country_selected})")
                    
                    top_5_rel = ", ".join(df_filtered.head(5)['Keyword'].tolist())
                    url_context = f"Web Sitesi: {url_input}" if url_input else ""
                    
                    prompt = f"""
                    Sen PlanB Media ajansının Global SEO Stratejistisin.
                    
                    ANALİZ DETAYLARI:
                    - Hedef Ülke: {country_selected}
                    - Konu: {keyword_input}
                    - {url_context}
                    - En Hacimli Kelimeler: {top_5_rel}
                    
                    GÖREV:
                    Bu verileri ve {country_selected} ülkesindeki güncel trendleri düşünerek 5 adet Blog Başlığı öner.
                    
                    KURALLAR:
                    1. Başlıklar kesinlikle {settings['lang_name']} ({settings['lang'].upper()}) dilinde olmalı.
                    2. "Neden?" açıklamaları kesinlikle TÜRKÇE olmalı.
                    3. Başlıklar {country_selected} kullanıcılarının arama niyetine ve trendlerine uygun olmalı.
                    
                    ÇIKTI FORMATI:
                    1. [Başlık ({settings['lang_name']})]
                       - 🎯 Odak: [Anahtar Kelime]
                       - 💡 Neden: [Türkçe stratejik açıklama]
                    
                    (Toplam 5 tane)
                    """
                    
                    try:
                        response = model.generate_content(prompt)
                        st.info(response.text)
                    except Exception as e:
                        st.warning(f"AI Yanıtı alınamadı: {e}")
            else:
                st.error("Veri bulunamadı. Lütfen kelimeyi veya ülkeyi kontrol edin.")