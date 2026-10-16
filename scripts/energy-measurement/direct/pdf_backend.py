"""Load only an already installed PDF module; never add all user packages to sys.path."""
from pathlib import Path
import sys,importlib,importlib.util

def load_pdf():
    try:return importlib.import_module('pymupdf')
    except ModuleNotFoundError as first:
        if first.name!='pymupdf':raise
    # Earlier Twix run installed PyMuPDF in the user site. Reuse only this package,
    # without also exposing the incompatible user-site NumPy/Matplotlib pair.
    init=Path.home()/f'.local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages/pymupdf/__init__.py'
    if init.is_file():
        spec=importlib.util.spec_from_file_location('pymupdf',init,submodule_search_locations=[str(init.parent)])
        module=importlib.util.module_from_spec(spec);sys.modules['pymupdf']=module
        try:spec.loader.exec_module(module);return module
        except Exception:
            sys.modules.pop('pymupdf',None);raise
    try:return importlib.import_module('fitz')
    except ImportError as e:raise RuntimeError('PyMuPDF fehlt in der gewählten Umgebung und im bekannten User-Verzeichnis. Keine Pakete wurden verändert.') from e
