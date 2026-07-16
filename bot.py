import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from vnstock.api.quote import Quote 

# ======================= CAU HINH BAO MAT =======================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')    
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
# ===============================================================

def is_trading_day():
    today = datetime.now().weekday()
    if today >= 5: 
        return False
    return True

def _get_history(symbol, start_date, end_date):
    sources = ['VCI', 'TCBS', 'SSI']
    for source in sources:
        try:
            q = Quote(symbol=symbol, source=source)
            df = q.history(start=start_date, end=end_date, interval='1D')
            if df is not None and not df.empty:
                df.columns = [str(c).lower() for c in df.columns]
                return df
        except Exception:
            continue 
    print(f"Loi: Khong the lay du lieu {symbol} tu tat ca cac nguon.")
    return None

def fetch_market_and_fund_data():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    latest_index = {}
    df_index = _get_history('VNINDEX', start_date, end_date)
    if df_index is not None and not df_index.empty:
        latest_index = df_index.iloc[-1].to_dict()

    funds = ['FUEVNVND', 'E1VFVN30', 'FUESSVFL']
    fund_data_summary = []

    for fund in funds:
        df_fund = _get_history(fund, start_date, end_date)
        if df_fund is not None and not df_fund.empty:
            latest_price = df_fund.iloc[-1]['close']
            prev_price = df_fund.iloc[-2]['close'] if len(df_fund) > 1 else latest_price
            pct_change = ((latest_price - prev_price) / prev_price) * 100 if prev_price else 0
            fund_data_summary.append(f"- {fund}: {latest_price:,.0f} VND ({pct_change:+.2f}%)")

    if not latest_index and not fund_data_summary:
        return None

    market_context = (
        f"Bao cao ngay: {end_date}\n"
        f"Chi so VNINDEX: {latest_index.get('close', 'N/A')} (Khoi luong: {latest_index.get('volume', 'N/A')})\n"
        f"Du lieu cac quy noi bat:\n" + ("\n".join(fund_data_summary) if fund_data_summary else "Khong co du lieu quy.")
    )
    return market_context

def analyze_with_gemini(raw_data):
    if not GEMINI_API_KEY:
        return "Loi: Chua cau hinh GEMINI_API_KEY tren GitHub Secrets."

    # Danh sach model Fallback - Dam bao 100% tim duoc model hoat dong
    models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    headers = {"Content-Type": "application/json"}

    prompt = f"""Ban la giam doc khoi phan tich quy dau tu.
Dua tren du lieu thuc te duoi day, hay lap ban tin phan tich (7-10 dong).

YEU CAU BAT BUOC 1: Toan bo cau tra loi cua ban phai duoc viet bang TIENG VIET KHONG DAU (loai bo hoan toan dau tieng Viet) de tranh loi phong.
YEU CAU BAT BUOC 2: KHONG dung cac ky tu Markdown nhu dau sao (*), dau gach duoi (_), dau thang (#). Chi dung van ban thuong va emoji.

Noi dung can co:
- Danh gia nhanh xu huong VN-Index.
- Phan tich dong luc cua cac quy ETF. 
- Canh bao rui ro va chi ra quy tiem nang nhat.

Du lieu:
{raw_data}"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 800
        }
    }

    error_logs = []
    
    # Vong lap thu nghiem tung model va phien ban API
    for model in models_to_try:
        urls_to_test = [
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}",
            f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={GEMINI_API_KEY}"
        ]
        
        for url in urls_to_test:
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    print(f"✅ AI ket noi thanh cong voi model: {model}")
                    return response.json()['candidates'][0]['content']['parts'][0]['text']
                else:
                    error_logs.append(f"[{model}] Loi {response.status_code}")
            except Exception as e:
                error_logs.append(f"[{model}] Loi mang: {e}")
                
    return f"Loi toan bo he thong AI. Chi tiet: {', '.join(error_logs)}"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }
    
    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            print("✅ Da gui bao cao thanh cong ve Telegram!")
        else:
            print(f"❌ LOI GUI TELEGRAM (Ma loi {res.status_code}): {res.text}")
    except Exception as e:
        print(f"❌ LOI KET NOI TELEGRAM: {e}")

if __name__ == "__main__":
    print("### BOT VERSION: v10-gemini-fallback-2026-07-16 ###")
    
    if not is_trading_day():
        print("Hom nay la cuoi tuan, thi truong dong cua. Dung bot.")
        exit(0)

    print("Dang quet du lieu thi truong...")
    market_data = fetch_market_and_fund_data()
    
    if market_data:
        print("Quet xong! AI dang tien hanh phan tich chuyen sau...")
        final_report = analyze_with_gemini(market_data)
        send_telegram(final_report)
    else:
        send_telegram("Canh bao: He thong khong the trich xuat du lieu tu Vnstock.")
