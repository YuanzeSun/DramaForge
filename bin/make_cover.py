#!/usr/bin/env python3
"""Export a lossless cover crop from approved GPT Image PNG artwork."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/continuous-video-drama/scripts"))
from covers import main

if __name__ == "__main__":
    sys.exit(main())
