import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dashboard"))
os.environ.setdefault("SESSION_SECRET", "x" * 40)
