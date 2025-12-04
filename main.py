import streamlit as st
import pandas as pd
import requests
import google.generativeai as genai

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
if 'brands' not in st.session_state:
    st.session_state.brands = {} 

if 'active_brand' not in st.session_state:
    st.session_state.active_brand = "Genel"
    st.session_state.brands["Genel"] = {"context": "Genel SEO analizi", "competitors": ["", "", ""]}

if 'analysis_trigger' not in st.session_state:
    st.session_state.analysis_trigger = False

# --- YARDIMCI FONKSİYONLAR ---

def safe_float(val):
    """Gelen veriyi güvenli bir şekilde ondalıklı sayıya çevirir."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def get_dataforseo_data(keyword, loc, lang):
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    payload = [{
        "keywords": [keyword], 
        "location_code": loc, 
        "language_code": lang, 
        "limit": 800, 
        "include_seed_keyword": True
    }]
    
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()
        
        if response.status_code == 200 and res.get('tasks') and res['tasks'][0]['result']:
            items = res['tasks'][0]['result'][0]['items']
            data = []
            for i in items:
                # Güvenli Veri Çekme (Hata Düzeltildi)
                kw_info = i.get('keyword_info', {})
                
                # Competition verisi string gelebilir, önce float'a çeviriyoruz
                comp_val = safe_float(kw_info.get('competition_level', 0))
                
                data.append({
                    "Keyword": i['keyword'],
                    "Volume": kw_info.get('search_volume', 0),
                    "CPC": kw_info.get('cpc', 0),
                    "Competition": int(comp_val * 100) # 0-1 arasını 0-100 yap
                })
            return pd.DataFrame(data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"API Veri İşleme Hatası: {e}")
        return None

def strict_filter(df, seed_keyword, brand_context):
    if df.empty: return df
    seed_lower = seed_keyword.lower()
    # İçinde anahtar kelime geçmeyenleri sil (Pantolon ararken elbise gelmesin)
    df = df[df['Keyword'].str.contains(seed_lower, na=False)]
    return df

# --- SIDEBAR: MARKA YÖNETİMİ ---

with st.sidebar:
    st.header("🏢 Marka Yönetimi")
    
    brand_list = list(st.session_state.brands.keys())
    selected_brand = st.selectbox("Çalışılan Marka", brand_list, index=brand_list.index(st.session_state.active_brand))
    
    new_brand_name = st.text_input("➕ Yeni Marka Ekle", placeholder="Örn: Altınyıldız Classics")
    if st.button("Markayı Oluştur"):
        if new_brand_name and new_brand_name not in st.session_state.brands:
            st.session_state.brands[new_brand_name] = {"context": "", "competitors": ["", "", ""]}
            st.session_state.active_brand = new_brand_name
            st.rerun()
    
    if selected_brand != st.session_state.active_brand:
        st.session_state.active_brand = selected_brand
        st.rerun()

    st.divider()
    
    active_data = st.session_state.brands[st.session_state.active_brand]
    
    st.subheader(f"📝 {st.session_state.active_brand} Bilgileri")
    
    brand_context = st.text_area(
        "Marka Tanımı & Hedef Kitle", 
        value=active_data["context"],
        height=100
    )
    
    st.write("⚔️ Rakipler")
    comp1 = st.text_input("Rakip 1", value=active_data["competitors"][0], key="c1")
    comp2 = st.text_input("Rakip 2", value=active_data["competitors"][1], key="c2")
    comp3 = st.text_input("Rakip 3", value=active_data["competitors"][2], key="c3")
    
    st.session_state.brands[st.session_state.active_brand]["context"] = brand_context
    st.session_state.brands[st.session_state.active_brand]["competitors"] = [comp1, comp2, comp3]
    
    st.divider()
    
    if 'keyword_input_val' not in st.session_state:
        st.session_state.keyword_input_val = "takım elbise"

    keyword_input = st.text_input("Anahtar Kelime", key="keyword_input_val")
    
    country_map = {"Türkiye": 2792, "ABD": 2840, "Almanya": 2276}
    country = st.selectbox("Hedef Ülke", list(country_map.keys()))
    
    analyze_btn = st.button("Analizi Başlat", type="primary")

# --- ANA EKRAN ---

col_logo, col_header = st.columns([1, 5])
with col_logo:
    try:
        st.image("logo.png", width=150)
    except:
        st.write("🅱️")
with col_header:
    st.title("PlanB Media SEO Agent V10.1")
    st.caption(f"Aktif Oturum: **{st.session_state.active_brand}**")

if analyze_btn:
    st.session_state.analysis_trigger = True

if st.session_state.analysis_trigger:
    with st.spinner(f"🚀 {st.session_state.active_brand} için veriler analiz ediliyor..."):
        
        raw_df = get_dataforseo_data(keyword_input, country_map[country], "tr" if country=="Türkiye" else "en")
        
        if raw_df is not None and not raw_df.empty:
            
            df_filtered = strict_filter(raw_df, keyword_input, brand_context)
            df_filtered = df_filtered.sort_values(by="Volume", ascending=False).reset_index(drop=True)
            
            if df_filtered.empty:
                st.warning("Seçilen kelimeyi içeren sonuç bulunamadı (Strict Filter devrede).")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Toplam Kelime", len(df_filtered))
                c2.metric("Toplam Hacim", f"{df_filtered['Volume'].sum():,}")
                c3.metric("En Popüler", df_filtered.iloc[0]['Keyword'])
                
                st.divider()
                
                st.subheader("📋 Anahtar Kelime Listesi (Tıklanabilir)")
                st.info("💡 Tablodaki kelimelere tıklayarak yeni analiz başlatabilirsiniz.")
                
                event = st.dataframe(
                    df_filtered,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    column_config={
                        "Keyword": "Anahtar Kelime",
                        "Volume": st.column_config.NumberColumn("Hacim", format="%d"),
                        "CPC": st.column_config.NumberColumn("CPC", format="$%.2f"),
                        "Competition": st.column_config.ProgressColumn("Rekabet", min_value=0, max_value=100)
                    },
                    height=400
                )
                
                if len(event.selection.rows) > 0:
                    selected_index = event.selection.rows[0]
                    new_keyword = df_filtered.iloc[selected_index]["Keyword"]
                    
                    if new_keyword != st.session_state.keyword_input_val:
                        st.session_state.keyword_input_val = new_keyword
                        st.rerun()

                st.divider()
                
                st.subheader(f"🧠 {st.session_state.active_brand} İçerik Planlayıcısı")
                
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
                   - ⚔️ Rekabet Avantajı: (Rakiplerden farklı olarak ne sunmalıyız?)
                   
                (Toplam 5 madde)
                """
                
                try:
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                except Exception as e:
                    st.warning("AI şu an yanıt veremiyor.")
        else:
            st.warning("Veri bulunamadı. Lütfen kelimeyi kontrol edin.")
