"""Test-level conftest — ensures sys.path is set up before any test module imports.

Path strategy (no namespace collision):
  - PopScale root → `popscale.*` resolves to PopScale modules
  - PG root       → `src.*` resolves to PG modules (PG's internal convention)
"""
import sys
from pathlib import Path

_TESTS_DIR     = Path(__file__).parent
_POPSCALE_ROOT = _TESTS_DIR.parent
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"

if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))

if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))
