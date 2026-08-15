"""Shared test setup.

The integration's modules reference each other with relative imports
(``from .const import …``). Loaded flat that fails, and loading them via
``custom_components.lognotifier`` would drag in ``__init__.py`` together with
Home Assistant. The directory is therefore registered here as a package of its
own, without executing its ``__init__.py``: relative imports resolve, the HA
dependency stays out.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "lognotifier"

# The name is deliberately not "lognotifier": it must not collide with a real
# package that someone installed alongside.
PACKAGE = "lognotifier_component"


def register_package() -> None:
    """Register the component directory as an importable package."""
    if PACKAGE in sys.modules:
        return
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(COMPONENT)]
    sys.modules[PACKAGE] = package


register_package()
