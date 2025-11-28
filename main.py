import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import google.generativeai as genai
import json

# --- AYARLAR ---
st.set_page_config(page_title="AI SEO App", layout="wide")

import streamlit as st

# Şifreleri Streamlit'in güvenli kasasından (secrets) çekiyoruz
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
DFS_LOGIN = st.secrets["DFS_LOGIN"]
DFS_PASSWORD = st.secrets["DFS_PASSWORD"]

# Gemini Başlat
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    pass # Sessizce geç, aşağıda kontrol ederiz

# --- YENİ API FONKSİYONU (KEYWORD IDEAS) ---
def get_data(keyword, loc, lang):
    # Endpoint değişti: keyword_ideas (Daha stabil)
    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"
    
    # Keyword Ideas için payload yapısı farklıdır (Liste ister)
    payload = [{
        "keywords": [keyword], 
        "location_code": loc, 
        "language_code": lang, 
        "limit": 100,
        "include_seed_keyword": True 
    }]
    
    try:
        response = requests.post(url, auth=(DFS_LOGIN, DFS_PASSWORD), json=payload)
        res = response.json()

        # 1. Bağlantı Hatası Kontrolü
        if response.status_code != 200:
            st.error(f"API Bağlantı Hatası: {response.status_code}")
            st.json(res) # Detayı görelim
            return None

        # 2. DataForSEO İç Hata Kontrolü
        if 'tasks' not in res or not res['tasks']:
            st.error("API Cevabı Beklenmedik Format:")
            st.json(res)
            return None
            
        task = res['tasks'][0]
        if task['status_code'] != 20000:
            st.error(f"DataForSEO Hatası: {task['status_message']}")
            return None

        # 3. Veri Çekme (Hata: 'keyword' burada çözüldü)
        if task['result'] and task['result'][0]['items']:
            items = task['result'][0]['items']
            data = []
            
            for i in items:
                # Garantiye alalım: keyword yoksa atla
                if 'keyword' not in i:
                    continue
                    
                data.append({
                    "Keyword": i['keyword'],
                    "Volume": i.get('keyword_info', {}).get('search_volume', 0),
                    "KD": i.get('keyword_properties', {}).get('keyword_difficulty', 0),
                    "CPC": i.get('keyword_info', {}).get('cpc', 0),
                    "Intent": i.get('search_intent_info', {}).get('main_intent', 'Unknown')
                })
            
            df = pd.DataFrame(data)
            # Sıralama
            if not df.empty:
                df = df.sort_values(by="Volume", ascending=False).reset_index(drop=True)
            return df
        else:
            return pd.DataFrame() # Boş döndür
            
    except Exception as e:
        st.error(f"Kod İçinde Hata Oluştu: {e}")
        return None

# --- ARAYÜZ ---
st.title("🔎 Gerçek Verili SEO Analizi (V6.0 Final)")
st.info("Endpoint: keyword_ideas | Status: Live")

with st.sidebar:
    st.header("Ayarlar")
    kw = st.text_input("Anahtar Kelime", "takım elbise")
    url_input = st.text_input("Web Sitesi URL", "")
    btn = st.button("Analiz Et", type="primary")

if btn:
    if not DFS_PASSWORD or "BURAYA" in DFS_PASSWORD:
        st.error("Lütfen kodun içine DataForSEO şifrenizi girdiğinizden emin olun.")
    else:
        with st.spinner("DataForSEO ve Gemini çalışıyor..."):
            # Türkiye (2792) ve Türkçe (tr)
            df = get_data(kw, 2792, "tr")
            
            if df is not None and not df.empty:
                # METRİKLER
                top_vol = df['Volume'].sum()
                avg_kd = int(df['KD'].mean())
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Toplam Hacim", f"{top_vol:,}")
                c2.metric("Ortalama Zorluk", f"%{avg_kd}")
                c3.metric("Kelime Sayısı", len(df))
                
                st.divider()
                
                # TABLO VE GRAFİK
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.subheader("📊 Hacim Grafiği")
                    fig = px.bar(df.head(10), x='Volume', y='Keyword', orientation='h', color='KD')
                    fig.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)
                    
                with col2:
                    st.subheader("📋 Kelime Listesi")
                    st.dataframe(df, use_container_width=True, height=400)
                    
                    # CSV İndir
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Listeyi İndir (CSV)", csv, "keywords.csv", "text/csv")
                
                # AI YORUMU
                st.divider()
                st.subheader("🧠 AI İçerik Önerileri")
                
                top_kws = ", ".join(df.head(5)['Keyword'].tolist())
                url_txt = f"Web Sitesi: {url_input}" if url_input else ""
                
                prompt = f"""
                Sen uzman bir SEO stratejistisin.
                Konu: {kw}
                {url_txt}
                
                Gerçek verilerle en çok aranan kelimeler şunlar: {top_kws}
                
                Lütfen bu verilere dayanarak trafik getirecek 3 adet Blog Başlığı öner.
                Her başlık için 'Neden?' kısmını kısa tut.
                """
                
                try:
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                except Exception as e:
                    st.warning(f"AI Yanıt Oluşturamadı: {e}")
                    
            elif df is not None and df.empty:
                st.warning("DataForSEO sonuç döndürmedi. Kelime çok niş olabilir veya bakiye/limit sorunu olabilir.")