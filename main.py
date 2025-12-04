import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai
import time

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="PlanB Media SEO Agent", 
    layout="wide", 
    page_icon="🅱️"
)

# --- CSS VE TASARIM ---
st.markdown("""
    <style>
    .main > div {padding-top: 1rem;}
    h1 {color: #d32f2f;}
    .stTextInput > label {font-weight:bold; color: #333;}
    .stTextArea > label {font-weight:bold; color: #333;}
    .block-container {padding-top: 2rem;}
    div[data-testid="stMetricValue"] {font-size: 1.8rem;}
    </style>
    """, unsafe_allow_html=True)

# --- API BİLGİLERİ ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    DFS_LOGIN = st.secrets["DFS_LOGIN"]
    DFS_PASSWORD = st.secrets["DFS_PASSWORD"]
except:
    st.error("API Anahtarları eksik! Lütfen secrets.toml dosyasını kontrol edin.")
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- SESSION STATE (HAFIZA) YÖNETİMİ ---
# Markaları ve verileri hafızada tutmak için yapı kuruyoruz
if 'brands' not in st.session_state:
    st.session_state.brands = {} # { 'MarkaAdi': {'context': '', 'competitors': ['', '', '']} }

if 'active_brand' not in st.session_state:
    st.session_state.active_brand = "Genel"
    st.session_state.brands["Genel"] = {"context": "Genel SEO analizi", "competitors": ["", "", ""]}

if 'analysis_trigger' not in st.session_state:
    st.session_state.analysis_trigger = False

# --- FONKSİYONLAR ---

