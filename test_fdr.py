import FinanceDataReader as fdr

tests = [
    ("KS11", "20250101", "20250320"),
    ("KOSPI/PBR", "20250101", "20250320"),
]

for sym, s, e in tests:
    try:
        df = fdr.DataReader(sym, s, e)
        print(f"OK {sym}: rows={len(df)}, cols={list(df.columns)}")
        if not df.empty:
            print(f"   last: {df.index[-1]}")
            print(df.tail(3))
    except Exception as ex:
        print(f"FAIL {sym}: {ex}")
