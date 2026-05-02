"""
Initialize metadata save and ensure using the correct version
"""

import os
import sys
from pathlib import Path

pp = str(Path(__file__).parent.parent)
sys.path.insert(0, pp)

os.environ["JSONLITEDB_DISABLE_META"] = "true"  # avoid churn
os.environ["JSONLITEDB_ENABLE_REGEX"] = "1"
