# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
"""
Compatibility shim for setuptools >= 82 which removed pkg_resources.

Patches third-party libraries (e.g. coreapi) that still import pkg_resources
to use importlib.metadata instead. Must be called before those libraries are
imported.
"""
import importlib.metadata
import sys
import types


def _make_pkg_resources_shim():
    """Create a minimal pkg_resources shim module with iter_entry_points."""
    mod = types.ModuleType("pkg_resources")
    mod.__doc__ = "Minimal shim for setuptools >= 82 compatibility"

    def iter_entry_points(group, name=None):
        """Replacement for pkg_resources.iter_entry_points using importlib.metadata."""
        eps = importlib.metadata.entry_points()
        # importlib.metadata.entry_points() returns a dict-like (3.12+) or SelectableGroups
        if hasattr(eps, "select"):
            selected = eps.select(group=group)
        elif isinstance(eps, dict):
            selected = eps.get(group, [])
        else:
            selected = [ep for ep in eps if ep.group == group]

        for ep in selected:
            if name is None or ep.name == name:
                # Wrap to match pkg_resources EntryPoint interface
                wrapper = types.SimpleNamespace(
                    name=ep.name,
                    load=ep.load,
                    dist=getattr(ep, "dist", None),
                )
                yield wrapper

    mod.iter_entry_points = iter_entry_points
    return mod


def install_pkg_resources_shim():
    """Install a pkg_resources shim if the real one is not available."""
    try:
        import pkg_resources  # noqa: F401
    except ImportError:
        sys.modules["pkg_resources"] = _make_pkg_resources_shim()
