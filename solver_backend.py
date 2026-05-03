"""
Symbolic equilibrium solving: SymPy (default) with optional Wolfram Client.
No closed-form hard-coded force formulas — unknowns come from matrix solution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import sympy as sp
from sympy import Matrix


@dataclass
class SolveResult:
    unknown_labels: list[str]
    equations_display: list[str]
    matrix_A: Matrix
    vector_b: Matrix
    solution_numeric: dict[str, float]
    solution_symbolic: dict[str, sp.Expr]
    used_wolfram: bool
    wolfram_note: str
    is_numeric_case: bool


def _try_wolfram_solve(A_list: list[list[float]], b_list: list[float]) -> Optional[list[float]]:
    kernel_path = os.environ.get("WOLFRAM_KERNEL_PATH", "").strip()
    if not kernel_path or not os.path.isfile(kernel_path):
        return None
    try:
        from wolframclient.evaluation import WolframLanguageSession
        from wolframclient.language import wl

        with WolframLanguageSession(kernel=kernel_path) as session:
            x_wl = session.evaluate(wl.LinearSolve(A_list, b_list))
        if x_wl is None:
            return None
        if isinstance(x_wl, (list, tuple)):
            return [float(v) for v in x_wl]
        if hasattr(x_wl, "args"):
            return [float(v) for v in x_wl.args]
        return None
    except Exception:
        return None


def _is_numeric_matrix(m: Matrix) -> bool:
    for i in range(m.rows):
        for j in range(m.cols):
            v = sp.simplify(m[i, j])
            if v.free_symbols:
                return False
            try:
                float(v)
            except Exception:
                return False
    return True


def build_and_solve(
    A_sym: Matrix,
    b_sym: Matrix,
    unknowns: list[sp.Symbol],
    subs: dict[sp.Symbol, sp.Expr],
    *,
    equation_rows_meta: Optional[list[tuple[str, str]]] = None,
) -> SolveResult:
    """Substitute params (numeric or symbolic) and solve A x = b."""
    A_sub = Matrix(A_sym.subs(subs))
    b_sub = Matrix(b_sym.subs(subs))

    labels = [str(u) for u in unknowns]
    equations_display: list[str] = []
    if equation_rows_meta and len(equation_rows_meta) == A_sub.rows:
        for i, (title, lhs_text) in enumerate(equation_rows_meta):
            equations_display.append(f"{title}: {lhs_text} = {sp.simplify(b_sub[i])}")
    else:
        for i in range(A_sub.rows):
            terms = []
            for j, u in enumerate(unknowns):
                terms.append(f"({sp.simplify(A_sub[i, j])})·{u}")
            equations_display.append(f"Row {i + 1}: {' + '.join(terms)} = {sp.simplify(b_sub[i])}")

    try:
        x_sym = A_sub.LUsolve(b_sub)
        sol_sym = {str(unknowns[i]): sp.simplify(x_sym[i]) for i in range(len(unknowns))}
    except Exception:
        sol_sym = {str(u): sp.Symbol(f"unsolved_{u}") for u in unknowns}

    is_numeric_case = _is_numeric_matrix(A_sub) and _is_numeric_matrix(b_sub)
    used_wolfram = False
    wolfram_note = ""
    sol_num: dict[str, float] = {}

    if is_numeric_case:
        A_f = Matrix(A_sub.evalf())
        b_f = Matrix(b_sub.evalf())
        wl = _try_wolfram_solve(
            [[float(A_f[i, j]) for j in range(A_f.cols)] for i in range(A_f.rows)],
            [float(b_f[i, 0]) for i in range(b_f.rows)],
        )
        if wl is not None and len(wl) == len(unknowns):
            used_wolfram = True
            wolfram_note = "Solved using Wolfram Kernel (LinearSolve)."
            sol_num = {labels[i]: float(wl[i]) for i in range(len(labels))}
        else:
            if os.environ.get("WOLFRAM_KERNEL_PATH"):
                wolfram_note = "WOLFRAM_KERNEL_PATH set but Wolfram solve failed; used SymPy."
            else:
                wolfram_note = "SymPy numerical solve (set WOLFRAM_KERNEL_PATH for Wolfram Kernel)."
            try:
                x_num = A_f.LUsolve(b_f)
                sol_num = {labels[i]: float(x_num[i]) for i in range(len(labels))}
            except Exception:
                wolfram_note += " Numeric solve failed (singular or ill-conditioned)."
                sol_num = {labels[i]: float("nan") for i in range(len(labels))}
    else:
        wolfram_note = "Symbolic solve mode (inputs include variables)."

    return SolveResult(
        unknown_labels=labels,
        equations_display=equations_display,
        matrix_A=A_sub,
        vector_b=b_sub,
        solution_numeric=sol_num,
        solution_symbolic=sol_sym,
        used_wolfram=used_wolfram,
        wolfram_note=wolfram_note,
        is_numeric_case=is_numeric_case,
    )
