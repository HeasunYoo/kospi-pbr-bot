import FinanceDataReader as fdr

# 종가 테스트
print("=== KS11 종가 ===")
df = fdr.DataReader("KS11", "20250101", "20250320")
print(f"rows={len(df)}, cols={list(df.columns)}")
if not df.empty:
    print(df.tail(2))

# PBR 소스 테스트
sources = [
    "KRX/INDEX/KOSPI",
    "NAVER/INDEX/KOSPI",
]

for sym in sources:
    print(f"\n=== {sym} ===")
    try:
        df = fdr.DataReader(sym, "20250101", "20250320")
        print(f"rows={len(df)}, cols={list(df.columns)}")
        if not df.empty:
            print(df.tail(2))
    except Exception as e:
        print(f"FAIL: {e}")
