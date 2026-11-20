"""Shared settings and helpers for the event studies."""
import os
import numpy as np
import pandas as pd

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(BASE, "data")
RESULTS = os.path.join(BASE, "results")
os.makedirs(RESULTS, exist_ok=True)

SAMPLE_START, SAMPLE_END = "2025-07-01", "2026-06-30"

# Dated by first public information (Taipei time); windows cover that day and the next.
EVENTS = [
    ("2025-09-16", "Industry asks members to develop accounting relief"),
    ("2025-11-21", "Industry association proposes the change"),
    ("2025-12-18", "Regulator reports to the legislature; public hearing"),
    ("2025-12-23", "Draft amendment published"),
    ("2026-01-21", "First insurer resolves to adopt"),
    ("2026-01-29", "Amendment issued; large insurers adopt"),
]

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}&cosd={start}&coed={end}"


def fred(code, start=SAMPLE_START, end=SAMPLE_END):
    """Download one FRED daily series."""
    df = pd.read_csv(FRED_URL.format(code=code, start=start, end=end))
    df.columns = ["date", code]
    df["date"] = pd.to_datetime(df["date"])
    df[code] = pd.to_numeric(df[code], errors="coerce")
    return df.set_index("date")[code]


def event_study(target, peer, n_draws=20000, seed=42):
    """Peer-adjusted two-day abnormal changes on event windows, with randomisation inference.

    target, peer: daily changes on a common index (non-missing).
    Returns dict with beta, per-event raw/abnormal changes and p-values, cumulative effect.
    """
    idx = target.index
    beta = float(np.polyfit(peer.values, target.values, 1)[0]) if float(np.abs(peer.values).sum()) > 0 else 0.0
    ab = target - beta * peer
    starts, rows = [], []
    for d, label in EVENTS:
        i = int(idx.searchsorted(pd.Timestamp(d)))
        starts.append(i)
        rows.append({"date": d, "label": label,
                     "raw": float(target.iloc[i:i + 2].sum()),
                     "abnormal": float(ab.iloc[i:i + 2].sum())})
    used = set()
    for i in starts:
        used.update({i, i + 1})
    placebo = np.array([ab.iloc[i:i + 2].sum() for i in range(len(ab) - 1)
                        if i not in used and i + 1 not in used])
    for r in rows:
        r["p"] = float((np.abs(placebo) >= abs(r["abnormal"])).mean())
    cum = float(sum(r["abnormal"] for r in rows))
    rng = np.random.default_rng(seed)
    sims = np.array([rng.choice(placebo, size=len(EVENTS), replace=False).sum() for _ in range(n_draws)])
    return {"beta": beta, "events": rows, "cum": cum,
            "p_one": float((sims >= cum).mean()), "p_two": float((np.abs(sims) >= abs(cum)).mean()),
            "sd_window": float(placebo.std(ddof=1)), "n_placebo": int(len(placebo)),
            "n_days": int(len(target)), "start": str(idx.min().date()), "end": str(idx.max().date())}


def fmt(x, nd=2, sign=True):
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace("-", "$-$") if s.startswith("-") else s
