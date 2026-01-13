import argparse
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import glob
import sys
import numpy as np

def find_latest_csv(pattern="results/*keyframe_resilience*.csv"):
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=lambda p: Path(p).stat().st_mtime)

def load_csv(path):
    df = pd.read_csv(path, dtype=str)
    # normalize columns
    df["index"] = pd.to_numeric(df["index"], errors="coerce").fillna(0).astype(int)
    df["total_notes"] = pd.to_numeric(df.get("total_notes", 0), errors="coerce").fillna(0).astype(int)
    df["ok"] = df["ok"].astype(str).str.lower().map({"true": True, "false": False}).fillna(False)
    df["crc_mismatch"] = df["crc_mismatch"].astype(str).str.lower().map({"true": True, "false": False}).fillna(False)
    df["sync_hits"] = pd.to_numeric(df.get("sync_hits", 0), errors="coerce").fillna(0).astype(int)
    df["recovered_len"] = pd.to_numeric(df.get("recovered_len", 0), errors="coerce").fillna(0).astype(int)
    return df.sort_values("index").reset_index(drop=True)

def plot_cumulative_success(df, out_dir):
    df = df.copy()
    df["ok_cum"] = df["ok"].cumsum() / (df.index + 1)
    plt.figure(figsize=(8,4))
    plt.plot(df["index"], df["ok_cum"], marker="o", lw=1)
    plt.xlabel("corrupt index")
    plt.ylabel("cumulative success rate")
    plt.title("Cumulative success rate by corrupt index")
    plt.grid(alpha=0.3)
    out = out_dir / "cumulative_success_rate.png"
    plt.tight_layout()
    plt.savefig(out)
    plt.close()
    return out

def plot_recovered_len_cdf(df, out_dir):
    vals = df["recovered_len"].values
    vals_sorted = np.sort(vals)
    cdf = (np.arange(len(vals_sorted)) + 1) / len(vals_sorted)
    plt.figure(figsize=(8,4))
    plt.step(vals_sorted, cdf, where="post")
    plt.xlabel("recovered_len (bytes)")
    plt.ylabel("CDF")
    plt.title("CDF of recovered_len")
    plt.grid(alpha=0.3)
    out = out_dir / "recovered_len_cdf.png"
    plt.tight_layout()
    plt.savefig(out)
    plt.close()
    return out

def summary_stats(df):
    total = len(df)
    ok_cnt = df["ok"].sum()
    crc_cnt = df["crc_mismatch"].sum()
    recovered_positive = (df["recovered_len"] > 0).sum()
    median_len = int(df["recovered_len"].median())
    return {
        "total": total,
        "ok_cnt": int(ok_cnt),
        "ok_rate": ok_cnt / total if total else 0.0,
        "crc_mismatch_cnt": int(crc_cnt),
        "recovered_positive": int(recovered_positive),
        "median_recovered_len": median_len
    }

def main():
    parser = argparse.ArgumentParser(description="Plot resilience CSV results")
    parser.add_argument("--csv", help="path to results CSV (if omitted, use latest in results/)", default=None)
    args = parser.parse_args()

    csv_path = args.csv or find_latest_csv()
    # if user passed a bare filename, try results/ prefix as fallback
    if csv_path and not Path(csv_path).exists():
        alt = Path("results") / csv_path
        if alt.exists():
            csv_path = str(alt)
    if not csv_path:
        print("No CSV found in results/ directory.", file=sys.stderr)
        sys.exit(1)
    csv_path = Path(csv_path)
    df = load_csv(csv_path)

    out_dir = Path("results") / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    s = summary_stats(df)
    print(f"CSV: {csv_path}")
    print(f"total={s['total']} ok={s['ok_cnt']} ok_rate={s['ok_rate']:.3f} crc_mismatch={s['crc_mismatch_cnt']} recovered_positive={s['recovered_positive']} median_recovered_len={s['median_recovered_len']}")

    p1 = plot_cumulative_success(df, out_dir)
    p2 = plot_recovered_len_cdf(df, out_dir)
    print("Saved plots:")
    print(" -", p1)
    print(" -", p2)

if __name__ == "__main__":
    main()
