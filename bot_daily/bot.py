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

# ======================= DANH SACH MODEL (CAP NHAT 2026) =======================
# v13: Uu tien model 2.5 (on dinh) hon alias latest (co the la 3.x thinking model - giam tokens output)
MODELS_FALLBACK = [
    "gemini-pro-latest",           # alias pro
    "gemini-2.5-pro",              # 2.5 pro - chat luong cao
    "gemini-2.5-flash",            # UA TIEN #1: 2.5 flash - on dinh, output day du
    "gemini-flash-latest",         # alias flash
    "gemini-2.5-flash-lite",       # nhe
    "gemini-3.1-flash-lite",       # 3.x lite
    "gemini-3.5-flash",            # 3.x flash
]
# =============================================================================

# ======================= FIX v12: SYMBOL + SOURCE =======================
FUNDS_SYMBOLS = {
    'FUEVFVND': 'FUEVFVND',
    'E1VFVN30': 'E1VFVN30',
    'FUESSVFL': 'FUESSVFL',
}
DATA_SOURCES = ['KBS', 'VCI', 'MSN']
# ============================================================================


def is_trading_day():
    today = datetime.now().weekday()
    if today >= 5:
        return False
    return True


def _get_history(symbol, start_date, end_date):
    for source in DATA_SOURCES:
        try:
            q = Quote(symbol=symbol, source=source)
            df = q.history(start=start_date, end=end_date, interval='1D')
            if df is not None and not df.empty:
                df.columns = [str(c).lower() for c in df.columns]
                if 'close' in df.columns:
                    return df
        except Exception:
            continue
    print(f"⚠️ Khong the lay du lieu {symbol} tu cac nguon {DATA_SOURCES}.")
    return None


def fetch_market_and_fund_data():
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    latest_index = {}
    df_index = _get_history('VNINDEX', start_date, end_date)
    if df_index is not None and not df_index.empty:
        latest_index = df_index.iloc[-1].to_dict()

    fund_data_summary = []
    for fund_name, fund_symbol in FUNDS_SYMBOLS.items():
        df_fund = _get_history(fund_symbol, start_date, end_date)
        if df_fund is not None and not df_fund.empty:
            latest_price = df_fund.iloc[-1]['close']
            prev_price = df_fund.iloc[-2]['close'] if len(df_fund) > 1 else latest_price
            pct_change = ((latest_price - prev_price) / prev_price) * 100 if prev_price else 0
            fund_data_summary.append(f"- {fund_name}: {latest_price:,.2f} VND ({pct_change:+.2f}%)")
        else:
            # ĐÃ SỬA CÓ DẤU
            fund_data_summary.append(f"- {fund_name}: Không có dữ liệu (đã thử {DATA_SOURCES})")

    if not latest_index and not fund_data_summary:
        return None

    # ĐÃ SỬA CÓ DẤU ĐỂ AI KHÔNG BẮT CHƯỚC VĂN PHONG KHÔNG DẤU
    market_context = (
        f"Báo cáo ngày: {end_date}\n"
        f"Chỉ số VNINDEX: {latest_index.get('close', 'N/A')} (Khối lượng: {latest_index.get('volume', 'N/A')})\n"
        f"Dữ liệu các quỹ nổi bật:\n" + "\n".join(fund_data_summary)
    )
    return market_context


# ======================= PHAN AI v13: FIX OUTPUT NGAN =======================

def _build_prompt(raw_data, retry=False):
    """Xay dung prompt cho AI."""
    if retry:
        return f"""Phân tích ngắn gọn thị trường chứng khoán Việt Nam ngày hôm nay.

Dữ liệu:
{raw_data}

Hãy viết từ 7 đến 10 câu bằng tiếng Việt có dấu chuẩn Unicode UTF-8.
Mỗi câu trên một dòng.
Mỗi dòng bắt đầu bằng một emoji.
Không sử dụng Markdown.
Chỉ trả về bản tin."""
    
    return f"""Bạn là chuyên gia phân tích tài chính hàng đầu.

Hãy lập bản tin phân tích chi tiết cho thị trường chứng khoán Việt Nam.

QUY TẮC BẮT BUỘC:
1. Toàn bộ đầu ra phải là tiếng Việt có dấu chuẩn Unicode UTF-8.
2. Không được viết tiếng Việt không dấu.
3. Không sử dụng Markdown.
4. Viết từ 7 đến 10 dòng.
5. Mỗi dòng bắt đầu bằng một emoji.
6. Mỗi dòng chỉ gồm một câu.
7. Không thêm lời mở đầu hoặc kết thúc.

CẤU TRÚC:
📈 Dòng 1: Tổng quan thị trường.
📊 Dòng 2: Phân tích VN-Index.
💰 Dòng 3: Phân tích FUEVFVND.
📉 Dòng 4: Phân tích E1VFVN30.
🏦 Dòng 5: Phân tích FUESSVFL.
💵 Dòng 6: Đánh giá dòng tiền.
⚠️ Dòng 7: Cảnh báo rủi ro.
🎯 Dòng 8: Gợi ý chiến lược.
⭐ Dòng 9: Quỹ tiềm năng nhất.
📝 Dòng 10: Kết luận.

YÊU CẦU:
- Chỉ sử dụng dữ liệu được cung cấp.
- Không tự suy diễn.
- Không lặp ý.
- Nếu thiếu dữ liệu thì ghi rõ "Không có dữ liệu để đánh giá".

Dữ liệu thị trường:
{raw_data}

Chỉ trả về bản tin, không thêm bất kỳ giải thích nào.
Hãy bắt đầu viết ngay:"""


