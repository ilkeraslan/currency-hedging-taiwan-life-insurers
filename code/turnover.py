"""Interbank turnover by instrument (Section 5.4): outright forwards and FX swaps in the Taipei market.

Reads data/cbc_fx_turnover.csv (central bank's monthly press releases, US$ billion) and
data/cbc_swap_balance.csv, and writes results/results_turnover.tex.
"""
import os
import numpy as np
import pandas as pd
from common import DATA, RESULTS

t = pd.read_csv(os.path.join(DATA, "cbc_fx_turnover.csv"))
t["days"] = (t["total_usd_bn"] / t["daily_avg_usd_bn"]).round().astype(int)
t["fwd"] = t["outright_forwards_usd_bn"] / t["days"]
t["swap"] = t["fx_swaps_usd_bn"] / t["days"]
t["share"] = 100 * t["outright_forwards_usd_bn"] / t["total_usd_bn"]
t["year"] = t["month"].str[:4]
t["q"] = pd.PeriodIndex(t["month"], freq="M").asfreq("Q").astype(str)
a, b = t[t.year == "2025"], t[t.year == "2026"]
f25, f26, s25, s26 = a.fwd.mean(), b.fwd.mean(), a.swap.mean(), b.swap.mean()
sh25 = 100 * a.outright_forwards_usd_bn.sum() / a.total_usd_bn.sum()
sh26 = 100 * b.outright_forwards_usd_bn.sum() / b.total_usd_bn.sum()
all_below = bool(b.fwd.max() < a.fwd.min())
se = np.sqrt(a.fwd.var(ddof=1) / len(a) + b.fwd.var(ddof=1) / len(b))
tstat = (f25 - f26) / se
dec, jan = float(a.fwd.iloc[-1]), float(b.fwd.iloc[0])
sb = pd.read_csv(os.path.join(DATA, "cbc_swap_balance.csv")).set_index("date").iloc[:, 0]
nov, jun = sb["2025-11-28"], sb["2026-06-30"]
last = pd.Timestamp(b.month.iloc[-1] + "-01").strftime("%B %Y")

rows = []
for q, g in t.groupby("q"):
    lab = f"{q[:4]} Q{q[-1]}"
    rows.append(f"{lab} & {g.fwd.mean():.2f} & {g.swap.mean():.1f} & "
                f"{100 * g.outright_forwards_usd_bn.sum() / g.total_usd_bn.sum():.1f} \\\\")
tab = [r"\begin{table}[htbp]", r"\centering", r"\small", r"\begin{threeparttable}",
       r"\caption{Turnover in the Taipei foreign-exchange market by instrument}\label{tab:turnover}",
       r"\begin{tabular}{@{}lccc@{}}", r"\toprule",
       r"& Outright forwards & FX swaps & Forwards, share of \\",
       r"Quarter & (US\$ bn a day) & (US\$ bn a day) & total turnover (\%) \\", r"\midrule"] + rows + [
       r"\midrule", f"2025 & {f25:.2f} & {s25:.1f} & {sh25:.1f} \\\\",
       f"2026, January to {last.split()[0]} & {f26:.2f} & {s26:.1f} & {sh26:.1f} \\\\",
       r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}", r"\footnotesize",
       (r"\item Notes: Averages of monthly turnover per trading day, net of double counting of interbank transactions, "
        r"for authorised foreign-exchange banks and offshore banking units, all currency pairs. Trading days are total "
        r"turnover divided by the reported daily average. Source: Central Bank of the Republic of China (Taiwan), "
        r"monthly releases on the Taipei foreign exchange market."),
       r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}"]
open(os.path.join(RESULTS, "results_turnover.tex"), "w").write("\n".join(tab) + "\n")
print(f"Turnover: forwards {f25:.2f} to {f26:.2f} a day ({100 * (1 - f26 / f25):.0f} per cent lower, t {tstat:.1f}); "
      f"swaps {s25:.1f} to {s26:.1f}; all 2026 months below 2025: {all_below}; forward share {sh25:.1f} to {sh26:.1f} per cent; "
      f"forwards December 2025 {dec:.2f}, January 2026 {jan:.2f}; central-bank swaps {nov:.1f} (Nov 2025) and {jun:.1f} (Jun 2026).")
print(t[["month", "days", "fwd", "swap", "share"]].round(2).to_string(index=False))
