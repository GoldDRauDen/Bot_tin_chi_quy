import os
import traceback
import requests
import pandas as pd
from datetime import datetime, timedelta
# Su dung kien truc Unified UI moi cua Vnstock v4
from vnstock import Market 

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')    
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')

def _get_history(symbol, start_date, end_date):
    """
    Lay du lieu bang lop Market() cua Vnstock 4.x.
    He thong se tu dong chon nguon data tot nhat.
    """
    market = Market()
    try:
        # market.equity.ohlcv ho tro ca co phieu, chung chi quy va index
        df = market.equity.ohlcv(symbol=symbol, start=start_date, end=end_date)
        if df is not None and not df.empty:
            df.columns = [str(c).lower() for c in df.columns]
            return df
    except Exception as e:
        print(f"Loi tai du lieu {symbol}: {e}")
    return None

def fetch_market_and_fund_data():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    # 1. Lay du lieu VNINDEX
    latest_index = {}
    df_index = _get_history('VNINDEX', start_date, end_date)
    if df_index is not None and not df_index.empty:
        latest_index = df_index.iloc[-1].to_dict()
    else:
        print("Canh bao: Khong lay duoc du lieu VNINDEX.")

    # 2. Lay du lieu cac Quy ETF
    funds = ['FUEVNVND', 'E1VFVN30', 'FUESSVFL']
    fund_data_summary = []

    for fund in funds:
        df_fund = _get_history(fund, start_date, end_date)
        if df_fund is not None and not df_fund.empty:
            latest_price = df_fund.iloc[-1]['close']
            prev_price = df_fund.iloc[-2]['close'] if len(df_fund) > 1 else latest_price
            pct_change = ((latest_price - prev_price) / prev_price) * 100 if prev_price else 0
            fund_data_summary.append(f"• {fund}: {latest_price:,.0f}d ({pct_change:+.2f}%)")
        else:
            print(f"Canh bao: Khong lay duoc du lieu cho {fund}.")

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

    # Cap nhat prompt de DeepSeek tra ve bao cao hoan toan khong co dau
    prompt = f"""Ban la giam doc khoi phan tich quy dau tu.
Dua tren du lieu thuc te duoi day, lap ban tin phan tich (7-10 dong).

YEU CAU BAT BUOC: Toan bo cau tra loi phai viet bang tieng Viet khong dau (loai bo hoan toan dau tieng Viet) de dam bao khong bi loi font tren cac thiet bi. Dung dinh dang Markdown va cac emoji phu hop.

- Danh gia nhanh xu huong VN-Index.
- Phan tich dong luc cua cac quy ETF (FUEVNVND, E1VFVN30...). 
- Canh bao rui ro va chi ra quy tiem nang nhat.

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
        return f"Loi ket noi he thong AI: {e}"

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
    print("### BOT VERSION: v3-vnstock-unified-2026-07-15 ###")
    print("Dang quet du lieu thi truong...")
    market_data = fetch_market_and_fund_data()
    
    if market_data:
        print("AI dang tien hanh phan tich chuyen sau...")
        final_report = analyze_with_deepseek(market_data)
        send_telegram(final_report)
        print("Da gui bao cao thanh cong ve Telegram!")
    else:
        send_telegram("⚠️ He thong cot loi gap su co: Khong the trich xuat du lieu tu Vnstock.")
