"""Forward-market evidence from exchange-traded currency futures.

Downloads the Singapore Exchange's daily settlement files and extracts the TWD/USD futures and the
exchange's actively traded futures on other Asian currencies. The ratio of the settlement prices of two
contracts gives the dollar's annualised forward discount between their expiry dates. The script
  (i)   tabulates and plots the discount over the sample,
  (ii)  measures its change between the industry's proposal and the end of 2025, and
  (iii) tests for a response in the two-day windows beginning on the announcement dates.
Writes results/results_futures.tex, results/fig_futures.pdf, results/futures_results.json and
results/futures_discount_three_month.csv; run with --history to build the longer comparison sample
(results/futures_long_results.json). The settlement files are downloaded from the exchange and
cached in data/sgx_fx_futures.csv and data/sgx_fx_futures_history.csv.
"""
import glob, io, json, os, sys, zipfile, calendar
import numpy as np
import pandas as pd
from common import DATA, RESULTS, SAMPLE_START, SAMPLE_END, EVENTS, event_study, fmt

URL = "https://links.sgx.com/1.0.0/derivatives-daily/{n}/FUTURE.zip"
CACHE = os.path.join(DATA, "sgx_fx_futures.csv")
HIST = os.path.join(DATA, "sgx_fx_futures_history.csv")      # earlier years, for the long comparison sample
HIST_START = "2019-01-01"
# Contract code and quotation. TWD, KU and IU are quoted in US dollars per unit of local currency;
# UC (USD/CNH) is quoted in renminbi per dollar. Peers are the Asian currency futures that trade actively;
# the exchange's contracts on the Philippine peso and Indonesian rupiah did not trade in the sample.
TWD = ("TWD", False)
PEERS = {"the Korean won": ("KU", False), "the Indian rupee": ("IU", False),
         "the offshore renminbi": ("UC", True)}
ALL_CODES = ["TWD", "TD", "KRW", "KU", "INR", "IU", "UC", "PHP", "IDR"]
PROPOSAL, YEAR_END = "2025-11-21", "2025-12-31"
MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}


def fetch(n):
    import requests, time
    r = None
    for attempt in range(4):
        try:
            r = requests.get(URL.format(n=n), timeout=40, headers={"User-Agent": "Mozilla/5.0"})
            break
        except Exception:
            time.sleep(2 + 3 * attempt)
    if r is None or r.status_code != 200 or r.content[:2] != b"PK":
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    raw = z.read(z.namelist()[0]).decode("latin-1")
    sep = "\t" if raw.splitlines()[0].count("\t") >= 3 else ","
    df = pd.read_csv(io.StringIO(raw), sep=sep)
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def file_date(df):
    col = next((c for c in df.columns if c in ("DATE", "TRADE_DATE", "BUSINESS_DATE")), df.columns[0])
    vals = df[col].dropna()
    if vals.empty:                                   # a file with a header and no rows
        return pd.NaT
    return pd.to_datetime(str(vals.iloc[0]).strip(), errors="coerce")


def locate(target):
    """Find the archive number whose file is dated on or just after `target`."""
    n = None
    for guess in list(range(6600, 4800, -150)) + list(range(6750, 8400, 150)):
        df = fetch(guess)
        if df is not None and pd.notna(file_date(df)):
            n, d = guess, file_date(df)
            break
    if n is None:
        raise RuntimeError("no SGX archive file found")
    for _ in range(25):
        gap = int(np.busday_count(d.date(), target.date()))
        if gap == 0:
            break
        step = gap if abs(gap) > 3 else int(np.sign(gap))
        m = n + step
        df = fetch(m)
        tries = 0
        while df is None and tries < 5:
            m += int(np.sign(step)); df = fetch(m); tries += 1
        if df is None:
            break
        n, d = m, file_date(df)
    while d < target:
        n += 1
        df = fetch(n)
        if df is not None:
            d = file_date(df)
    return n


