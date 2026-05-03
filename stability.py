"""
Stability core: connectivity path, equilibrium-matrix singularity, one-way support bounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import sympy as sp
from sympy import Matrix


@dataclass
class StabilityReport:
    ok: bool
    messages: list[str]
    collapse_mode: Optional[str]  # e.g. 'Tipping', 'Sliding', 'Mechanism', 'Support lift-off'
    highlight_edges: list[tuple[str, str]] = field(default_factory=list)
    highlight_nodes: list[str] = field(default_factory=list)
    determinant: Optional[float] = None


def _adjacency_from_edges(edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    g: dict[str, set[str]] = {}
    for a, b in edges:
        g.setdefault(a, set()).add(b)
        g.setdefault(b, set()).add(a)
    return g


def connectivity_path_exists(nodes: list[str], edges: list[tuple[str, str]], start: str) -> tuple[bool, set[str]]:
    """BFS from start; all nodes must be reachable."""
    g = _adjacency_from_edges(edges)
    if start not in g and nodes:
        return False, set()
    seen: set[str] = {start}
    q = [start]
    while q:
        u = q.pop()
        for v in g.get(u, ()):
            if v not in seen:
                seen.add(v)
                q.append(v)
    return set(nodes) <= seen, seen


def check_stability(
    *,
    node_ids: list[str],
    structural_edges: list[tuple[str, str]],
    A_sym: Matrix,
    b_sym: Matrix,
    unknown_labels: list[str],
    subs: dict,
    one_way_supports: dict[str, Literal["vertical_up", "vertical_down", "horizontal_left", "horizontal_right", "cable_tension"]],
    det_tol: float = 1e-9,
) -> StabilityReport:
    """
    - Connectivity: all node_ids must lie in one component reachable from first node (or explicit start = node_ids[0]).
    - Singularity: det(A) after subs; zero => mechanism.
    - Boundary: after solve, check one-way reactions (negative in admissible direction => failure).

    one_way_supports maps unknown label -> physical meaning for sign check:
      vertical_up: reaction must be >= 0 (cannot pull ground down / lift-off)
      vertical_down: must be <= 0
      horizontal_right: must be >= 0
      horizontal_left: must be <= 0
      cable_tension: must be >= 0 (slack if negative)
    """
    messages: list[str] = []
    highlight_edges: list[tuple[str, str]] = []
    highlight_nodes: list[str] = []
    collapse_mode: Optional[str] = None
    det_val: Optional[float] = None

    start = node_ids[0] if node_ids else ""
    ok_conn, reached = connectivity_path_exists(node_ids, structural_edges, start)
    if not ok_conn:
        missing = set(node_ids) - reached
        messages.append(
            f"SYSTEM COLLAPSED: CONNECTIVITY — discontinuous structure; unreachable nodes: {sorted(missing)}"
        )
        # highlight a gap: any edge that would bridge — we highlight nodes not reached
        highlight_nodes.extend(sorted(missing))
        return StabilityReport(
            ok=False,
            messages=messages,
            collapse_mode="Disconnected geometry",
            highlight_edges=highlight_edges,
            highlight_nodes=highlight_nodes,
            determinant=None,
        )

    A_num = Matrix(A_sym.subs(subs).evalf())
    for i in range(A_num.rows):
        for j in range(A_num.cols):
            v = sp.N(A_num[i, j])
            if not (v.is_real and v.is_finite):
                messages.append("SYSTEM COLLAPSED: INVALID INPUT DOMAIN (non-real/non-finite equilibrium matrix).")
                return StabilityReport(False, messages, "Invalid input domain", highlight_edges, highlight_nodes, None)
    n = A_num.rows
    if A_num.cols != n:
        messages.append("Equilibrium matrix is not square; singularity check uses rectangular rank.")
        try:
            r = A_num.rank()
            if r < min(A_num.rows, A_num.cols):
                messages.append("SYSTEM COLLAPSED: GEOMETRIC INSTABILITY (Mechanism)")
                collapse_mode = "Mechanism"
                highlight_edges = list(structural_edges)
                return StabilityReport(False, messages, collapse_mode, highlight_edges, highlight_nodes, None)
        except Exception:
            pass
        return StabilityReport(True, messages, None, highlight_edges, highlight_nodes, None)

    try:
        d = A_num.det()
        det_val = float(sp.N(d))
    except Exception:
        det_val = None

    if det_val is not None and abs(det_val) < det_tol:
        messages.append("SYSTEM COLLAPSED: GEOMETRIC INSTABILITY (Mechanism)")
        collapse_mode = "Mechanism"
        highlight_edges = list(structural_edges)
        return StabilityReport(False, messages, collapse_mode, highlight_edges, highlight_nodes, det_val)

    # Solve for boundary check
    b_num = Matrix(b_sym.subs(subs).evalf())
    for i in range(b_num.rows):
        v = sp.N(b_num[i, 0])
        if not (v.is_real and v.is_finite):
            messages.append("SYSTEM COLLAPSED: INVALID INPUT DOMAIN (non-real/non-finite load vector).")
            return StabilityReport(False, messages, "Invalid input domain", highlight_edges, highlight_nodes, det_val)
    try:
        x = A_num.LUsolve(b_num)
    except Exception:
        messages.append("SYSTEM COLLAPSED: GEOMETRIC INSTABILITY (Mechanism)")
        return StabilityReport(False, messages, "Mechanism", highlight_edges, highlight_nodes, det_val)

    vals = {unknown_labels[i]: float(x[i, 0]) for i in range(len(unknown_labels))}

    for label, kind in one_way_supports.items():
        if label not in vals:
            continue
        v = vals[label]
        bad = False
        if kind == "vertical_up" and v < 0:
            bad = True
            collapse_mode = collapse_mode or "Tipping / lift-off at roller"
        elif kind == "vertical_down" and v > 0:
            bad = True
        elif kind == "horizontal_right" and v < 0:
            bad = True
            collapse_mode = collapse_mode or "Sliding"
        elif kind == "horizontal_left" and v > 0:
            bad = True
            collapse_mode = collapse_mode or "Sliding"
        elif kind == "cable_tension" and v < 0:
            bad = True
            collapse_mode = collapse_mode or "Cable slack"
        if bad:
            messages.append("SYSTEM COLLAPSED: SUPPORT FAILURE (Lift-off/Slack)")
            if label == "R_Cy":
                node_guess = "C"
            elif label in ("F_A", "F_B"):
                node_guess = label[-1]
            else:
                node_guess = label.split("_")[-1] if "_" in label else label
            if node_guess not in highlight_nodes:
                highlight_nodes.append(node_guess)

    if messages and any("SUPPORT FAILURE" in m for m in messages):
        return StabilityReport(False, messages, collapse_mode, highlight_edges, highlight_nodes, det_val)

    return StabilityReport(True, ["Structure passes connectivity, determinacy, and one-way support checks."], None, [], [], det_val)
