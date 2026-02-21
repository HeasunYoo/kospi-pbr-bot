import os
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import requests
import holidays
from pykrx import stock as pkstock

MARKET = "KOSPI"
INDEX_NAME = "코스피"

LOW = 0.84
HIGH = 1.60

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


def two(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "N/A"
    return f"{float(x):.2f}"


def fmt_date_only(d) -> str:
    """YYYY-MM-DD (시간 제거)"""
    s = str(d)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    try:
        return pd.Timestamp(d).date().isoformat()
    except Exception:
        return s


def is_korea_business_day(today: date) -> bool:
    """월~금 + 한국 공휴일 제외"""
    if today.weekday() >= 5:  # 5=토, 6=일
        return False
    kr_holidays = holidays.KR(years=today.year)
    return today not in kr_holidays


def now_kst() -> datetime:
    """GitHub Actions는 보통 UTC이므로 KST로 변환"""
    return datetime.utcnow() + timedelta(hours=9)


def run_label(kst_dt: datetime) -> str:
    hhmm = kst_dt.strftime("%H:%M")
    if kst_dt.hour < 12:
        return f"🌅 오전 알림 ({hhmm} KST)"
    return f"🌇 오후 알림 ({hhmm} KST)"


def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("GitHub Secrets에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 설정해야 합니다.")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    r.raise_for_status()


def main():
    kst = now_kst()
    today = kst.date()
    force = os.getenv("FORCE_SEND", "0") == "1"  # ✅ 테스트용(주말/공휴일에도 발송)

    if (not force) and (not is_korea_business_day(today)):
        print("Skip: weekend/holiday in Korea")
        return

    # 1) 지수 ticker 찾기
    itickers = pkstock.get_index_ticker_list(market=MARKET)
    i2name = {t: f"{MARKET}:{pkstock.get_index_ticker_name(t)}" for t in itickers}
    name2i = {v: k for k, v in i2name.items()}
    key = f"{MARKET}:{INDEX_NAME}"
    if key not in name2i:
        candidates = [k for k in name2i.keys() if INDEX_NAME in k]
        raise ValueError(f"지수명을 못 찾았습니다: {key}\n후보: {candidates[:30]}")
    iticker = name2i[key]

    # 2) 최근 10년 조회
    from_date = (datetime.today() - timedelta(days=365 * 10 + 10)).strftime("%Y%m%d")
    to_date = datetime.today().strftime("%Y%m%d")

    df = pkstock.get_index_fundamental(from_date, to_date, iticker)[["종가", "PBR"]].copy()
    df.replace(0, np.nan, inplace=True)

    last_date = df.index[-1]
    last_close = df["종가"].iloc[-1]
    last_pbr = df["PBR"].iloc[-1]

    pbr_series = df["PBR"].dropna()
    avg10 = float(pbr_series.mean())
    min10 = float(pbr_series.min())
    max10 = float(pbr_series.max())
    dmin = pbr_series.idxmin()
    dmax = pbr_series.idxmax()

    header = run_label(kst)

    msg = (
        f"{header}\n"
        "📌 <KOSPI PBR>\n\n"
        f"📅 기준일: {fmt_date_only(last_date)}\n"
        f"📈 종가: {last_close}\n"
        f"🏷️ PBR: {two(last_pbr)}\n\n"
        "🧾 <최근 10년 PBR>\n"
        f"📊 평균: {two(avg10)}\n"
        f"🔻 최저: {two(min10)} ({fmt_date_only(dmin)})\n"
        f"🔺 최고: {two(max10)} ({fmt_date_only(dmax)})\n\n"
        "✅ 조건: 0.84 이하 or 1.6 이상\n"
    )

    if last_pbr == last_pbr and (float(last_pbr) <= LOW or float(last_pbr) >= HIGH):
        msg += f"\n🚨🚨 조건 충족! 현재 PBR={two(last_pbr)} 🚨🚨"

    send_telegram(msg)


if __name__ == "__main__":
    main()
