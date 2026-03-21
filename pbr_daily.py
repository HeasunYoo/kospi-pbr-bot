import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import requests
from pykrx import stock as pkstock

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    r.raise_for_status()

kst = datetime.now(ZoneInfo("Asia/Seoul"))

# 여러 날짜 조합으로 테스트
test_cases = [
    ("20250101", "20250321"),
    ("20250301", "20250321"),
    ("20250310", "20250321"),
    ("20250317", "20250321"),
]

msg = "🔬 pykrx 진단 결과\n\n"

for from_d, to_d in test_cases:
    try:
        df = pkstock.get_index_fundamental(from_d, to_d, "1001")
        msg += f"✅ {from_d}~{to_d}\n"
        msg += f"   rows={len(df)}, cols={list(df.columns)}\n"
        if not df.empty:
            msg += f"   마지막행: {df.index[-1]}\n"
    except Exception as e:
        msg += f"❌ {from_d}~{to_d}: {e}\n"
    msg += "\n"

print(msg)
send_telegram(msg)
