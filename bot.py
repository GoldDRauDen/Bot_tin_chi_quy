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
# Thu tu uu tien: alias on dinh nhat -> GA 2.5 -> GA 3.x
# - google luon cap nhat alias "*-latest" tro ve model GA moi nhat
# - gemini-1.5* da shut down -> KHONG dung
# - gemini-pro (1.0) khong con duoc ho tro -> KHONG dung
MODELS_FALLBACK = [
    "gemini-flash-latest",         # alias -> tro ve GA flash moi nhat (uu tien 1)
    "gemini-2.5-flash",            # GA, on dinh, free tier friendly
    "gemini-2.5-pro",              # GA, on dinh
    "gemini-2.5-flash-lite",       # nhe, re, free tier
    "gemini-3.1-flash-lite",       # GA moi (May 2026)
    "gemini-3.5-flash",            # GA moi nhat (May 2026)
    "gemini-pro-latest",           # alias -> tro ve GA pro moi nhat
]
# =============================================================================


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


def _try_single_request(url, payload, headers, model_name, endpoint_label):
    """Thu mot cuoc goi don le, tra ve (ok, text, status_code)."""
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            try:
                data = response.json()
                text = data['candidates'][0]['content']['parts'][0]['text']
                return True, text, 200
            except (KeyError, IndexError, ValueError) as parse_err:
                return False, f"parse_error:{parse_err}", response.status_code
        else:
            # Lay chi tiet loi tu response neu co
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
    """Tu dong goi listModels de lay danh sach model con hoat dong cho key nay.
    Tra ve list string model_id (uu tien GA + generateContent support).
    Rat huu ich khi key free-tier chi expose mot subset model."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            print(f"⚠️ listModels that bai (HTTP {r.status_code})")
            return None
        data = r.json()
        models = data.get('models', [])
        # Loc: chi lay model ho tro generateContent va KHONG PHAI embedding/image/audio
        valid = []
        for m in models:
            name = m.get('name', '')  # dang "models/gemini-xxx"
            methods = m.get('supportedGenerationMethods', []) or m.get('capabilities', [])
            if not name:
                continue
            if methods and 'generateContent' not in methods:
                continue
            # bo qua model embedding/image/audio/robotics
            short = name.split('/')[-1]
            skip_keywords = ['embedding', 'image', 'imagen', 'tts', 'robotics', 'veo',
                             'lyria', 'nano-banana', 'aqa', 'computer-use']
            if any(k in short.lower() for k in skip_keywords):
                continue
            valid.append(short)
        return valid
    except Exception as e:
        print(f"⚠️ listModels exception: {e}")
        return None


def analyze_with_gemini(raw_data):
    if not GEMINI_API_KEY:
        return "Loi: Chua cau hinh GEMINI_API_KEY tren GitHub Secrets."

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
    headers = {"Content-Type": "application/json"}

    # ===== GIAI DOAN 1: Thu listModels de uu tien model con song =====
    # Neu key bi gioi han (free tier thuong chi expose 1 subset) thi listModels se cho biet chinh xac
    print("Dang kiem tra danh sach model kha dung cho API key...")
    discovered = _discover_available_models()

    # Sap xep model can thu: discovered (neu co) → fallback list
    models_to_try = []
    if discovered:
        print(f"📋 listModels tra ve {len(discovered)} model kha dung.")
        # uu tien alias *-latest, sau do GA, roi them fallback list
        latest_aliases = [m for m in discovered if m.endswith('-latest')]
        others = [m for m in discovered if not m.endswith('-latest')]
        models_to_try.extend(latest_aliases)
        models_to_try.extend(others)
        # them nhung model trong MODELS_FALLBACK chua co (de co nhieu lua chon)
        for m in MODELS_FALLBACK:
            if m not in models_to_try:
                models_to_try.append(m)
    else:
        print("⚠️ Khong the listModels, su dung fallback list cu.")
        models_to_try = list(MODELS_FALLBACK)

    # ===== GIAI DOAN 2: Vong lap thu tung model voi ca v1beta va v1 =====
    error_logs = []
    for model in models_to_try:
        # Bo qua model 1.5 (da shut down) va gemini-pro (1.0)
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
                print(f"✅ AI ket noi thanh cong voi model: {model} (endpoint: {endpoint})")
                return result
            else:
                # Neu 404 -> bo qua, khong can log noi endpoint khac cung 404
                error_logs.append(f"[{model}/{endpoint}] {result}")
                if status == 404:
                    # 404 o v1beta cung se 404 o v1 -> break de khong spam
                    break

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
    print("### BOT VERSION: v11-gemini-fallback-2026-07-16 ###")

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
