"""Run the project from its own folder without requiring a package install."""
from pathlib import Path
import sys

# Add the parent of this project folder so its package name resolves even when
# the current working directory is elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kr_financial_collector.main import main

if __name__ == "__main__":
    raise SystemExit(main())