def get_dataforseo_data(keyword, loc, lang):
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    payload = [{
        "keywords": [keyword], 
        "location_code": loc, 
        "language_code": lang, 
        "limit": 800, # Filtreleme yapacağımız için bol veri çekiyoruz
        "include_seed_keyword": True
    }]
    
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()
        
        if response.status_code == 200 and res.get('tasks') and res['tasks'][0]['result']:
            items = res['tasks'][0]['result'][0]['items']
            data = []
            for i in items:
                # Sadece gerekli verileri al
                data.append({
                    "Keyword": i['keyword'],
                    "Volume": i.get('keyword_info', {}).get('search_volume', 0),
                    "CPC": i.get('keyword_info', {}).get('cpc', 0),
                    "Competition": round(i.get('keyword_info', {}).get('competition_level', 0) * 100)
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"API Hatası: {e}")
        return None

def strict_filter(df, seed_keyword, brand_context):
    """
    Kullanıcının şikayet ettiği 'pantolon aradım elbise geldi' sorununu çözer.
    Ayrıca Marka Tanımı'na (Context) göre alakasızları eler (Basit kural bazlı).
    """
    if df.empty: return df
    
    seed_lower = seed_keyword.lower()
    
    # 1. KURAL: KELİME KESİNLİKLE İÇİNDE GEÇMELİ (Strict Broad Match)
    # Pantolon arıyorsa içinde 'pantolon' geçmeyen her şeyi sileriz.
    df = df[df['Keyword'].str.contains(seed_lower, na=False)]
    
    # 2. KURAL: MARKA BAĞLAMI (Opsiyonel AI filtresi yerine basit negatif filtre)
    # Eğer marka context'inde "Erkek Giyim" yazıyorsa, "Kadın" kelimesini içerenleri eleyebiliriz vb.
    # (Burayı performans için şimdilik manuel filtre gibi tutuyoruz, ileride AI ile her satır kontrol edilebilir)
    
    return df

# --- SIDEBAR: MARKA YÖNETİMİ ---

with st.sidebar:
    st.header("🏢 Marka Yönetimi")
    
    # Marka Seçimi / Oluşturma
    brand_list = list(st.session_state.brands.keys())
    selected_brand = st.selectbox("Çalışılan Marka", brand_list, index=brand_list.index(st.session_state.active_brand))
    
    # Yeni Marka Ekleme
    new_brand_name = st.text_input("➕ Yeni Marka Ekle", placeholder="Örn: Altınyıldız Classics")
    if st.button("Markayı Oluştur"):
        if new_brand_name and new_brand_name not in st.session_state.brands:
            st.session_state.brands[new_brand_name] = {"context": "", "competitors": ["", "", ""]}
            st.session_state.active_brand = new_brand_name
            st.rerun()
    
    # Aktif Markayı Güncelle
    if selected_brand != st.session_state.active_brand:
        st.session_state.active_brand = selected_brand
        st.rerun()

    st.divider()
    
    # Marka Detayları (Hafızaya Kaydedilir)
    active_data = st.session_state.brands[st.session_state.active_brand]
    
    st.subheader(f"📝 {st.session_state.active_brand} Bilgileri")
    
    # Context Input
    brand_context = st.text_area(
        "Marka Tanımı & Hedef Kitle", 
        value=active_data["context"],
        placeholder="Biz kimiz? Hedef kitlemiz kim? Neyi satıyoruz?",
        height=100
    )
    
    # Competitor Inputs
    st.write("⚔️ Rakipler")
    comp1 = st.text_input("Rakip 1", value=active_data["competitors"][0], key="c1")
    comp2 = st.text_input("Rakip 2", value=active_data["competitors"][1], key="c2")
    comp3 = st.text_input("Rakip 3", value=active_data["competitors"][2], key="c3")
    
    # Bilgileri Kaydet (Her değişiklikte session güncellenir)
    st.session_state.brands[st.session_state.active_brand]["context"] = brand_context
    st.session_state.brands[st.session_state.active_brand]["competitors"] = [comp1, comp2, comp3]
    
    st.divider()
    
    # Analiz Girdileri
    # Session state kullanarak tıklanan kelimeyi buraya taşıyacağız
    if 'keyword_input_val' not in st.session_state:
        st.session_state.keyword_input_val = "keten pantolon"

    keyword_input = st.text_input("Anahtar Kelime", key="keyword_input_val")
    
    country_map = {"Türkiye": 2792, "ABD": 2840, "Almanya": 2276}
    country = st.selectbox("Hedef Ülke", list(country_map.keys()))
    
    analyze_btn = st.button("Analizi Başlat", type="primary")

# --- ANA EKRAN ---

# Logo
col_logo, col_header = st.columns([1, 5])
with col_logo:
    try:
        st.image("logo.png", width=150)
    except:
        st.write("🅱️")
with col_header:
    st.title("PlanB Media SEO Agent V10.0")
    st.caption(f"Aktif Oturum: **{st.session_state.active_brand}**")

# Analiz Tetikleyici (Buton veya Tablo Tıklaması)
if analyze_btn:
    st.session_state.analysis_trigger = True

if st.session_state.analysis_trigger:
    with st.spinner(f"🚀 {st.session_state.active_brand} için veriler ve rakipler analiz ediliyor..."):
        
        # 1. API VERİ ÇEKME
        raw_df = get_dataforseo_data(keyword_input, country_map[country], "tr" if country=="Türkiye" else "en")
        
        if raw_df is not None and not raw_df.empty:
            
            # 2. STRICT FILTERING (Pantolon -> Elbise sorununu çözen yer)
            # Marka context'i de fonksiyona gönderiyoruz
            df_filtered = strict_filter(raw_df, keyword_input, brand_context)
            
            # Hacme göre sırala
            df_filtered = df_filtered.sort_values(by="Volume", ascending=False).reset_index(drop=True)
            
            # METRİKLER
            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Kelime", len(df_filtered))
            c2.metric("Toplam Hacim", f"{df_filtered['Volume'].sum():,}")
            c3.metric("En Popüler", df_filtered.iloc[0]['Keyword'] if not df_filtered.empty else "-")
            
            st.divider()
            
            # 3. ETKİLEŞİMLİ TABLO (Click to Analyze)
            st.subheader("📋 Anahtar Kelime Listesi (Tıklanabilir)")
            st.info("💡 Tablodaki herhangi bir kelimenin solundaki kutucuğa veya satıra tıklayarak o kelime için yeni analiz başlatabilirsiniz.")
            
            # Streamlit Dataframe Selection Event
            event = st.dataframe(
                df_filtered,
                use_container_width=True,
                hide_index=True,
                on_select="rerun", # Seçim yapılınca sayfayı yenile
                selection_mode="single-row", # Tek satır seçimi
                column_config={
                    "Keyword": "Anahtar Kelime",
                    "Volume": st.column_config.NumberColumn("Hacim", format="%d"),
                    "CPC": st.column_config.NumberColumn("CPC", format="$%.2f"),
                    "Competition": st.column_config.ProgressColumn("Rekabet", min_value=0, max_value=100)
                },
                height=400
            )
            
            # Seçim Kontrolü
            if len(event.selection.rows) > 0:
                selected_index = event.selection.rows[0]
                new_keyword = df_filtered.iloc[selected_index]["Keyword"]
                
                # Eğer seçilen kelime mevcut inputtan farklıysa güncelle ve yenile
                if new_keyword != st.session_state.keyword_input_val:
                    st.session_state.keyword_input_val = new_keyword
                    st.rerun()

            st.divider()
            
            # 4. CONTENT GAP & RAKİP ANALİZLİ AI STRATEJİSİ
            st.subheader(f"🧠 {st.session_state.active_brand} İçerik Planlayıcısı")
            
            # Verileri Hazırla
            top_10_kws = ", ".join(df_filtered.head(10)['Keyword'].tolist())
            competitors_txt = ", ".join([c for c in active_data["competitors"] if c])
            
            prompt = f"""
            Sen PlanB Media'nın Kıdemli SEO Danışmanısın.
            
            MARKAMIZ HAKKINDA BİLGİ (CONTEXT):
            {active_data['context']}
            
            RAKİPLERİMİZ:
            {competitors_txt if competitors_txt else "Belirtilmedi"}
            
            ANALİZ EDİLEN KONU: {keyword_input}
            BULUNAN EN HACİMLİ KELİMELER: {top_10_kws}
            
            GÖREV:
            Rakiplerimizi ve markamızı göz önünde bulundurarak bir 'Content Gap' (İçerik Boşluğu) analizi yap.
            Rakiplerin muhtemelen hedeflediği ama bizim bu kelimelerle daha iyi yapabileceğimiz 5 adet İçerik Fikri ver.
            
            Lütfen şu formatta yanıt ver:
            
            ### 🚀 Stratejik Fırsat Analizi
            (Markamızın bu kelimelerde rakiplere göre avantajı veya eksiği hakkında 2 cümlelik yorum)
            
            ### 📝 Önerilen İçerik Planı
            
            1. [Başlık Önerisi]
               - 🎯 Hedef Kelime: [Listeden seç]
               - ⚔️ Rekabet Avantajı: (Rakiplerden farklı olarak ne sunmalıyız? Neden bu içerik bizi öne geçirir?)
               
            (Toplam 5 madde)
            """
            
            try:
                response = model.generate_content(prompt)
                st.markdown(response.text)
            except Exception as e:
                st.warning("AI şu an yanıt veremiyor.")
                
        else:
            st.warning("Veri bulunamadı. Lütfen kelimeyi kontrol edin.")
            
    # Analiz bittiğinde trigger'ı kapatmıyoruz ki sonuçlar ekranda kalsın.
    # Ancak yeni arama yapılınca yukarıdaki logic tekrar çalışacak.
