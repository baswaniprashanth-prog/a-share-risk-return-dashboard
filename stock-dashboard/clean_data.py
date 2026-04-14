import argparse
import os
from datetime import datetime

import pandas as pd


REQUIRED = ["date", "open", "high", "low", "close", "volume"]


def clean_one_csv(path: str, min_date: str | None = None, max_date: str | None = None):
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}

    if "date" not in cols or "close" not in cols:
        raise ValueError("missing required columns: date/close")

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(df[cols["date"]], errors="coerce")
    out["close"] = pd.to_numeric(df[cols["close"]], errors="coerce")

    for c in ["open", "high", "low", "volume"]:
        if c in cols:
            out[c] = pd.to_numeric(df[cols[c]], errors="coerce")
        else:
            out[c] = out["close"] if c != "volume" else 0

    before_rows = len(out)
    dup_dates = int(out["date"].duplicated().sum())
    na_close = int(out["close"].isna().sum())

    out = out.dropna(subset=["date", "close"]).copy()
    out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")

    # basic sanity checks
    bad_price = (out["close"] <= 0) | (out["open"] <= 0)
    bad_hl = out["high"] < out["low"]
    bad_volume = out["volume"] < 0
    out = out.loc[~(bad_price | bad_hl | bad_volume)].copy()

    if min_date:
        out = out[out["date"] >= pd.to_datetime(min_date)]
    if max_date:
        out = out[out["date"] <= pd.to_datetime(max_date)]

    out = out[REQUIRED].reset_index(drop=True)

    report = {
        "file": os.path.basename(path),
        "rows_before": before_rows,
        "rows_after": len(out),
        "rows_removed": before_rows - len(out),
        "duplicate_dates": dup_dates,
        "close_missing_before": na_close,
        "date_min": out["date"].min().date().isoformat() if len(out) else "",
        "date_max": out["date"].max().date().isoformat() if len(out) else "",
    }
    return out, report


def main():
    parser = argparse.ArgumentParser(description="Clean OHLCV CSV files for offline dashboard")
    parser.add_argument("--in-dir", default="data", help="input folder containing raw csv files")
    parser.add_argument("--out-dir", default="data_clean", help="output folder for cleaned csv files")
    parser.add_argument("--min-date", default="2022-01-01", help="optional min date, format YYYY-MM-DD")
    parser.add_argument("--max-date", default="", help="optional max date, format YYYY-MM-DD")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    reports = []
    failures = []

    for fn in sorted(os.listdir(args.in_dir)):
        if not fn.lower().endswith(".csv"):
            continue
        if fn.startswith("_"):
            continue
        src = os.path.join(args.in_dir, fn)
        dst = os.path.join(args.out_dir, fn)
        try:
            cleaned, rep = clean_one_csv(src, min_date=args.min_date, max_date=args.max_date or None)
            if len(cleaned) == 0:
                failures.append(f"{fn}: no usable rows after cleaning")
                continue
            cleaned.to_csv(dst, index=False, encoding="utf-8-sig")
            reports.append(rep)
        except Exception as e:
            failures.append(f"{fn}: {e}")

    report_df = pd.DataFrame(reports)
    report_path = os.path.join(args.out_dir, "_data_quality_report.csv")
    report_df.to_csv(report_path, index=False, encoding="utf-8-sig")

    print(f"Cleaned files: {len(reports)}")
    print(f"Failed files: {len(failures)}")
    print(f"Quality report: {report_path}")
    if failures:
        fail_path = os.path.join(args.out_dir, "_clean_failures.txt")
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failures))
        print(f"Failure details: {fail_path}")
    print(f"Finished at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()

