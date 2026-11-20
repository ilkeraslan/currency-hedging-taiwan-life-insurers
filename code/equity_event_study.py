"""Share-price event study: insurance-heavy financial holding companies against bank-heavy ones.

Downloads daily adjusted closing prices from Yahoo Finance (pip install yfinance) for listed Taiwanese
financial holding companies and tests whether the insurance-heavy group outperformed the bank-heavy
group in the two-day windows beginning on the announcement dates.
Writes results/equity_results.json and results/results_equity.tex. If the download fails, nothing is
written; --from-json rebuilds the table from results/equity_results.json.
"""
import os, sys, json
import numpy as np
import pandas as pd
from common import RESULTS, SAMPLE_START, SAMPLE_END, event_study, fmt

INSURERS = {"2882.TW": "Cathay", "2881.TW": "Fubon", "2883.TW": "KGI", "2887.TW": "Taishin-Shin Kong"}
BANKS = {"2884.TW": "E.Sun", "2886.TW": "Mega", "2892.TW": "First", "2880.TW": "Hua Nan",
         "5880.TW": "Taiwan Cooperative", "2890.TW": "SinoPac"}


def download():
    import yfinance as yf
    tickers = list(INSURERS) + list(BANKS)
    end = (pd.Timestamp(SAMPLE_END) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.download(tickers, start=SAMPLE_START, end=end, auto_adjust=True, progress=False)
    px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    return px.dropna(how="all")


def main(px=None):
    if px is None:
        try:
            px = download()
        except Exception as err:
            print(f"Share prices not downloaded ({err.__class__.__name__}: {err}). Results not written.")
            return False
    ins = [t for t in INSURERS if t in px and px[t].notna().sum() > 150]
    bnk = [t for t in BANKS if t in px and px[t].notna().sum() > 150]
    if len(ins) < 2 or len(bnk) < 3:
        print("Too few share-price series returned. Results not written.")
        return False
    r = np.log(px[ins + bnk]).diff() * 100
    grp = pd.DataFrame({"ins": r[ins].mean(axis=1), "bnk": r[bnk].mean(axis=1)}).dropna()
    res = event_study(grp["ins"], grp["bnk"])
    res["insurers"], res["banks"] = [INSURERS[t] for t in ins], [BANKS[t] for t in bnk]
    json.dump(res, open(os.path.join(RESULTS, "equity_results.json"), "w"), indent=1)
    return write_outputs(res)


def write_outputs(res):

    cum, p1 = res["cum"], res["p_one"]
    names = ", ".join(res["insurers"][:-1]) + " and " + res["insurers"][-1]
    lines = [r"\begin{table}[htbp]", r"\centering", r"\small", r"\begin{threeparttable}",
             r"\caption{Share-price response of insurance-heavy financial groups on announcement days}\label{tab:equity}",
             r"\begin{tabular}{@{}lp{6.2cm}cc@{}}", r"\toprule",
             r"Window & Event & Abnormal return (pp) & $p$ \\", r"\midrule"]
    for e in res["events"]:
        d = pd.Timestamp(e["date"]).strftime("%d %b %Y").lstrip("0")
        lines.append(f"{d} & {e['label']} & {fmt(e['abnormal'])} & {e['p']:.2f} \\\\")
    lines += [r"\midrule",
              f"\\multicolumn{{2}}{{@{{}}l}}{{Sum over the six windows}} & {fmt(cum)} & \\\\",
              f"\\multicolumn{{2}}{{@{{}}l}}{{Randomisation $p$, one-sided (two-sided)}} & {p1:.2f} ({res['p_two']:.2f}) & \\\\",
              r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}", r"\footnotesize",
              (r"\item Notes: Two-day log returns, in per cent, of an equal-weighted portfolio of " + names +
               r" less the return of an equal-weighted portfolio of " + ", ".join(res["banks"]) +
               f" times the regression slope ({res['beta']:.2f}). Inference as in Table~\\ref{{tab:spot}}. "
               r"Dividend-adjusted closing prices, Taiwan Stock Exchange, "
               f"{pd.Timestamp(res['start']).strftime('%d %B %Y').lstrip('0')} to "
               f"{pd.Timestamp(res['end']).strftime('%d %B %Y').lstrip('0')}."),
              r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}"]
    open(os.path.join(RESULTS, "results_equity.tex"), "w").write("\n".join(lines) + "\n")
    print(f"Share-price results written: sum {cum:+.2f} pp, one-sided p {p1:.2f}.")
    return True


if __name__ == "__main__":
    if "--from-json" in sys.argv:  # rebuild the table from saved results
        sys.exit(0 if write_outputs(json.load(open(os.path.join(RESULTS, "equity_results.json")))) else 1)
    sys.exit(0 if main() else 1)
