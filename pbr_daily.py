import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import holidays


# =====================
# 설정
# =====================

INDEX_TICKER = "1001"
LOW = 0.84

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


# =====================
# 시간
# =====================

def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul"))


# =====================
# 유틸
# =====================

def two(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "N/A"
    return f"{float(x):.2f}"


def fmt_date_only(d):
    s = str(d)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    try:
        return pd.Timestamp(d).date().isoformat()
    except Exception:
        return s


def is_korea_business_day(today: date):
    if today.weekday() >= 5:
        return False
    kr_holidays = holidays.KR(years=today.year)
    return today not in kr_holidays


def last_business_day(today: date) -> date:
    d = today - timedelta(days=1)
    while not is_korea_business_day(d):
        d -= timedelta(days=1)
    return d


def run_label(kst_dt: datetime):
    hhmm = kst_dt.strftime("%H:%M")
    if kst_dt.hour < 12:
        return f"🌅 오전 알림 ({hhmm} KST)"
    return f"🌇 오후 알림 ({hhmm} KST)"


# =====================
# Telegram
# =====================

def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("Telegram Secrets 설정 필요")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    r.raise_for_status()


# =====================
# KRX 직접 API 호출
# =====================

def get_kospi_pbr_data(from_date: str, to_date: str) -> pd.DataFrame:
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT00601",
        "locale": "ko_KR",
        "idxIndMidclssCd": "01",
        "strtDd": from_date,
        "endDd": to_date,
        "share": "2",
        "money": "3",
        "csvxls_isNo": "false",
    }

    headers = {
        "Referer": "http://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT00601.cmd",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    r = requests.post(url, data=payload, headers=headers, timeout=30)
    r.raise_for_status()

    data = r.json()

    if "output" not in data or not data["output"]:
        return pd.DataFrame()

    rows = []
    for item in data["output"]:
        try:
            if item.get("IDX_NM", "") != "코스피":
                continue
            trd_dd = item.get("TRD_DD", "").replace("/", "").replace("-", "")
            close = float(item.get("CLSPRC_IDX", "0").replace(",", ""))
            pbr = float(item.get("PBR", "0").replace(",", ""))
            if pbr == 0:
                continue
            rows.append({"날짜": trd_dd, "종가": close, "PBR": pbr})
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["날짜"] = pd.to_datetime(df["날짜"], format="%Y%m%d")
    df = df.set_index("날짜").sort_index()
    return df


# =====================
# percentile 계산
# =====================

def percentile_rank(series, value):
    return (series < value).mean() * 100


# =====================
# valuation 상태
# =====================

def valuation_state(pbr):
    if pbr <= 0.8:
        return "🔥 역사적 저평가"
    if pbr <= 0.9:
        return "🟢 저평가 구간"
    if pbr <= 1.1:
        return "⚖️ 중립 구간"
    return "🔴 고평가 구간"


# =====================
# 메인
# =====================

def main():
    kst = now_kst()
    today = kst.date()

    force = os.getenv("FORCE_SEND", "0") == "1"

    if (not force) and (not is_korea_business_day(today)):
        print("Skip: weekend/holiday")
        return

    to_date = last_business_day(today).strftime("%Y%m%d")
    from_date = (today - timedelta(days=365 * 10 + 10)).strftime("%Y%m%d")

    print(f"[INFO] 조회 기간: {from_date} ~ {to_date}")

    df = get_kospi_pbr_data(from_date, to_date)

    if df.empty:
        msg = f"⚠️ KRX 데이터 없음\n조회기간: {from_date} ~ {to_date}"
        print(msg)
        send_telegram(msg)
        return

    last_date = df.index[-1]
    last_close = float(df["종가"].iloc[-1])
    last_pbr = float(df["PBR"].iloc[-1])

    pbr_series = df["PBR"].dropna()
    avg10 = float(pbr_series.mean())
    min10 = float(pbr_series.min())
    max10 = float(pbr_series.max())
    dmin = pbr_series.idxmin()
    dmax = pbr_series.idxmax()

    pct = percentile_rank(pbr_series, last_pbr)
    state = valuation_state(last_pbr)

    if last_pbr > 0:
        target_index = last_close * (LOW / last_pbr)
    else:
        target_index = np.nan

    header = run_label(kst)

    report_msg = (
        f"{header}\n"
        "📊 <KOSPI 밸류에이션>\n\n"
        f"📅 기준일: {fmt_date_only(last_date)}\n"
        f"📈 지수: {two(last_close)}\n"
        f"🏷️ PBR: {two(last_pbr)}\n"
        f"📊 역사 percentile: {two(pct)}%\n"
        f"📌 상태: {state}\n\n"
        "📚 <최근 10년 PBR>\n"
        f"평균: {two(avg10)}\n"
        f"최저: {two(min10)} ({fmt_date_only(dmin)})\n"
        f"최고: {two(max10)} ({fmt_date_only(dmax)})\n\n"
        "🎯 <투자 감시 기준>\n"
        f"PBR 0.84 도달 지수 : {two(target_index)}\n"
    )

    send_telegram(report_msg)

    if last_pbr <= LOW:
        alert_msg = (
            "🚨 <저평가 구간 진입>\n\n"
            f"PBR: {two(last_pbr)}\n"
            f"지수: {two(last_close)}\n"
            f"날짜: {fmt_date_only(last_date)}"
        )
        send_telegram(alert_msg)


if __name__ == "__main__":
    main()
