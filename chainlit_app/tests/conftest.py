"""Tests of the Chainlit side (spec 020): the data layer and the resume hook, against a fake Indico."""

import os
import sys
from pathlib import Path

os.environ.setdefault("CHAINLIT_AUTH_SECRET", "test-secret-" + "x" * 32)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
