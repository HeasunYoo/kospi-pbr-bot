import os
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import requests
import holidays
from pykrx import stock as pkstock

MARKET = "KOSPI"
INDEX_NAME = "코스피"

LOW = 0.84  # 감시 기준

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


def two(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "N/A"
    return f"{float(x):.2f}"


def fmt_date_only(d) -> str:
    s = str(d)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    try:
        return pd.Timestamp(d).date().isoformat()
    except Exception:
        return s


def is_korea_business_day(today: date) -> bool:
    if today.weekday() >= 5:
        return False
    kr_holidays = holidays.KR(years=today.year)
    return today not in kr_holidays


def now_kst() -> datetime:
    return datetime.now(datetime.UTC) + timedelta(hours=9)


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


def get_index_ticker(market: str, index_name_kor: str) -> str:
    itickers = pkstock.get_index_ticker_list(market=market)
    i2name = {t: f"{market}:{pkstock.get_index_ticker_name(t)}" for t in itickers}
    name2i = {v: k for k, v in i2name.items()}
    return name2i[f"{market}:{index_name_kor}"]


def main():
    kst = now_kst()
    today = kst.date()
    force = os.getenv("FORCE_SEND", "0") == "1"

    if (not force) and (not is_korea_business_day(today)):
        print("Skip: weekend/holiday in Korea")
        return

    iticker = get_index_ticker(MARKET, INDEX_NAME)

    from_date = (datetime.today() - timedelta(days=365 * 10 + 10)).strftime("%Y%m%d")
    to_date = datetime.today().strftime("%Y%m%d")

    df = pkstock.get_index_fundamental(from_date, to_date, iticker)[["종가", "PBR"]].copy()
    df.replace(0, np.nan, inplace=True)

    last_date = df.index[-1]
    last_close = float(df["종가"].iloc[-1])
    last_pbr = float(df["PBR"].iloc[-1])

    pbr_series = df["PBR"].dropna()
    avg10 = float(pbr_series.mean())
    min10 = float(pbr_series.min())
    max10 = float(pbr_series.max())
    dmin = pbr_series.idxmin()
    dmax = pbr_series.idxmax()

    # ✅ 0.84 도달 지수 계산
    if last_pbr > 0:
        target_index = last_close * (LOW / last_pbr)
    else:
        target_index = np.nan

    header = run_label(kst)

    report_msg = (
        f"{header}\n"
        "📌 <KOSPI PBR>\n\n"
        f"📅 기준일: {fmt_date_only(last_date)}\n"
        f"📈 오늘 종가(지수): {two(last_close)}\n"
        f"🏷️ 오늘 지수 PBR: {two(last_pbr)}\n\n"
        "🧾 <최근 10년 PBR>\n"
        f"📊 평균: {two(avg10)}\n"
        f"🔻 최저: {two(min10)} ({fmt_date_only(dmin)})\n"
        f"🔺 최고: {two(max10)} ({fmt_date_only(dmax)})\n\n"
        "✅ 조건: 0.84 이하\n"
        f"📉 현재 기준 PBR 0.84 도달 하기 위한 주가지수 : {two(target_index)}\n"
    )

    send_telegram(report_msg)

    # ✅ 조건 충족(0.84 이하) 시 별도 경고
    if last_pbr <= LOW:
        alert_msg = (
            "🚨 <조건 충족 알림>\n"
            f"PBR이 0.84 이하입니다.\n\n"
            f"📅 기준일: {fmt_date_only(last_date)}\n"
            f"📈 종가(지수): {two(last_close)}\n"
            f"🏷️ PBR: {two(last_pbr)}\n"
        )
        send_telegram(alert_msg)


if __name__ == "__main__":
    main()