def download():
    start, end = pd.Timestamp(SAMPLE_START), pd.Timestamp(SAMPLE_END)
    n = locate(start)
    rows, misses, sample_saved = [], 0, False
    print(f"SGX archive starts at file {n}; downloading about 260 daily files ...")
    while misses < 8:
        df = fetch(n)
        n += 1
        if df is None:
            misses += 1
            continue
        misses = 0
        d = file_date(df)
        if pd.isna(d) or d > end:
            break
        if not sample_saved:
            df.head(400).to_csv(os.path.join(DATA, "sgx_sample.csv"), index=False)
            sample_saved = True
        df["FILE_DATE"] = d
        rows.append(df)
    allr = pd.concat(rows, ignore_index=True)
    com = next(c for c in allr.columns if c in ("COM", "COMMODITY", "CONTRACT", "SERIES"))
    keep = set(ALL_CODES)
    fx = allr[allr[com].astype(str).str.strip().isin(keep)].copy()
    fx.to_csv(CACHE, index=False)
    return fx


def download_history():
    """Daily files before the main sample, back to HIST_START. Resumable: progress is saved every batch."""
    from concurrent.futures import ThreadPoolExecutor
    start = pd.Timestamp(HIST_START)
    if os.path.exists(HIST):
        done = pd.read_csv(HIST)
        n = int(done["ARCHIVE_N"].min()) - 1
        if pd.to_datetime(done["FILE_DATE"], format="mixed").min() <= start + pd.Timedelta(days=7):
            return done
        parts = [done]
    else:
        n = locate(pd.Timestamp(SAMPLE_START)) - 1
        parts = []
    print(f"Downloading earlier daily files back to {HIST_START}, starting at file {n} (about 1,650 files; "
          "this takes 15 to 30 minutes and can be interrupted and resumed) ...", flush=True)
    empty = 0
    while n > 0 and empty < 8:
        batch = list(range(n, max(n - 24, 0), -1))
        with ThreadPoolExecutor(8) as ex:
            got = list(ex.map(fetch, batch))
        n = batch[-1] - 1
        rows, earliest = [], None
        for k, df in zip(batch, got):
            if df is None or not {"COM", "COM_MM", "COM_YY", "SETTLE"} <= set(df.columns):
                continue
            d = file_date(df)
            if pd.isna(d):
                continue
            earliest = d if earliest is None else min(earliest, d)
            if d < start:
                continue
            df = df[df["COM"].astype(str).str.strip().isin(ALL_CODES)].copy()
            df["FILE_DATE"], df["ARCHIVE_N"] = d, k
            rows.append(df)
        if earliest is None:
            empty += 1
            continue
        empty = 0
        if rows:
            parts.append(pd.concat(rows, ignore_index=True))
            pd.concat(parts, ignore_index=True).to_csv(HIST, index=False)
            print(f"  back to {earliest.date()}", flush=True)
        if earliest < start:
            break
    if not parts:
        raise RuntimeError("no earlier SGX files found")
    return pd.concat(parts, ignore_index=True)


