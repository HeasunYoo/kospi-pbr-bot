import os
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import requests
import holidays  # ✅ 공휴일 체크용
from pykrx import stock as pkstock

MARKET = "KOSPI"
INDEX_NAME = "코스피"

LOW = 0.84
HIGH = 1.60

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def two(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "N/A"
    return f"{float(x):.2f}"

def fmt_date_only(d):
    """YYYY-MM-DD (시간 제거)"""
    # pykrx index가 'YYYYMMDD' 문자열일 때
    s = str(d)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    # Timestamp/Datetime일 때
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

def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("GitHub Secrets에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID를 설정해야 합니다.")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    r.raise_for_status()

def main():
    # ✅ 공휴일/주말이면 아예 전송하지 않음
    today = datetime.now().date()
    if not is_korea_business_day(today):
        print("Skip: weekend/holiday in Korea")
        return

    # 지수 ticker 찾기
    itickers = pkstock.get_index_ticker_list(market=MARKET)
    i2name = {t: f"{MARKET}:{pkstock.get_index_ticker_name(t)}" for t in itickers}
    name2i = {v: k for k, v in i2name.items()}
    iticker = name2i[f"{MARKET}:{INDEX_NAME}"]

    # 최근 10년 조회
    from_date = (datetime.today() - timedelta(days=365 * 10)).strftime("%Y%m%d")
    to_date = datetime.today().strftime("%Y%m%d")

    df = pkstock.get_index_fundamental(from_date, to_date, iticker)[["종가", "PBR"]].copy()
    df.replace(0, np.nan, inplace=True)

    last_date = df.index[-1]
    last_close = df["종가"].iloc[-1]
    last_pbr = df["PBR"].iloc[-1]

    pbr_series = df["PBR"].dropna()
    avg10 = pbr_series.mean()
    min10 = pbr_series.min()
    max10 = pbr_series.max()
    dmin = pbr_series.idxmin()
    dmax = pbr_series.idxmax()

    # ✅ 이모지 + 문구 변경(요구사항 1,3)
    msg = (
        "📌 <KOSPI PBR 알림>\n\n"
        f"📅 기준일: {fmt_date_only(last_date)}\n"
        f"📈 종가: {last_close}\n"
        f"🏷️ PBR: {two(last_pbr)}\n\n"
        "🧾 <최근 10년 PBR>\n"
        f"📊 평균: {two(avg10)}\n"
        f"🔻 최저: {two(min10)} ({fmt_date_only(dmin)})\n"
        f"🔺 최고: {two(max10)} ({fmt_date_only(dmax)})\n\n"
        "✅ 조건: 0.84 이하 or 1.6 이상\n"
    )

    # 조건 충족 시 추가 알림
    if last_pbr == last_pbr and (float(last_pbr) <= LOW or float(last_pbr) >= HIGH):
        msg += f"\n🚨 조건 충족! 현재 PBR={two(last_pbr)}"

    send_telegram(msg)

if __name__ == "__main__":
    main()
