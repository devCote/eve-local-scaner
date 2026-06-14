# Allow running this script from tools/ while importing runtime modules from project root.
from pathlib import Path as _Path
import sys as _sys
_ROOT = _Path(__file__).resolve().parents[2]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from esi_client import get_character_id

name = input("Pilot name: ")

character_id = get_character_id(name)

print("Character ID:", character_id)