def long_sample(fx_all):
    """Announcement windows and the proposal-to-year-end change against the history since HIST_START."""
    out = {}
    for far, key in ((1, "one_month"), (3, "three_month")):
        lev, chg = panel(fx_all, far)
        # stale settlement prices in the early years produce a few extreme one-day changes; trim them symmetrically
        lim = chg["TWD"].abs().quantile(0.995)
        chg = chg[chg["TWD"].abs() <= lim]
        r = event_study(-chg["TWD"], -chg["peers"])
        out[key] = {"cum": r["cum"], "p_one": r["p_one"], "p_two": r["p_two"], "n_placebo": r["n_placebo"],
                    "sd_window": r["sd_window"], "start": r["start"], "end": r["end"],
                    "events": [{"date": e["date"], "abnormal": e["abnormal"], "p": e["p"]} for e in r["events"]]}
        if far == 3:
            w = window_change(lev)
            rel = lev["TWD"] - lev["peers"]
            n = w["n"]
            allc = (rel.shift(-n) - rel).dropna()
            a = int(lev.index.searchsorted(pd.Timestamp(PROPOSAL))) - 1
            grid = allc.iloc[[i for i in range(a % n, len(allc), n) if i != a]]     # non-overlapping windows
            raw = (lev["TWD"].shift(-n) - lev["TWD"]).dropna()
            out["window"] = {**w, "n_windows": int(len(allc)), "share_raw": float((raw <= w["twd"]).mean()),
                             "n_nonoverlap": int(len(grid)), "nonoverlap_as_large": int((grid <= w["rel"]).sum()),
                             "episodes": sorted({str(d.date())[:7] for d in allc[allc <= w["rel"]].index})}
            yearly = lev.resample("YE").mean()
            out["yearly_three_month"] = {str(k.year): {"TWD": float(v["TWD"]), "peers": float(v["peers"])} for k, v in yearly.iterrows()}
            lev.round(1).to_csv(os.path.join(RESULTS, "futures_discount_three_month_long.csv"))
        tw = fx_all[fx_all["COM"].astype(str).str.strip() == TWD[0]]
        out["twd_volume_by_year"] = {str(k): float(v) for k, v in tw.groupby(pd.to_datetime(tw["FILE_DATE"], format="mixed").dt.year)["VOLUME"].sum().items()}
    return out


def third_monday(year, month):
    d = pd.Timestamp(year=year, month=month, day=1)
    return d + pd.Timedelta(days=(7 - d.weekday()) % 7 + 14)


def discount(fx, code, flip, far):
    """Dollar's annualised forward discount (bp) between the nearest contract and the one `far` months on.

    Returns the daily level and the daily change; the change on each day is computed for that day's
    pair of contracts on both days, so that it never mixes two pairs when the nearest contract rolls.
    """
    g = fx[fx["COM"].astype(str).str.strip() == code].copy()
    g["p"] = pd.to_numeric(g["SETTLE"], errors="coerce")
    g = g[g["p"] > 0]
    g["expiry"] = [third_monday(int(y), int(m)) for y, m in zip(g["COM_YY"], g["COM_MM"])]
    g["d"] = pd.to_datetime(g["FILE_DATE"], format="mixed")
    piv = g.pivot_table(index="d", columns="expiry", values="p")
    dates, lev, chg = list(piv.index), {}, {}
    for k, d in enumerate(dates):
        cols = [c for c in piv.columns if c >= d + pd.Timedelta(days=7) and pd.notna(piv.loc[d, c])]
        if len(cols) <= far:
            continue
        c1, c2 = cols[0], cols[far]

        def disc(row):
            a, b = row[c1], row[c2]
            if pd.isna(a) or pd.isna(b):
                return np.nan
            ratio = a / b if flip else b / a          # price of the far contract relative to the near one
            return (ratio - 1) * 360 / (c2 - c1).days * 1e4

        lev[d] = disc(piv.loc[d])
        if k > 0:
            chg[d] = lev[d] - disc(piv.loc[dates[k - 1]])
    return pd.Series(lev).sort_index(), pd.Series(chg).sort_index()


def panel(fx, far):
    lev, chg = {}, {}
    lev["TWD"], chg["TWD"] = discount(fx, TWD[0], TWD[1], far)
    for name, (code, flip) in PEERS.items():
        lev[name], chg[name] = discount(fx, code, flip, far)
    lev, chg = pd.DataFrame(lev), pd.DataFrame(chg).dropna()
    lev["peers"] = lev[list(PEERS)].mean(axis=1)
    chg["peers"] = chg[list(PEERS)].mean(axis=1)
    return lev, chg


