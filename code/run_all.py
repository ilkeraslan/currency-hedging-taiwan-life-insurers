"""Run every step of the analysis.

    python code/run_all.py              uses the local copies of the FRED series in data/
    python code/run_all.py --download   re-downloads the FRED series first and adds the long-sample check

1. Spot event study (Table 4) from FRED noon buying rates.
2. Share-price event study from Yahoo Finance prices (needs yfinance and internet access).
3. Futures evidence (Section 5.4, Figure 2, Table 6) from Singapore Exchange settlement files, which are
   downloaded on first use (about 260 small files) and cached in data/.
4. Interbank turnover (Table 7) from the central bank's monthly releases.
5. Figure 1 from the regulator's monthly statistics.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args):
    print(f"\n=== {' '.join(args)}")
    subprocess.run([sys.executable, os.path.join(HERE, args[0])] + args[1:], check=False)


run(["spot_event_study.py"] + (["--download"] if "--download" in sys.argv else []))
run(["equity_event_study.py"])
run(["futures_event_study.py", "--history"])
run(["futures_event_study.py"])
run(["turnover.py"])
run(["make_figure.py"])
