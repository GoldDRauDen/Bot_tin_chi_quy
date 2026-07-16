import os
import requests
import pandas as pd
from datetime import datetime, timedelta
# Import dung chuan vnstock.api de sach log va khong bi spam canh bao
from vnstock.api.quote import Quote 

# ======================= CAU HINH BAO MAT =======================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')    
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
# ===============================================================

def is_trading_day():
    """Kiem tra xem hom nay co phai la ngay giao dich khong (Bo qua Thu 7, Chu Nhat)"""
    today = datetime.now().weekday()
    if today >= 5: # 5 la Thu 7, 6 la Chu Nhat
        return False
    return True

def _get_history(symbol, start_date, end_date):
    """
    Lay du lieu dung chuan vnstock.api.
    Su dung nguon VCI theo dung thong bao va huong dan tu Vnstock V4 core.
    """
    try:
        # Ap dung cu phap New tuong thich 100% voi ban open-source hien tai
        q = Quote(symbol=symbol, source='VCI')
        df = q.history(start=start_date, end=end_date, interval='1D')
        if df is not None and not df.empty:
            df.columns = [str(c).lower() for c in df.columns]
            return df
    except Exception as e:
        print(f"Loi khi tai ma {symbol}: {e}")
    return None

def fetch_market_and_fund_data():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    # 1. Lay du lieu VNINDEX
    latest_index = {}
    df_index = _get_history('VNINDEX', start_date, end_date)
    if df_index is not None and not df_index.empty:
        latest_index = df_index.iloc[-1].to_dict()

    # 2. Lay du lieu Quy ETF
    funds = ['FUEVNVND', 'E1VFVN30', 'FUESSVFL']
    fund_data_summary = []

    for fund in funds:
        df_fund = _get_history(fund, start_date, end_date)
        if df_fund is not None and not df_fund.empty:
            latest_price = df_fund.iloc[-1]['close']
            prev_price = df_fund.iloc[-2]['close'] if len(df_fund) > 1 else latest_price
            pct_change = ((latest_price - prev_price) / prev_price) * 100 if prev_price else 0
            fund_data_summary.append(f"• {fund}: {latest_price:,.0f} VND ({pct_change:+.2f}%)")

    if not latest_index and not fund_data_summary:
        return None

    market_context = (
        f"Bao cao ngay: {end_date}\n"
        f"Chi so VNINDEX: {latest_index.get('close', 'N/A')} (Khoi luong: {latest_index.get('volume', 'N/A')})\n"
        f"Du lieu cac quy noi bat:\n" + ("\n".join(fund_data_summary) if fund_data_summary else "Khong co du lieu quy.")
    )
    return market_context

def analyze_with_deepseek(raw_data):
    if not DEEPSEEK_API_KEY:
        return "Loi: Chua cau hinh API Key cho DeepSeek."

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""Ban la giam doc khoi phan tich quy dau tu.
Dua tren du lieu thuc te duoi day, hay lap ban tin phan tich sang nay (7-10 dong).

YEU CAU BAT BUOC: Toan bo cau tra loi cua ban phai duoc viet bang TIENG VIET KHONG DAU (loai bo hoan toan dau tieng Viet) de tranh loi font.

Noi dung can co:
- Danh gia nhanh xu huong VN-Index.
- Phan tich dong luc cua cac quy ETF (FUEVNVND, E1VFVN30...). 
- Canh bao rui ro va chi ra quy tiem nang nhat.
- Dung dinh dang Markdown va cac emoji phu hop.

Du lieu:
{raw_data}"""

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 800
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"Loi API DeepSeek (Ma loi: {response.status_code})"
    except Exception as e:
        return f"Loi ket noi AI: {e}"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload, timeout=15)

if __name__ == "__main__":
    print("### BOT VERSION: v6-clean-api-2026-07-16 ###")
    
    if not is_trading_day():
        print("Hom nay la cuoi tuan, thi truong dong cua. Dung bot.")
        exit(0)

    print("Dang quet du lieu thi truong...")
    market_data = fetch_market_and_fund_data()
    
    if market_data:
        print("AI dang tien hanh phan tich chuyen sau...")
        final_report = analyze_with_deepseek(market_data)
        send_telegram(final_report)
        print("Da gui bao cao thanh cong ve Telegram!")
    else:
        send_telegram("Canh bao: He thong khong the trich xuat du lieu tu Vnstock.")