def window_change(lev):
    """Change in the discount from the last close before the proposal to the last trading day of 2025."""
    rel = lev["TWD"] - lev["peers"]
    a = int(lev.index.searchsorted(pd.Timestamp(PROPOSAL))) - 1
    b = int(lev.index.searchsorted(pd.Timestamp(YEAR_END), side="right")) - 1
    n = b - a
    out = {"from": str(lev.index[a].date()), "to": str(lev.index[b].date()), "n": n,
           "twd_from": float(lev["TWD"].iloc[a]), "twd_to": float(lev["TWD"].iloc[b]),
           "twd": float(lev["TWD"].iloc[b] - lev["TWD"].iloc[a]),
           "peers": float(lev["peers"].iloc[b] - lev["peers"].iloc[a])}
    out["rel"] = out["twd"] - out["peers"]
    allc = (rel.shift(-n) - rel).dropna()
    bigger = allc[allc <= out["rel"]]                 # a narrowing is a fall in the discount
    out["share"] = float(len(bigger) / len(allc))
    return out


def history_stats():
    """Level and change of the three-month discount against the contract's history (needs --history first)."""
    path = os.path.join(RESULTS, "futures_discount_three_month_long.csv")
    if not os.path.exists(path):
        return None
    l = pd.read_csv(path, index_col=0, parse_dates=True).dropna(subset=["TWD"])
    a = int(l.index.searchsorted(pd.Timestamp(PROPOSAL))) - 1
    b = int(l.index.searchsorted(pd.Timestamp(YEAR_END), side="right")) - 1
    n = b - a
    pre, post = l.iloc[:a + 1], l[l.index > pd.Timestamp(YEAR_END)]
    monthly = pre["TWD"].resample("ME").mean()
    rel = l["TWD"] - l["peers"]
    ch = (rel.shift(-n) - rel).dropna()
    pos = np.arange(len(ch))
    other = ch[np.abs(pos - a) >= n]                      # windows that do not overlap the event window
    big = other[other <= ch.iloc[a]]
    mid25 = big[(big.index >= "2025-06-01") & (big.index <= "2025-07-31")]
    out = {"start": str(l.index[0].date()), "n_pre": int(len(pre)), "pre_mean": float(pre["TWD"].mean()),
           "pre_min_month": float(monthly.min()), "pre_min_month_date": str(monthly.idxmin().date())[:7],
           "pre_days_below_100": int((pre["TWD"] < 100).sum()), "post_mean": float(post["TWD"].mean()),
           "post_share_premium": float((post["TWD"] < 0).mean()), "post_end": str(post.index[-1].date()),
           "n_other": int(len(other)), "n_big": int(len(big)), "n_big_mid25": int(len(mid25)), "n": int(n)}
    long_json = os.path.join(RESULTS, "futures_long_results.json")
    if os.path.exists(long_json):
        r = json.load(open(long_json))
        out["p_one_month"], out["p_three_month"] = r["one_month"]["p_one"], r["three_month"]["p_one"]
        out["volume_by_year"] = r.get("twd_volume_by_year", {})
    return out, l


def figure(lev, long=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    panels = [(lev, 5, "")] if long is None else [(long, 20, "(a) Since March 2020, 20-day moving average"),
                                                  (lev, 5, "(b) July 2025 to June 2026, five-day moving average")]
    fig, axes = plt.subplots(len(panels), 1, figsize=(6.2, 2.9 if long is None else 5.2), squeeze=False)
    for ax, (data, win, title) in zip(axes[:, 0], panels):
        sm = data.rolling(win, min_periods=1).mean() / 100
        ax.plot(sm.index, sm["TWD"], "k-", lw=1.2, label="Taiwan dollar")
        ax.plot(sm.index, sm["peers"], color="0.55", lw=1.0, label="Average of won, rupee and offshore renminbi")
        ax.axhline(0, color="0.3", lw=0.5)
        for d in ("2025-11-21", "2025-12-23", "2026-01-29"):
            ax.axvline(pd.Timestamp(d), color="0.5", ls="--", lw=0.8)
        ax.set_ylabel("Per cent a year")
        if title:
            ax.set_title(title, fontsize=8, loc="left")
        ax.tick_params(axis="x", labelrotation=45 if not title else 0, labelsize=7)
        ax.spines[["top", "right"]].set_visible(False)
    axes[-1, 0].legend(frameon=False, fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "fig_futures.pdf"))


