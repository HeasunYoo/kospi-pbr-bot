import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import holidays
import FinanceDataReader as fdr


# =====================
# 설정
# =====================

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
# 데이터 가져오기 (FinanceDataReader)
# =====================

def get_kospi_pbr_data(from_date: str, to_date: str) -> pd.DataFrame:
    """FinanceDataReader로 KOSPI PBR 데이터 가져오기"""

    print(f"[INFO] FinanceDataReader로 데이터 조회: {from_date} ~ {to_date}")

    # KOSPI 지수 데이터 (종가 포함)
    df = fdr.DataReader("KS11", from_date, to_date)

    print(f"[INFO] KS11 rows: {len(df)}, columns: {list(df.columns)}")

    if df.empty:
        return pd.DataFrame()

    # 종가 컬럼 확인
    close_col = None
    for c in ["Close", "종가", "close"]:
        if c in df.columns:
            close_col = c
            break

    if close_col is None:
        print(f"[ERROR] 종가 컬럼 없음. 전체 컬럼: {list(df.columns)}")
        return pd.DataFrame()

    df = df[[close_col]].rename(columns={close_col: "종가"})
    df = df.replace(0, np.nan).dropna()

    # PBR 데이터 가져오기
    try:
        pbr_df = fdr.DataReader("KOSPI/PBR", from_date, to_date)
        print(f"[INFO] PBR rows: {len(pbr_df)}, columns: {list(pbr_df.columns)}")

        if not pbr_df.empty:
            pbr_col = pbr_df.columns[0]
            pbr_df = pbr_df[[pbr_col]].rename(columns={pbr_col: "PBR"})
            pbr_df["PBR"] = pd.to_numeric(pbr_df["PBR"], errors="coerce")
            df = df.join(pbr_df, how="inner")

    except Exception as e:
        print(f"[WARN] PBR 직접 조회 실패: {e}, NAVER 방식으로 시도")
        try:
            pbr_df = fdr.DataReader("NAVER/INDEX/KOSPI", from_date, to_date)
            print(f"[INFO] NAVER rows: {len(pbr_df)}, columns: {list(pbr_df.columns)}")
            pbr_candidates = [c for c in pbr_df.columns if "PBR" in str(c).upper()]
            if pbr_candidates:
                pbr_df = pbr_df[[pbr_candidates[0]]].rename(columns={pbr_candidates[0]: "PBR"})
                pbr_df["PBR"] = pd.to_numeric(pbr_df["PBR"], errors="coerce")
                df = df.join(pbr_df, how="inner")
        except Exception as e2:
            print(f"[ERROR] PBR fallback도 실패: {e2}")
            return pd.DataFrame()

    if "PBR" not in df.columns:
        print("[ERROR] PBR 컬럼 최종 없음")
        return pd.DataFrame()

    result = df[["종가", "PBR"]].replace(0, np.nan).dropna()
    print(f"[INFO] 최종 데이터: {len(result)} rows")
    return result


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
