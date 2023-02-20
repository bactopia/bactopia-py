import glob
import os
from pathlib import Path

modules = Path(__file__).parent.glob("*.py")
__all__ = [
    str(f.name)[:-3]
    for f in modules
    if f.is_file() and not str(f).endswith("__init__.py")
]
del modules
del glob
del os

from bactopia.parsers import *
