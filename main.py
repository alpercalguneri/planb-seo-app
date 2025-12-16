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
model = genai.GenerativeModel('gemini-1.5-flash') # Hız ve mantık için 1.5 Flash ideal

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
