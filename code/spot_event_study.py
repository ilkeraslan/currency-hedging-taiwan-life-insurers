"""Spot event study: Taiwan dollar against regional peers around the announcement dates.

Uses FRED daily noon buying rates (DEXTAUS, DEXKOUS, DEXSIUS). Local copies in data/ are used
if present; run with --download to fetch fresh data from FRED instead.
Writes results/results_spot.tex (table) and results/spot_macros.tex (numbers cited in the text).
"""
import glob, os, sys, json
import numpy as np
import pandas as pd
from common import DATA, RESULTS, SAMPLE_START, SAMPLE_END, fred, event_study, fmt

CODES = {"TWD": "DEXTAUS", "KRW": "DEXKOUS", "SGD": "DEXSIUS"}


def local(name):
    files = sorted(glob.glob(os.path.join(DATA, f"{name.lower()}_*.csv")))
    if not files:
        return None
    df = pd.concat([pd.read_csv(f, parse_dates=["observation_date"]) for f in files])
    return pd.to_numeric(df.set_index("observation_date").iloc[:, 0], errors="coerce")


def load():
    series = {}
    for name, code in CODES.items():
        s = None
        if "--download" in sys.argv:
            try:
                s = fred(code)
            except Exception as err:  # no connection: fall back to the copies in data/
                print(f"FRED download failed for {code} ({err.__class__.__name__}); using data/ copy.")
        series[name] = s if s is not None else local(name)
    px = pd.concat(series, axis=1).sort_index().loc[SAMPLE_START:SAMPLE_END].dropna()
    return np.log(px).diff().dropna() * 100  # per cent; positive = local currency weaker


def main():
    r = load()
    res = {"SGD": event_study(r["TWD"], r["SGD"]),
           "KRW+SGD": event_study(r["TWD"], (r["KRW"] + r["SGD"]) / 2)}
    json.dump(res, open(os.path.join(RESULTS, "spot_results.json"), "w"), indent=1)

    a, b = res["SGD"], res["KRW+SGD"]
    lines = [r"\begin{table}[htbp]", r"\centering", r"\small", r"\begin{threeparttable}",
             r"\caption{Spot response of the Taiwan dollar on announcement days}\label{tab:spot}",
             r"\begin{tabular}{@{}lp{4.6cm}cccc@{}}", r"\toprule",
             r"& & & \multicolumn{3}{c}{Abnormal change against} \\ \cmidrule(l){4-6}",
             r"Window & Event & Raw change & SGD & KRW and SGD & $p$ \\", r"\midrule"]
    for ea, eb in zip(a["events"], b["events"]):
        d = pd.Timestamp(ea["date"]).strftime("%d %b %Y").lstrip("0")
        lines.append(f"{d} & {ea['label']} & {fmt(ea['raw'])} & {fmt(ea['abnormal'])} & {fmt(eb['abnormal'])} & {eb['p']:.2f} \\\\")
    lines += [r"\midrule",
              f"\\multicolumn{{3}}{{@{{}}l}}{{Sum over the six windows}} & {fmt(a['cum'])} & {fmt(b['cum'])} & \\\\",
              f"\\multicolumn{{3}}{{@{{}}l}}{{Randomisation $p$, one-sided (two-sided)}} & {a['p_one']:.2f} ({a['p_two']:.2f}) & {b['p_one']:.2f} ({b['p_two']:.2f}) & \\\\",
              f"\\multicolumn{{3}}{{@{{}}l}}{{Standard deviation of two-day abnormal change}} & {a['sd_window']:.2f} & {b['sd_window']:.2f} & \\\\",
              r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}", r"\footnotesize",
              (r"\item Notes: Changes in the log price of the US dollar in local currency, in per cent, over two-day windows "
               r"beginning on the event date; a positive value is a weaker Taiwan dollar. Abnormal changes subtract the "
               r"comparison currency's change times the slope of a regression of daily Taiwan-dollar changes on it "
               f"(slopes {a['beta']:.2f} and {b['beta']:.2f}). The $p$-value for each window is the share of the {b['n_placebo']} "
               r"non-event two-day windows with a larger absolute abnormal change (KRW and SGD comparison). Randomisation "
               r"$p$-values for the sum compare it with 20{,}000 sums of six windows drawn from the non-event windows. "
               f"Federal Reserve noon buying rates, {pd.Timestamp(a['start']).strftime('%d %B %Y').lstrip('0')} to "
               f"{pd.Timestamp(a['end']).strftime('%d %B %Y').lstrip('0')} ({a['n_days']} trading days)."),
              r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}"]
    open(os.path.join(RESULTS, "results_spot.tex"), "w").write("\n".join(lines) + "\n")

    e2b, e6b = b["events"][1], b["events"][5]
    e2a, e6a = a["events"][1], a["events"][5]
    lo = min(e2a["abnormal"], e2b["abnormal"], e6a["abnormal"], e6b["abnormal"])
    hi = max(e2a["abnormal"], e2b["abnormal"], e6a["abnormal"], e6b["abnormal"])
    mac = {
        "spotLo": f"{lo:.1f}", "spotHi": f"{hi:.1f}",
        "spotCumSGD": f"{a['cum']:.2f}", "spotCumBoth": f"{b['cum']:.2f}",
        "spotPoneSGD": f"{a['p_one']:.2f}", "spotPoneBoth": f"{b['p_one']:.2f}",
        "spotEtwoP": f"{e2b['p']:.2f}", "spotEsixP": f"{e6b['p']:.2f}",
        "spotEoneAb": f"{abs(b['events'][0]['abnormal']):.2f}",
        "spotNdays": str(a["n_days"]), "spotSD": f"{b['sd_window']:.2f}",
    }
    open(os.path.join(RESULTS, "spot_macros.tex"), "w").write(
        "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in mac.items()) + "\n")
    for k, v in mac.items():
        print(f"{k:14s} {v}")


def long_sample():
    """Robustness: the same test with placebo windows drawn from January 2019 onwards (needs FRED access)."""
    try:
        px = pd.concat({n: fred(c, "2019-01-01", SAMPLE_END) for n, c in CODES.items()}, axis=1).dropna()
    except Exception as err:
        print(f"Long-sample robustness skipped ({err.__class__.__name__}).")
        return
    r = np.log(px).diff().dropna() * 100
    res = event_study(r["TWD"], (r["KRW"] + r["SGD"]) / 2)
    e2, e6 = res["events"][1], res["events"][5]
    px.to_csv(os.path.join(DATA, "fred_spot_2019_2026.csv"))
    json.dump(res, open(os.path.join(RESULTS, "spot_long_results.json"), "w"), indent=1)
    print(f"Long-sample robustness: {res['n_placebo']:,} non-event windows; p-values {e2['p']:.2f} and "
          f"{e6['p']:.2f} for the second and sixth windows; one-sided p {res['p_one']:.2f} for the sum.")


if __name__ == "__main__":
    main()
    if "--download" in sys.argv:
        long_sample()
