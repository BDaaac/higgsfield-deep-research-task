"""Auto-load all metric plugins so they register themselves."""

import importlib
import pathlib

from metrics.base import METRIC_REGISTRY, BaseMetric, register_metric  # noqa: F401

_here = pathlib.Path(__file__).parent
for _path in sorted(_here.glob("*.py")):
    if _path.stem not in ("__init__", "base"):
        importlib.import_module(f"metrics.{_path.stem}")
