#!/usr/bin/env python3
"""The canonical runner is drama.py; require an explicit episode and run name."""
import sys
from drama import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit("Use drama.py --project PROJECT render --episode ep01 --run take01; see drama.py --help")
    sys.exit(main())
