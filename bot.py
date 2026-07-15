import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

# ======================= CẤU HÌNH BẢO MẬT =======================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
# ===============================================================

def get_historical_data_robust(symbol, start_date, end_date):
    """
    Hàm lấy dữ liệu thích ứng thông minh (Universal Wrapper).
    Tự động thử các phiên bản Vnstock khác nhau, nếu lỗi thì gọi thẳng API TCBS.
    """
    # --- TẦNG 1: Thử theo chuẩn Vnstock V3 mới nhất ---
    try:
        from vnstock import vnstock
        vs = vnstock()
        df = vs.stock(symbol=symbol, source='TCBS').trading.historical_data(start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            print(f"[{symbol}] Lấy dữ liệu thành công bằng Vnstock V3.")
            return df
    except Exception:
        pass

    try:
        from vnstock import Vnstock
        vs = Vnstock()
        df = vs.stock(symbol=symbol, source='TCBS').trading.historical_data(start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            print(f"[{symbol}] Lấy dữ liệu thành công bằng Vnstock V3 (Alt).")
            return df
    except Exception:
        pass

    # --- TẦNG 2: Thử theo chuẩn Vnstock Legacy (v0.2.x) ---
    try:
        import vnstock as vs_legacy
        if hasattr(vs_legacy, 'stock_historical_data'):
            df = vs_legacy.stock_historical_data(symbol=symbol, start_date=start_date, end_date=end_date, source='TCBS')
            if df is not None and not df.empty:
                print(f"[{symbol}] Lấy dữ liệu thành công bằng Vnstock Legacy.")
                return df
    except Exception:
        pass

    # --- TẦNG 3 (Bất tử): Tự gọi thẳng API công khai của TCBS (Không cần thư viện) ---
    try:
        # Chuyển đổi ngày sang UNIX Timestamp (giây)
        from_ts = int(time.mktime(time.strptime(start_date, "%Y-%m-%d")))
        to_ts = int(time.mktime(time.strptime(end_date, "%Y-%m-%d")))
        
        url = f"https://apipublish.tcbs.com.vn/api/v1/ticker-joint/history?ticker={symbol}&from={from_ts}&to={to_ts}&resolution=D"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'c' in data and len(data['c']) > 0:
                # Tạo DataFrame từ cấu trúc JSON của TradingView UDF từ TCBS
                df = pd.DataFrame({
                    'time': [datetime.fromtimestamp(t).strftime('%Y-%m-%d') for t in data['t']],
                    'open': data['o'],
                    'high': data['h'],
                    'low': data['l'],
                    'close': data['c'],
                    'volume': data['v']
                })
                print(f"[{symbol}] Lấy dữ liệu thành công trực tiếp từ API gốc TCBS.")
                return df
    except Exception as e:
        print(f"Lỗi khi cố gắng gọi API trực tiếp cho {symbol}: {e}")

    return pd.DataFrame()


def fetch_market_and_fund_data():
    """Hợp nhất dữ liệu thị trường sử dụng hàm Robust Wrapper"""
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        
        # 1. Lấy dữ liệu VN-Index
        df_index = get_historical_data_robust('VNINDEX', start_date, end_date)
        if df_index.empty:
            raise ValueError("Không thể lấy dữ liệu VNINDEX từ bất kỳ nguồn nào.")
            
        latest_index = df_index.iloc[-1].to_dict()

        # 2. Lấy dữ liệu các Chứng chỉ quỹ / ETF lớn
        funds = ['FUEVNVND', 'E1VFVN30', 'FUESSVFL']
        fund_data_summary = []
        
        for fund in funds:
            df_fund = get_historical_data_robust(fund, start_date, end_date)
            if not df_fund.empty:
                latest_price = df_fund.iloc[-1]['close']
                prev_price = df_fund.iloc[-2]['close'] if len(df_fund) > 1 else latest_price
                pct_change = ((latest_price - prev_price) / prev_price) * 100
                fund_data_summary.append(f"• {fund}: {latest_price:,.0f}đ ({pct_change:+.2f}%)")
            else:
                fund_data_summary.append(f"• {fund}: Không có dữ liệu")
        
        market_context = (
            f"Báo cáo ngày: {end_date}\n"
            f"Chỉ số VNINDEX: {latest_index.get('close', 'N/A')} (Khối lượng: {latest_index.get('volume', 'N/A')})\n"
            f"Dữ liệu các quỹ nổi bật:\n" + "\n".join(fund_data_summary)
        )
        return market_context
        
    except Exception as e:
        print(f"Lỗi hệ thống thu thập dữ liệu: {e}")
        return None


def analyze_with_deepseek(raw_data):
    """Đưa dữ liệu vào DeepSeek"""
    if not DEEPSEEK_API_KEY:
        return "Lỗi: Chưa cấu hình API Key cho DeepSeek."

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""Bạn là một giám đốc khối phân tích quỹ đầu tư thuộc top 0.1% thị trường Việt Nam.
Dựa trên dữ liệu tài chính thực tế dưới đây, hãy lập bản tin phân tích sáng nay (7-10 dòng):
- Đánh giá nhanh xu hướng VN-Index và tác động đến các nhóm chứng chỉ quỹ.
- Phân tích động lực tăng/giảm của các quỹ ETF (FUEVNVND, E1VFVN30...). 
- Cảnh báo rủi ro (lệch giá NAV, dòng vốn ngoại rút ròng nếu có) và chỉ ra quỹ tiềm năng nhất hôm nay.

Yêu cầu: Viết chuyên nghiệp, sắc bén, dùng định dạng Markdown và các emoji 📊📈📉📌 phù hợp. Không dài dòng văn tự.

Dữ liệu đầu vào:
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
            return f"Lỗi API DeepSeek (Mã lỗi: {response.status_code})"
    except Exception as e:
        return f"Lỗi kết nối hệ thống AI: {e}"


def send_telegram(text):
    """Gửi Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Không thể gửi tin nhắn Telegram: {e}")


if __name__ == "__main__":
    print("Đang quét dữ liệu thị trường...")
    market_data = fetch_market_and_fund_data()
    
    if market_data:
        print("AI đang tiến hành phân tích chuyên sâu...")
        final_report = analyze_with_deepseek(market_data)
        send_telegram(final_report)
        print("Đã gửi báo cáo thành công về Telegram!")
    else:
        send_telegram("⚠️ Hệ thống cốt lõi lỗi: Không thể trích xuất dữ liệu.")