def bp0(x):
    return "0" if abs(x) < 0.5 else fmt(x, 0)


def main():
    if "--history" in sys.argv:
        try:
            hist = download_history()
            fx_all = pd.concat([hist, pd.read_csv(CACHE)], ignore_index=True).drop_duplicates(["FILE_DATE", "SERIES"])
            fx_all["FILE_DATE"] = pd.to_datetime(fx_all["FILE_DATE"], format="mixed")
            res = long_sample(fx_all)
            json.dump(res, open(os.path.join(RESULTS, "futures_long_results.json"), "w"), indent=1)
            w = res["window"]
            print(f"Long sample from {res['three_month']['start']}: announcement windows p {res['one_month']['p_one']:.2f} and "
                  f"{res['three_month']['p_one']:.2f}; proposal-to-year-end change exceeded in {100 * w['share']:.1f} per cent of "
                  f"{w['n_windows']} windows ({w['nonoverlap_as_large']} of {w['n_nonoverlap']} non-overlapping).")
        except Exception as err:
            print(f"Long futures sample not built ({err.__class__.__name__}: {err}). Results not written.")
            return False
        return True
    if glob.glob(os.path.join(DATA, "ndf_input.*")):
        print("data/ndf_input.* present: futures test skipped in favour of the NDF test.")
        return True
    try:
        fx = pd.read_csv(CACHE) if os.path.exists(CACHE) else download()
    except Exception as err:
        print(f"SGX futures data not downloaded ({err.__class__.__name__}: {err}). Results not written.")
        return False
    need = {"COM", "COM_MM", "COM_YY", "SETTLE", "VOLUME", "FILE_DATE"}
    if not need <= set(fx.columns):
        print("SGX file layout not recognised; data/sgx_sample.csv saved for inspection. Results not written.")
        return False
    lev1, chg1 = panel(fx, 1)
    lev3, chg3 = panel(fx, 3)
    if len(chg1) < 150:
        print("No usable TWD/USD futures series in the SGX files (see data/sgx_sample.csv). Results not written.")
        return False
    # sign convention in the tests: a positive change is a narrowing of the discount
    r1 = event_study(-chg1["TWD"], -chg1["peers"])
    r3 = event_study(-chg3["TWD"], -chg3["peers"])
    w = window_change(lev3)
    m3, m1 = lev3.resample("ME").mean(), lev1.resample("ME").mean()
    tw = fx[fx["COM"].astype(str).str.strip() == TWD[0]].copy()
    tw["rank"] = tw.groupby("FILE_DATE").cumcount()
    traded = float((tw[tw["rank"] < 2].groupby("FILE_DATE")["VOLUME"].sum() > 0).mean())
    res = {"one_month": r1, "three_month": r3, "window": w, "share_days_traded": traded,
           "monthly_three_month": {str(k.date())[:7]: {"TWD": float(v["TWD"]), "peers": float(v["peers"])} for k, v in m3.iterrows()},
           "monthly_one_month": {str(k.date())[:7]: {"TWD": float(v["TWD"]), "peers": float(v["peers"])} for k, v in m1.iterrows()}}
    json.dump(res, open(os.path.join(RESULTS, "futures_results.json"), "w"), indent=1)
    lev3.round(1).to_csv(os.path.join(RESULTS, "futures_discount_three_month.csv"))
    hs = history_stats()
    hist, long_lev = hs if hs else (None, None)
    if hist:
        res["history"] = hist
        json.dump(res, open(os.path.join(RESULTS, "futures_results.json"), "w"), indent=1)
    figure(lev3, long_lev[long_lev.index >= lev3.index[0] - pd.Timedelta(days=2000)] if hist else None)

    peer_names = "the Korean won, the Indian rupee and the offshore renminbi"
    c1, c3, p1, p3 = r1["cum"], r3["cum"], r1["p_one"], r3["p_one"]

    lines = [r"\begin{figure}[htbp]", r"\centering", r"\includegraphics[width=0.86\textwidth]{results/fig_futures.pdf}",
             (r"\caption{Dollar's three-month forward discount implied by Singapore Exchange currency futures. "
              r"Annualised difference between the settlement prices of the nearest and the fourth contract; "
              r"positive values are a forward discount of the dollar, negative values a premium. Dashed lines mark the industry's "
              r"proposal (21 November 2025), the draft amendment (23 December 2025) and the issuance of the amendment "
              r"(29 January 2026). Source: Singapore Exchange.}\label{fig:futures}"),
             r"\end{figure}", "",
             r"\begin{table}[htbp]", r"\centering", r"\small", r"\begin{threeparttable}",
             r"\caption{Forward discount implied by Taiwan-dollar futures on announcement days}\label{tab:fut}",
             r"\begin{tabular}{@{}lp{5.4cm}cccc@{}}", r"\toprule",
             r" & & \multicolumn{2}{c}{One month} & \multicolumn{2}{c}{Three months} \\",
             r"\cmidrule(lr){3-4}\cmidrule(l){5-6}",
             r"Window & Event & Change (bp) & $p$ & Change (bp) & $p$ \\", r"\midrule"]
    for a, b in zip(r1["events"], r3["events"]):
        d = pd.Timestamp(a["date"]).strftime("%d %b %Y").lstrip("0")
        lines.append(f"{d} & {a['label']} & {bp0(a['abnormal'])} & {a['p']:.2f} & {bp0(b['abnormal'])} & {b['p']:.2f} \\\\")
    lines += [r"\midrule",
              f"\\multicolumn{{2}}{{@{{}}l}}{{Sum over the six windows}} & {fmt(c1, 0)} & & {fmt(c3, 0)} & \\\\",
              f"\\multicolumn{{2}}{{@{{}}l}}{{Randomisation $p$, one-sided}} & {p1:.2f} & & {p3:.2f} & \\\\",
              f"\\multicolumn{{2}}{{@{{}}l}}{{Standard deviation of non-event windows}} & {r1['sd_window']:.0f} & & {r3['sd_window']:.0f} & \\\\",
              r"\bottomrule", r"\end{tabular}", r"\begin{tablenotes}", r"\footnotesize",
              (r"\item Notes: Two-day narrowing of the dollar's annualised forward discount against the Taiwan dollar, in "
               r"basis points, implied by the settlement prices of Singapore Exchange TWD/USD futures: nearest contract "
               r"against the next (one month) and against the fourth (three months). Changes are net of the average change "
               f"for futures on {peer_names} times the regression slope ({r1['beta']:.2f} and {r3['beta']:.2f}). A positive "
               r"value means the discount narrowed. Inference as in Table~\ref{tab:spot}. "
               f"Sample {pd.Timestamp(r1['start']).strftime('%d %B %Y').lstrip('0')} to "
               f"{pd.Timestamp(r1['end']).strftime('%d %B %Y').lstrip('0')} ({r1['n_days']} trading days). Source: Singapore Exchange."),
              r"\end{tablenotes}", r"\end{threeparttable}", r"\end{table}"]
    open(os.path.join(RESULTS, "results_futures.tex"), "w").write("\n".join(lines) + "\n")
    print(f"Futures results written: discount {w['twd_from']:.0f} bp on {w['from']} to {w['twd_to']:.0f} bp on "
          f"{w['to']} (peers {w['peers']:+.0f}); event windows {c1:+.0f} bp (p {p1:.2f}) and {c3:+.0f} bp (p {p3:.2f}).")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
