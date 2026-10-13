"""
selectors.py — Centralized selector registry and stdlib-safe forwarder.

Provides all DOM selectors for LinkedIn profile components from dom_selectors.py,
while transparently providing standard library selectors attributes if shadowed by sys.path[0].
"""

import sys
import os
import importlib.util

# 1. Provide stdlib selectors attributes if imported by socket/asyncio/playwright
_stdlib_path = os.path.join(sys.base_prefix, "Lib", "selectors.py")
if os.path.isfile(_stdlib_path):
    try:
        _spec = importlib.util.spec_from_file_location("_real_stdlib_selectors", _stdlib_path)
        if _spec and _spec.loader:
            _real_selectors = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_real_selectors)
            for _attr in dir(_real_selectors):
                if not _attr.startswith("__"):
                    globals()[_attr] = getattr(_real_selectors, _attr)
    except Exception:
        pass

# 2. Re-export all DOM selectors from dom_selectors.py
try:
    from skills.profile_scraper.dom_selectors import *
except ImportError:
    try:
        from dom_selectors import *
    except ImportError:
        pass
