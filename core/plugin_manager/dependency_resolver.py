"""Dependency resolver (PRD §18.3).

A tiny semver-style resolver for plugin dependencies. It does
**not** implement full PEP 440 — it supports the subset that
matters for the platform:

* ``"1.2.3"``        — exact match
* ``">=1.2.0"``      — greater-or-equal
* ``"<2.0"``         — less-than
* ``"^1.2"``         — compatible (>=1.2, <2.0)
* ``"~1.2.3"``       — patch-level (>=1.2.3, <1.3.0)

Constraints are written per plugin in ``manifest.yaml``:

.. code-block:: yaml

    dependencies:
      plugins:
        dingtalk_adapter: ">=1.0.0"

The resolver is intentionally a class (not a global) so multiple
plugin manager instances can run side by side in tests.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ResolutionError(ValueError):
    """Raised when dependencies cannot be satisfied."""


def _parse_version(spec: str) -> Tuple[int, int, int]:
    parts = spec.strip().split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise ResolutionError(f"invalid version: {spec}") from exc


_VERSION_RE = re.compile(r"^(>=|<=|==|~|\^|<|>)?\s*(\d+(?:\.\d+){0,2})$")


def _parse_constraint(spec: str) -> Tuple[str, Tuple[int, int, int]]:
    """Return (op, version). op ∈ {>=,<=,==,~,^,<,>}."""

    m = _VERSION_RE.match(spec.strip())
    if not m:
        raise ResolutionError(f"invalid constraint: {spec}")
    op = m.group(1) or "=="
    return op, _parse_version(m.group(2))


def _check(op: str, want: Tuple[int, int, int], have: Tuple[int, int, int]) -> bool:
    if op == "==":
        return have == want
    if op == ">=":
        return have >= want
    if op == "<=":
        return have <= want
    if op == ">":
        return have > want
    if op == "<":
        return have < want
    if op == "^":  # >=want, same major
        return have >= want and have[0] == want[0]
    if op == "~":  # >=want, same major.minor
        return have >= want and have[0] == want[0] and have[1] == want[1]
    raise ResolutionError(f"unknown op: {op}")


@dataclass
class _PluginSpec:
    name: str
    version: str
    constraints: Dict[str, str] = field(default_factory=dict)


class DependencyResolver:
    """Holds all registered plugin specs and resolves their order."""

    def __init__(self) -> None:
        self._specs: Dict[str, _PluginSpec] = {}

    def add(self, name: str, version: str, constraints: Optional[Dict[str, str]] = None) -> None:
        self._specs[name] = _PluginSpec(name=name, version=version, constraints=dict(constraints or {}))

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #

    def resolve(self, root: Optional[str] = None) -> List[str]:
        """Return a topological order of plugin names, raising on conflict."""

        if not self._specs:
            return []
        roots: List[str]
        if root is not None:
            roots = [root]
        else:
            roots = sorted(self._specs.keys())

        visited: Dict[str, str] = {}  # name -> "white"/"gray"/"black"
        order: List[str] = []

        def visit(name: str, stack: List[str]) -> None:
            if visited.get(name) == "black":
                return
            if visited.get(name) == "gray":
                cycle = " -> ".join(stack + [name])
                raise ResolutionError(f"cycle: {cycle}")
            visited[name] = "gray"
            spec = self._specs.get(name)
            if spec is not None:
                for dep_name, constraint in spec.constraints.items():
                    if dep_name not in self._specs:
                        raise ResolutionError(f"missing dep: {dep_name}")
                    self._check_constraint(dep_name, constraint)
                    visit(dep_name, stack + [name])
            visited[name] = "black"
            order.append(name)

        for r in roots:
            visit(r, [])
        return order

    def _check_constraint(self, dep_name: str, constraint: str) -> None:
        op, want = _parse_constraint(constraint)
        have = _parse_version(self._specs[dep_name].version)
        if not _check(op, want, have):
            raise ResolutionError(
                f"{dep_name} {self._specs[dep_name].version} does not satisfy {constraint}"
            )

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def specs(self) -> List[_PluginSpec]:
        return list(self._specs.values())

    def has(self, name: str) -> bool:
        return name in self._specs

    def check(self, name: str, constraint: str) -> bool:
        """Public API: returns True if the registered version satisfies ``constraint``."""

        if name not in self._specs:
            return False
        try:
            self._check_constraint(name, constraint)
            return True
        except ResolutionError:
            return False
