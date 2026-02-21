import os
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
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

def fmt_date(d):
    s = str(d)
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s

def main():
    itickers = pkstock.get_index_ticker_list(market=MARKET)
    i2name = {t: f"{MARKET}:{pkstock.get_index_ticker_name(t)}" for t in itickers}
    name2i = {v: k for k, v in i2name.items()}
    iticker = name2i[f"{MARKET}:{INDEX_NAME}"]

    from_date = (datetime.today() - timedelta(days=365*10)).strftime("%Y%m%d")
    to_date = datetime.today().strftime("%Y%m%d")

    df = pkstock.get_index_fundamental(from_date, to_date, iticker)[["종가","PBR"]]
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

    msg = f"""[KOSPI PBR]

기준일: {fmt_date(last_date)}
종가: {last_close}
PBR: {two(last_pbr)}

[최근 10년]
평균: {two(avg10)}
최저: {two(min10)} ({fmt_date(dmin)})
최고: {two(max10)} ({fmt_date(dmax)})

조건: <= {LOW} 또는 >= {HIGH}
"""

    if float(last_pbr) <= LOW or float(last_pbr) >= HIGH:
        msg += f"\n🚨 조건 충족! PBR={two(last_pbr)}"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

if __name__ == "__main__":
    main()
