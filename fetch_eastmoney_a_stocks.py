import argparse
import csv
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


EASTMONEY_KLINE_URLS = [
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "http://push2his.eastmoney.com/api/qt/stock/kline/get",
]
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
EASTMONEY_UT = "fa5fd1943c7b386f172d6893dbfba10b"


def secid_from_symbol_exchange(symbol: str, exchange: str) -> Optional[str]:
    exchange = exchange.upper().strip()
    symbol = symbol.strip()
    if exchange == "SZ":
        return f"0.{symbol}"
    if exchange == "SH":
        return f"1.{symbol}"
    return None


def fetch_daily_ohlcv(
    session: requests.Session,
    secid: str,
    beg: str,
    end: str,
    timeout: int = 15,
) -> List[Dict[str, str]]:
    params = {
        "secid": secid,
        "ut": EASTMONEY_UT,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": "101",
        "fqt": "0",
        "beg": beg,
        "end": end,
    }
    payload = None
    last_error: Optional[Exception] = None
    for url in EASTMONEY_KLINE_URLS:
        try:
            resp = session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            break
        except Exception as exc:
            last_error = exc
            continue

    if payload is None:
        raise RuntimeError(f"请求失败: {last_error}")
    data = payload.get("data") or {}
    klines = data.get("klines") or []

    rows: List[Dict[str, str]] = []
    for k in klines:
        parts = k.split(",")
        if len(parts) < 6:
            continue
        # eastmoney格式: date,open,close,high,low,volume,...
        rows.append(
            {
                "date": parts[0],
                "open": parts[1],
                "high": parts[3],
                "low": parts[4],
                "close": parts[2],
                "volume": parts[5],
            }
        )
    return rows


def to_tencent_symbol(symbol: str, exchange: str) -> Optional[str]:
    exchange = exchange.upper().strip()
    symbol = symbol.strip()
    if exchange == "SZ":
        return f"sz{symbol}"
    if exchange == "SH":
        return f"sh{symbol}"
    return None


def fetch_daily_ohlcv_tencent(
    session: requests.Session,
    symbol: str,
    exchange: str,
    start_date_dash: str,
    end_date_dash: str,
    timeout: int = 15,
) -> List[Dict[str, str]]:
    tsymbol = to_tencent_symbol(symbol, exchange)
    if tsymbol is None:
        return []

    param = f"{tsymbol},day,{start_date_dash},{end_date_dash},640,qfq"
    resp = session.get(
        TENCENT_KLINE_URL,
        params={"param": param},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") or {}
    stock_data = data.get(tsymbol) or {}
    klines = stock_data.get("qfqday") or stock_data.get("day") or []

    rows: List[Dict[str, str]] = []
    for k in klines:
        if len(k) < 6:
            continue
        # 腾讯格式: date,open,close,high,low,volume
        rows.append(
            {
                "date": str(k[0]),
                "open": str(k[1]),
                "high": str(k[3]),
                "low": str(k[4]),
                "close": str(k[2]),
                "volume": str(k[5]),
            }
        )
    return rows


def clean_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    dedup: Dict[str, Dict[str, str]] = {}
    for row in rows:
        date = row["date"]
        dedup[date] = row
    sorted_dates = sorted(dedup.keys())
    return [dedup[d] for d in sorted_dates]


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_symbols(input_csv: Path) -> List[Tuple[str, str, str]]:
    stocks: List[Tuple[str, str, str]] = []
    with input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for item in reader:
            symbol = (item.get("symbol") or "").strip()
            exchange = (item.get("exchange") or "").strip()
            name = (item.get("name") or "").strip()
            if not symbol or not exchange:
                continue
            stocks.append((symbol, exchange, name))
    return stocks


def main() -> None:
    parser = argparse.ArgumentParser(description="批量抓取A股历史行情并按统一CSV格式落盘")
    parser.add_argument("--input", default="_all_a_stocks.csv", help="股票代码表CSV路径")
    parser.add_argument("--outdir", default="data", help="输出目录")
    parser.add_argument("--start", default="20220101", help="开始日期，格式YYYYMMDD")
    parser.add_argument("--end", default="20500101", help="结束日期，格式YYYYMMDD")
    parser.add_argument("--limit", type=int, default=0, help="仅抓取前N只，0表示全部")
    parser.add_argument("--sleep", type=float, default=0.08, help="每只股票请求后sleep秒数")
    parser.add_argument("--min-rows", type=int, default=200, help="最小行数阈值（仅提示）")
    parser.add_argument(
        "--source",
        default="auto",
        choices=["auto", "tencent", "eastmoney"],
        help="数据源：auto(优先腾讯)、tencent、eastmoney",
    )
    args = parser.parse_args()

    input_csv = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    stocks = read_symbols(input_csv)
    if args.limit > 0:
        stocks = stocks[: args.limit]

    session = requests.Session()
    # 避免使用系统代理，减少403/连接中断干扰。
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
        }
    )

    ok = 0
    failed: List[str] = []
    short_rows: List[str] = []

    for idx, (symbol, exchange, name) in enumerate(stocks, start=1):
        secid = secid_from_symbol_exchange(symbol, exchange)
        if secid is None:
            failed.append(f"{symbol}({exchange}) 不支持交易所")
            continue

        try:
            rows: List[Dict[str, str]] = []

            start_dash = f"{args.start[:4]}-{args.start[4:6]}-{args.start[6:8]}"
            end_dash = f"{args.end[:4]}-{args.end[4:6]}-{args.end[6:8]}"

            if args.source in ("auto", "tencent"):
                rows = fetch_daily_ohlcv_tencent(
                    session=session,
                    symbol=symbol,
                    exchange=exchange,
                    start_date_dash=start_dash,
                    end_date_dash=end_dash,
                )

            if not rows and args.source in ("auto", "eastmoney"):
                rows = fetch_daily_ohlcv(session, secid, args.start, args.end)

            rows = clean_rows(rows)
            if not rows:
                failed.append(f"{symbol}({exchange}) 无数据")
                continue
            out_path = outdir / f"{symbol}.csv"
            write_csv(out_path, rows)
            ok += 1
            if len(rows) < args.min_rows:
                short_rows.append(f"{symbol}({exchange}) 行数={len(rows)}")
            if idx % 50 == 0:
                print(f"[进度] {idx}/{len(stocks)} 已处理")
        except Exception as exc:
            failed.append(f"{symbol}({exchange}) 失败: {exc}")
        finally:
            if args.sleep > 0:
                time.sleep(args.sleep)

    print(f"\n完成: 成功 {ok} / 总数 {len(stocks)}")
    if short_rows:
        print(f"低于最小行数({args.min_rows})的股票数量: {len(short_rows)}")
        for item in short_rows[:20]:
            print("  -", item)
        if len(short_rows) > 20:
            print(f"  ... 其余 {len(short_rows) - 20} 条已省略")
    if failed:
        print(f"失败数量: {len(failed)}")
        for item in failed[:30]:
            print("  -", item)
        if len(failed) > 30:
            print(f"  ... 其余 {len(failed) - 30} 条已省略")


if __name__ == "__main__":
    main()
