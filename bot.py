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
    "gemini-2.5-flash",            # UA TIEN #1: 2.5 flash - on dinh, output day du
    "gemini-2.5-pro",              # 2.5 pro - chat luong cao
    "gemini-flash-latest",         # alias flash
    "gemini-2.5-flash-lite",       # nhe
    "gemini-3.1-flash-lite",       # 3.x lite
    "gemini-3.5-flash",            # 3.x flash
    "gemini-pro-latest",           # alias pro
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
            fund_data_summary.append(f"- {fund_name}: khong co du lieu (da thu {DATA_SOURCES})")

    if not latest_index and not fund_data_summary:
        return None

    market_context = (
        f"Bao cao ngay: {end_date}\n"
        f"Chi so VNINDEX: {latest_index.get('close', 'N/A')} (Khoi luong: {latest_index.get('volume', 'N/A')})\n"
        f"Du lieu cac quy noi bat:\n" + "\n".join(fund_data_summary)
    )
    return market_context


# ======================= PHAN AI v13: FIX OUTPUT NGAN =======================

def _build_prompt(raw_data, retry=False):
    """Xay dung prompt cho AI.
    v13: them vi du cu the, yeu cau so luong dong cu the, ep format."""
    if retry:
        # Prompt don gian hon cho retry (phong tru prompt qua phuc tap gay "no idea")
        return f"""Phan tich ngan gon thi truong chung khoan Viet Nam ngay hom nay.

Du lieu:
{raw_data}
Hay viet 7-10 cau phan tich (tieng Viet CO dau, khong Markdown).
    return f"""Ban la chuyen gia phan tich tai chinh hang dau. Hay lap ban tin phan tich chi tiet cho thi truong chung khoan Viet Nam.

QUY TAC BAT BUOC:
1. Dau ra phai la TIENG VIET CO DAU chuan Unicode UTF-8.
2. Khong su dung Markdown: khong *, khong _, khong #, khong [], khong ```.
3. Viet tu 7 den 10 dong, moi dong la mot y phan tich doc lap.
4. Moi dong bat dau bang mot emoji.
5. Moi dong chi gom mot cau ngan gon, de doc tren Messenger, Zalo hoac Telegram.
6. Khong viet giai thich them truoc hoac sau ban tin.

CAU TRUC BAN TIN:
📈 Dong 1: Tong quan thi truong hom nay.
📊 Dong 2: Phan tich VN-Index (xu huong, bien dong).
💰 Dong 3: Phan tich quy FUEVFVND (dong tien, suc manh).
📉 Dong 4: Phan tich quy E1VFVN30 (so sanh voi FUEVFVND).
🏦 Dong 5: Phan tich quy FUESSVFL (xu huong rieng).
💵 Dong 6: Nhan dinh dong tien lon trong ngay.
⚠️ Dong 7: Canh bao rui ro (thanh khoan, bien dong, ap luc ban).
🎯 Dong 8: Goi y chien luoc ngan han cho nha dau tu.
⭐ Dong 9: Quy tiem nang nhat trong cac quy da phan tich va ly do.
📝 Dong 10: Ket luan tong the.

YEU CAU NOI DUNG:
- Phan tich dua tren so lieu duoc cung cap.
- Neu mot quy hoac chi so khong co du lieu thi ghi ro "Khong co du lieu de danh gia", khong duoc tu suy dien.
- Khong lap lai y giua cac dong.
- Khong viet chung chung, moi dong phai co nhan dinh cu the.
- Su dung cac gia tri va so lieu trong du lieu ben duoi neu co.

Du lieu thi truong:
{raw_data}

Chi tra ve ban tin, khong them bat ky giai thich nao."""

Hay bat dau viet ngay:"""


def _try_single_request(url, payload, headers, model_name, endpoint_label):
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            try:
                data = response.json()
                # Kiem tra co bi safety block khong
                if 'candidates' not in data or not data['candidates']:
                    # Lay finishReason neu co
                    return False, "empty_candidates_safety_blocked", response.status_code
                candidate = data['candidates'][0]
                # Kiem tra finishReason (STOP, MAX_TOKENS, SAFETY, RECITATION, OTHER)
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
    """Check neu response qua ngan (< 200 ky tu) - co the bi safety block hoac model loi."""
    if not text:
        return True
    cleaned = text.strip()
    return len(cleaned) < min_chars


def analyze_with_gemini(raw_data):
    if not GEMINI_API_KEY:
        return "Loi: Chua cau hinh GEMINI_API_KEY tren GitHub Secrets."

    headers = {"Content-Type": "application/json"}

    # ===== Prompt co ban =====
    prompt = _build_prompt(raw_data, retry=False)

    # ===== Payload v13: maxOutputTokens 4000 + safety BLOCK_NONE =====
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4000,   # TANG TU 800 -> 4000
            "topP": 0.95,
            "topK": 40
        },
        # ===== v13: TAT SAFETY FILTERS =====
        # Mac dinh Gemini co the block mot so category: HARASSMENT, HATE_SPEECH,
        # SEXUALLY_EXPLICIT, DANGEROUS_CONTENT. Dat BLOCK_NONE de dam bao
        # phan tich tai chinh (rui ro, canh bao) khong bi chan.
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

    # ===== Vong lap thu tung model =====
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
                # v13: Validate do dai response
                if _is_response_too_short(result):
                    print(f"  ⚠️ Response qua ngan ({len(result)} chars): '{result[:80]}...' - thu model khac")
                    error_logs.append(f"[{model}/{endpoint}] TOO_SHORT: '{result[:100]}'")
                    # KHONG break, thu model tiep theo (co the model nay bi loi)
                    break  # break inner loop (v1beta cung se ngan)
                else:
                    print(f"✅ AI ket noi thanh cong voi model: {model} (endpoint: {endpoint}), {len(result)} chars")
                    return result
            else:
                error_logs.append(f"[{model}/{endpoint}] {result}")
                if status == 404:
                    break

    # ===== v13: RETRY VOI PROMPT DON GIAN HON =====
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
        send_telegram("Canh bao: He thong khong the trich xuat du lieu tu Vnstock.")
