import argparse
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import requests
from tqdm import tqdm

SESSION = requests.Session()
SESSION.trust_env = False


def disable_proxy_env():
    for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"


def load_stock_list(out_dir: str) -> pd.DataFrame:
    # 优先使用已有列表，避免再次联网取列表
    list_path = os.path.join(out_dir, "_all_a_stocks.csv")
    if not os.path.exists(list_path):
        raise FileNotFoundError("缺少 data/_all_a_stocks.csv，请先准备股票代码列表。")
    df = pd.read_csv(list_path, dtype=str)
    code_col = "symbol" if "symbol" in df.columns else df.columns[0]
    out = pd.DataFrame()
    out["symbol"] = df[code_col].astype(str).str.zfill(6)
    return out.drop_duplicates("symbol")


def netease_code(symbol: str) -> str:
    # 网易历史接口：上交所前缀0，深交所前缀1
    return ("0" if symbol.startswith(("5", "6", "9")) else "1") + symbol


def fetch_one(symbol: str, start: str, end: str, timeout: int = 20):
    code = netease_code(symbol)
    url = (
        "http://quotes.money.163.com/service/chddata.html"
        f"?code={code}&start={start}&end={end}"
        "&fields=TOPEN;HIGH;LOW;TCLOSE;VOTURNOVER"
    )
    resp = SESSION.get(url, timeout=timeout, proxies={"http": None, "https": None})
    if resp.status_code != 200 or not resp.content:
        return None
    try:
        text = resp.content.decode("gbk", errors="ignore")
    except Exception:
        return None
    if "日期" not in text:
        return None
    df = pd.read_csv(io.StringIO(text))
    # 常见列：日期,股票代码,名称,收盘价,最高价,最低价,开盘价,...,成交量
    rename_map = {}
    for c in df.columns:
        if c == "日期":
            rename_map[c] = "date"
        elif c == "开盘价":
            rename_map[c] = "open"
        elif c == "最高价":
            rename_map[c] = "high"
        elif c == "最低价":
            rename_map[c] = "low"
        elif c == "收盘价":
            rename_map[c] = "close"
        elif c == "成交量":
            rename_map[c] = "volume"
    df = df.rename(columns=rename_map)
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        return None
    out = df[["date", "open", "high", "low", "close", "volume"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["date", "close"]).sort_values("date").drop_duplicates("date")
    if out.empty:
        return None
    return out


def download_one(symbol: str, start: str, end: str, retries: int = 3):
    for i in range(retries):
        try:
            df = fetch_one(symbol, start, end)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
        time.sleep(0.8 * (i + 1))
    return None


def worker(symbol: str, args):
    fp = os.path.join(args.out_dir, f"{symbol}.csv")
    if os.path.exists(fp):
        return symbol, "skip"
    df = download_one(symbol, args.start, args.end, retries=3)
    if df is None or df.empty:
        return symbol, "fail"
    df.to_csv(fp, index=False, encoding="utf-8-sig")
    if args.sleep > 0:
        time.sleep(args.sleep)
    return symbol, "ok"


def run_batch(symbols, args):
    ok, skip, fail = 0, 0, 0
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futures = [ex.submit(worker, s, args) for s in symbols]
        pbar = tqdm(total=len(futures), desc="Downloading")
        for fut in as_completed(futures):
            _, status = fut.result()
            if status == "ok":
                ok += 1
            elif status == "skip":
                skip += 1
            else:
                fail += 1
                failed.append(_)
            pbar.update(1)
            pbar.set_postfix(ok=ok, skip=skip, fail=fail)
        pbar.close()
    return ok, skip, fail, failed


def main():
    parser = argparse.ArgumentParser(description="A股历史数据下载（网易CSV接口，断点续传）")
    parser.add_argument("--start", default="20220101", help="开始日期 YYYYMMDD")
    parser.add_argument("--end", default=datetime.now().strftime("%Y%m%d"), help="结束日期 YYYYMMDD")
    parser.add_argument("--max-stocks", type=int, default=0, help="仅下载前N只；0表示全量")
    parser.add_argument("--list-only", action="store_true", help="只读取并显示列表数量")
    parser.add_argument("--sleep", type=float, default=0.05, help="每只下载后额外等待秒数")
    parser.add_argument("--workers", type=int, default=4, help="并发线程数（建议 2~8）")
    parser.add_argument("--rounds", type=int, default=2, help="失败重试轮次")
    parser.add_argument("--out-dir", default="data", help="输出目录")
    parser.add_argument("--symbols-file", default="", help="只处理该文件中的代码（每行1个）")
    args = parser.parse_args()

    disable_proxy_env()
    os.makedirs(args.out_dir, exist_ok=True)

    stocks = load_stock_list(args.out_dir)
    print(f"A股列表数量: {len(stocks)}")
    if args.list_only:
        return
    if args.max_stocks > 0:
        stocks = stocks.head(args.max_stocks).copy()
    symbols = stocks["symbol"].tolist()
    if args.symbols_file:
        with open(args.symbols_file, "r", encoding="utf-8") as f:
            subset = {x.strip().zfill(6) for x in f if x.strip()}
        symbols = [s for s in symbols if s in subset]
    print(f"本次下载数量: {len(symbols)} | 并发: {args.workers} | 重试轮次: {args.rounds}")

    total_ok, total_skip = 0, 0
    pending = symbols[:]
    for r in range(1, max(1, args.rounds) + 1):
        if not pending:
            break
        print(f"\n第 {r}/{args.rounds} 轮，待处理: {len(pending)}")
        ok, skip, _fail, failed = run_batch(pending, args)
        total_ok += ok
        total_skip += skip
        pending = failed

    print("\n下载完成")
    print(f"成功: {total_ok}  跳过: {total_skip}  最终失败: {len(pending)}")
    if pending:
        fail_path = os.path.join(args.out_dir, "_failed_symbols.txt")
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("\n".join(pending))
        print(f"失败列表已保存: {fail_path}")


if __name__ == "__main__":
    main()

