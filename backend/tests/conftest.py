import os
import sys
from pathlib import Path

# The matching tests are pure Python and never touch the database.
os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
