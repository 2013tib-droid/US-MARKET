import sys
from pathlib import Path

# Supaya `import usmarket` jalan tanpa memasang paketnya.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
