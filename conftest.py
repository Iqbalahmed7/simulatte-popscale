"""PopScale pytest configuration — sets up sys.path for all tests.

Path strategy (no namespace collision):
  - PopScale root → `popscale.*` resolves to PopScale modules
  - PG root       → `src.*` resolves to PG modules (PG's internal convention)
"""
import sys
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parent
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"

if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))

if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))
