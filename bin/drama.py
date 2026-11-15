#!/usr/bin/env python3
"""Run the same self-contained workflow shipped in the skill."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/continuous-video-drama/scripts"))
from drama import main

if __name__ == "__main__":
    sys.exit(main())
