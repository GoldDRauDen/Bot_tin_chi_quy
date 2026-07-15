import os
import traceback
import requests
import pandas as pd
from datetime import datetime, timedelta
# Import thư viện vnstock thế hệ mới (Unified UI - vnstock >= 3.x/4.x)
from vnstock import Quote

# ======================= CẤU HÌNH BẢO MẬT =======================
# Khuyên dùng: Lưu vào Environment Variables. Điền token của bạn nếu test nhanh.
# CHỈ ĐỌC TỪ BIẾN MÔI TRƯỜNG - KHÔNG ĐỂ LỘ KEY TRÊN GITHUB
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')    
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')

# ===============================================================

def _get_history(symbol, start_date, end_date, source='KBS'):
    """
    Hàm helper gọi API mới của vnstock (Quote.history).
    Dùng nguồn KBS vì đây là nguồn được vnstock khuyến nghị chạy ổn định
    trên môi trường server/cloud (như GitHub Actions), ít bị chặn IP hơn VCI.
    Chuẩn hoá tên cột về chữ thường để tránh lỗi KeyError nếu API đổi casing.
    """
    quote = Quote(symbol=symbol, source=source)
    df = quote.history(start=start_date, end=end_date, interval='1D')
    if df is not None and not df.empty:
        df.columns = [str(c).lower() for c in df.columns]
    return df


def fetch_market_and_fund_data():
    """Lấy dữ liệu thật từ thị trường và các quỹ thông qua Vnstock (API hợp nhất - Unified UI)"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    # 1. Lấy dữ liệu VN-Index
    latest_index = {}
    try:
        df_index = _get_history('VNINDEX', start_date, end_date)
        if df_index is not None and not df_index.empty:
            latest_index = df_index.iloc[-1].to_dict()
        else:
            print("Cảnh báo: Không lấy được dữ liệu VNINDEX (DataFrame rỗng).")
    except Exception:
        print("Lỗi khi lấy dữ liệu VNINDEX:")
        print(traceback.format_exc())

    # 2. Lấy dữ liệu các Chứng chỉ quỹ / ETF lớn (Ví dụ: FUEVNVND, E1VFVN30)
    funds = ['FUEVNVND', 'E1VFVN30', 'FUESSVFL']
    fund_data_summary = []

    for fund in funds:
        try:
            df_fund = _get_history(fund, start_date, end_date)
            if df_fund is not None and not df_fund.empty:
                latest_price = df_fund.iloc[-1]['close']
                prev_price = df_fund.iloc[-2]['close'] if len(df_fund) > 1 else latest_price
                pct_change = ((latest_price - prev_price) / prev_price) * 100 if prev_price else 0
                fund_data_summary.append(f"• {fund}: {latest_price:,.0f}đ ({pct_change:+.2f}%)")
            else:
                print(f"Cảnh báo: Không lấy được dữ liệu cho {fund} (DataFrame rỗng).")
        except Exception:
            print(f"Lỗi khi lấy dữ liệu quỹ {fund}:")
            print(traceback.format_exc())

    # Nếu không lấy được cả VNINDEX lẫn bất kỳ quỹ nào -> coi như thất bại toàn phần
    if not latest_index and not fund_data_summary:
        return None

    market_context = (
        f"Báo cáo ngày: {end_date}\n"
        f"Chỉ số VNINDEX: {latest_index.get('close', 'N/A')} (Khối lượng: {latest_index.get('volume', 'N/A')})\n"
        f"Dữ liệu các quỹ nổi bật:\n" + ("\n".join(fund_data_summary) if fund_data_summary else "Không có dữ liệu quỹ.")
    )
    return market_context

def analyze_with_deepseek(raw_data):
    """Đưa dữ liệu thật vào DeepSeek để phân tích theo tư duy 0.1%"""
    if not DEEPSEEK_API_KEY:
        return "Lỗi: Chưa cấu hình API Key cho DeepSeek."

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    # Prompt nâng cấp bắt buộc AI tư duy theo dòng tiền và độ lệch giá
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
        "temperature": 0.2, # Giảm sáng tạo để AI tập trung vào logic tài chính số liệu
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
    """Gửi báo cáo phân tích chất lượng cao về Telegram cá nhân"""
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
    print("### BOT VERSION: v2-vnstock-unified-2026-07-15 ###")
    print("Đang quét dữ liệu thị trường...")
    market_data = fetch_market_and_fund_data()
    
    if market_data:
        print("AI đang tiến hành phân tích chuyên sâu...")
        final_report = analyze_with_deepseek(market_data)
        send_telegram(final_report)
        print("Đã gửi báo cáo thành công về Telegram!")
    else:
        send_telegram("⚠️ Hệ thống cốt lõi lỗi: Không thể trích xuất dữ liệu từ Vnstock.")