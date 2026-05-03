"""
Problem setups: symbolic equilibrium matrix A x = b (no closed-form force formulas).
"""

from __future__ import annotations

from dataclasses import dataclass

import sympy as sp
from sympy import Matrix, cos, sin, sqrt


@dataclass
class ProblemSetup:
    name: str
    unknowns: list[sp.Symbol]
    A: Matrix
    b: Matrix
    subs_keys: list[sp.Symbol]
    equation_meta: list[tuple[str, str]]
    node_ids: list[str]
    structural_edges: list[tuple[str, str]]
    one_way: dict[str, str]
    fbd_kind: str


def setup_flagpole() -> ProblemSetup:
    """
    Hinge O with frame triangle OAB (sides OA, OB, AB);
    cable tension scalar T (sign flips arrow): force on the body at A pulls toward D,
    with cable direction from horizontal angle θ (deg), θ = angle of D→A with +x.
    """
    L_OA, L_OB, L_AB, T_mag, theta_c_deg = sp.symbols("L_OA L_OB L_AB T theta_c", real=True)
    R_Ox, R_Oy = sp.symbols("R_Ox R_Oy", real=True)

    theta_r = sp.pi * theta_c_deg / 180
    # Unit vector D → A; tension on pin at A is toward D: −|direction| * T with T signed
    F_Ax = -T_mag * cos(theta_r)
    F_Ay = -T_mag * sin(theta_r)

    # O = (0, 0), B = (L_OB, 0), A from circle-circle intersection:
    # x_A from law of cosines projection and y_A >= 0 branch.
    x_A = (L_OA**2 + L_OB**2 - L_AB**2) / (2 * L_OB)
    y_A = sqrt(L_OA**2 - x_A**2)

    eq1 = R_Ox + F_Ax
    eq2 = R_Oy + F_Ay

    A = Matrix(
        [
            [sp.diff(eq1, R_Ox), sp.diff(eq1, R_Oy)],
            [sp.diff(eq2, R_Ox), sp.diff(eq2, R_Oy)],
        ]
    )
    b = Matrix([[-F_Ax], [-F_Ay]])

    eq_meta = [
        ("ΣFx = 0", "R_Ox"),
        ("ΣFy = 0", "R_Oy"),
    ]

    edges = [("O", "A"), ("A", "B"), ("B", "O")]
    nodes = ["O", "A", "B"]

    return ProblemSetup(
        name="Flagpole & frame (2/49 style)",
        unknowns=[R_Ox, R_Oy],
        A=A,
        b=b,
        subs_keys=[L_OA, L_OB, L_AB, T_mag, theta_c_deg],
        equation_meta=eq_meta,
        node_ids=nodes,
        structural_edges=edges,
        one_way={},
        fbd_kind="flagpole",
    )


def setup_clamp() -> ProblemSetup:
    """Top jaw: load P at x=0 (+P = downward on jaw in +y up coords). Screws at L1 and L1+L2."""
    L1, L2, P = sp.symbols("L1 L2 P", real=True)
    F_A, F_B = sp.symbols("F_A F_B", real=True)

    A = Matrix([[1, 1], [0, L2]])
    b = Matrix([[P], [P * L1]])

    eq_meta = [
        ("ΣFy = 0", "F_A + F_B"),
        ("ΣM_A = 0", "F_B·L2"),
    ]

    nodes = ["tip", "A", "B"]
    edges = [("tip", "A"), ("A", "B")]

    return ProblemSetup(
        name="Wood clamp (3/8 style)",
        unknowns=[F_A, F_B],
        A=A,
        b=b,
        subs_keys=[L1, L2, P],
        equation_meta=eq_meta,
        node_ids=nodes,
        structural_edges=edges,
        one_way={},
        fbd_kind="clamp",
    )
