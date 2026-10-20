"""Run the EMSR533 validation with no arguments: `python Run_Comparison.py` (or press Run in your IDE).

Defaults to the August 2021 Kabylie event (the only event with EMSR533 reference maps). Extra arguments are passed
through to scripts/validate_emsr.py, e.g.:

    python Run_Comparison.py --csv data/raw/firms_kabylie.csv     # offline, no API call
"""
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "src"))
if len(sys.argv) == 1:
    sys.argv += ["--event", "2021-08-08", "2021-08-16"]
runpy.run_path(str(root / "scripts" / "validate_emsr.py"), run_name="__main__")
