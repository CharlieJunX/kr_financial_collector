"""Run the European collector from any working directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kr_financial_collector.eu_collector import main

if __name__ == "__main__":
    raise SystemExit(main())
