"""Same credential-free diagnostic as the container, using the outbound wrapper."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from app.networkcheck import main

if __name__ == '__main__':
    raise SystemExit(main())
