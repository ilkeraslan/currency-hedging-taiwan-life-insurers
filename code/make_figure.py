"""Figure 1: sector hedge ratio and FX buffers, from data/fsc_monthly.csv."""
import os, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
df = pd.read_csv(os.path.join(B, "data", "fsc_monthly.csv"))
df["date"] = pd.to_datetime(df["month"]) + pd.offsets.MonthEnd(0)
plt.rcParams.update({"font.family": "serif", "font.size": 9})
fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.8))
h = df.dropna(subset=["hedge_ratio_pct"])
ax[0].plot(h["date"], h["hedge_ratio_pct"], "k-o", ms=3, lw=1)
for d, lab in [("2025-12-23", "Draft"), ("2026-01-01", "Effective")]:
    ax[0].axvline(pd.Timestamp(d), color="0.5", ls="--", lw=0.8)
ax[0].set_ylabel("Hedge ratio, per cent")
ax[0].set_title("(a) Sector hedge ratio", fontsize=9)
ax[0].set_ylim(40, 68)
r = df.dropna(subset=["fx_reserve_ntbn"])
ax[1].bar(r["date"], r["fx_reserve_ntbn"], width=20, color="0.35", label="FX valuation reserve")
s = df.dropna(subset=["special_surplus_reserve_ntbn"])
s = s[s["date"].isin(r["date"])]
ax[1].bar(s["date"], s["special_surplus_reserve_ntbn"], width=20, bottom=r.set_index("date").loc[s["date"], "fx_reserve_ntbn"].values,
          color="0.75", label="Special surplus reserve")
ax[1].set_ylabel("NT$ billion")
ax[1].set_title("(b) Foreign-exchange buffers", fontsize=9)
ax[1].legend(frameon=False, fontsize=7, loc="upper left")
for a in ax:
    a.tick_params(axis="x", labelrotation=45, labelsize=7)
    a.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(B, "results", "fig_hedging.pdf"))
print("saved")