def _try_single_request(url, payload, headers, model_name, endpoint_label):
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            try:
                data = response.json()
                if 'candidates' not in data or not data['candidates']:
                    return False, "empty_candidates_safety_blocked", response.status_code
                candidate = data['candidates'][0]
                finish_reason = candidate.get('finishReason', 'UNKNOWN')
                if 'content' not in candidate or 'parts' not in candidate.get('content', {}):
                    return False, f"no_content_finish_{finish_reason}", response.status_code
                text = candidate['content']['parts'][0]['text']
                return True, text, 200
            except (KeyError, IndexError, ValueError) as parse_err:
                return False, f"parse_error:{parse_err}", response.status_code
        else:
            try:
                err_body = response.json()
                err_msg = err_body.get('error', {}).get('message', response.text[:200])
            except Exception:
                err_msg = response.text[:200]
            return False, f"http_{response.status_code}:{err_msg}", response.status_code
    except requests.exceptions.Timeout:
        return False, "timeout", 0
    except requests.exceptions.ConnectionError as e:
        return False, f"connection_error:{str(e)[:100]}", 0
    except Exception as e:
        return False, f"exception:{str(e)[:100]}", 0


def _discover_available_models():
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        models = data.get('models', [])
        valid = []
        for m in models:
            name = m.get('name', '')
            methods = m.get('supportedGenerationMethods', []) or m.get('capabilities', [])
            if not name:
                continue
            if methods and 'generateContent' not in methods:
                continue
            short = name.split('/')[-1]
            skip_keywords = ['embedding', 'image', 'imagen', 'tts', 'robotics', 'veo',
                             'lyria', 'nano-banana', 'aqa', 'computer-use']
            if any(k in short.lower() for k in skip_keywords):
                continue
            valid.append(short)
        return valid
    except Exception:
        return None


def _is_response_too_short(text, min_chars=200):
    if not text:
        return True
    cleaned = text.strip()
    return len(cleaned) < min_chars


def analyze_with_gemini(raw_data):
    if not GEMINI_API_KEY:
        return "Lỗi: Chưa cấu hình GEMINI_API_KEY trên GitHub Secrets."

    headers = {"Content-Type": "application/json"}

    prompt = _build_prompt(raw_data, retry=False)

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4000,
            "topP": 0.95,
            "topK": 40
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    }

    print("Dang kiem tra danh sach model kha dung cho API key...")
    discovered = _discover_available_models()

    models_to_try = []
    if discovered:
        print(f"📋 listModels tra ve {len(discovered)} model kha dung.")
        latest_aliases = [m for m in discovered if m.endswith('-latest')]
        others = [m for m in discovered if not m.endswith('-latest')]
        models_to_try.extend(latest_aliases)
        models_to_try.extend(others)
        for m in MODELS_FALLBACK:
            if m not in models_to_try:
                models_to_try.append(m)
    else:
        print("⚠️ Khong the listModels, su dung fallback list cu.")
        models_to_try = list(MODELS_FALLBACK)

    error_logs = []
    for model in models_to_try:
        if model.startswith('gemini-1.5') or model == 'gemini-pro' or model == 'gemini-1.0-pro':
            continue

        urls_to_test = [
            (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}", "v1beta"),
            (f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={GEMINI_API_KEY}", "v1"),
        ]

        for url, endpoint in urls_to_test:
            print(f"  -> Thu [{model}] tren {endpoint}...")
            ok, result, status = _try_single_request(url, payload, headers, model, endpoint)
            if ok:
                if _is_response_too_short(result):
                    print(f"  ⚠️ Response qua ngan ({len(result)} chars) - thu model khac")
                    error_logs.append(f"[{model}/{endpoint}] TOO_SHORT: '{result[:100]}'")
                    break
                else:
                    print(f"✅ AI ket noi thanh cong voi model: {model} (endpoint: {endpoint}), {len(result)} chars")
                    return result
            else:
                error_logs.append(f"[{model}/{endpoint}] {result}")
                if status == 404:
                    break

    print("⚠️ Tat ca model deu cho output ngan hoac loi. Thu lai voi prompt don gian...")
    simple_prompt = _build_prompt(raw_data, retry=True)
    payload_simple = {
        "contents": [{"parts": [{"text": simple_prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4000
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    }

    for model in models_to_try:
        if model.startswith('gemini-1.5') or model == 'gemini-pro' or model == 'gemini-1.0-pro':
            continue
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            response = requests.post(url, json=payload_simple, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('candidates'):
                    text = data['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    if not _is_response_too_short(text):
                        print(f"✅ Retry thanh cong voi [{model}], {len(text)} chars")
                        return text
        except Exception:
            continue

    # ĐÃ SỬA CÓ DẤU
    return f"Lỗi toàn bộ hệ thống AI. Chi tiết: {', '.join(error_logs)}"


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
    print("### BOT VERSION: v13-output-length-fix-2026-07-16 ###")

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
        # ĐÃ SỬA CÓ DẤU
        send_telegram("Cảnh báo: Hệ thống không thể trích xuất dữ liệu từ Vnstock.")
