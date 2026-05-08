"""
Statics Presentation App: Streamlit + SymPy (+ optional Wolfram Kernel) matrix equilibrium.
"""

from __future__ import annotations

import io
import math
import re

import matplotlib.pyplot as plt
import streamlit as st
import sympy as sp

from fbd import draw_clamp_fbd, draw_centroid_diagram, draw_flagpole_fbd, draw_parallel_axis_diagram
from models import setup_clamp, setup_flagpole
from solver_backend import build_and_solve
from stability import check_stability

_RAW_SYMBOL_TO_SAFE: dict[str, str] = {}
_SAFE_SYMBOL_USED: set[str] = set()


def _safe_symbol_name(raw_token: str) -> str:
    if raw_token in _RAW_SYMBOL_TO_SAFE:
        return _RAW_SYMBOL_TO_SAFE[raw_token]

    base = re.sub(r"\W", "_", raw_token).strip("_")
    if not base:
        base = "sym"
    if not (base[0].isalpha() or base[0] == "_"):
        base = f"sym_{base}"

    candidate = base
    idx = 1
    while candidate in _SAFE_SYMBOL_USED:
        idx += 1
        candidate = f"{base}_{idx}"

    _RAW_SYMBOL_TO_SAFE[raw_token] = candidate
    _SAFE_SYMBOL_USED.add(candidate)
    return candidate


def _normalize_expression_with_symbol_map(text: str) -> tuple[str, dict[str, sp.Symbol]]:
    # Insert explicit multiplication for adjacent numeric/symbol tokens and for ")x".
    normalized = text.replace("^", "**")
    normalized = re.sub(r"(?<=\d)(?=[^\d\.\s\+\-\*/\^\(\)])", "*", normalized)
    normalized = re.sub(r"(?<=\))(?=[^\s\+\-\*/\^\)])", "*", normalized)

    # Symbol/function names that should keep native SymPy meaning.
    reserved = {"pi", "E", "I", "sin", "cos", "tan", "sqrt", "log", "ln", "exp", "Abs"}
    local_dict: dict[str, sp.Symbol] = {}

    token_pattern = re.compile(r"[^\s\+\-\*/\^\(\)\$#%]+")

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        if re.fullmatch(r"\d+(\.\d+)?|\.\d+", token):
            return token
        if token in reserved:
            return token
        safe = _safe_symbol_name(token)
        local_dict[safe] = sp.Symbol(token)
        return safe

    normalized = token_pattern.sub(repl, normalized)
    return normalized, local_dict


def _setup_for_choice(choice: str):
    if choice.startswith("Flagpole"):
        return setup_flagpole()
    return setup_clamp()


def _parse_expr(label: str, raw: str):
    text = raw.strip()
    if not text:
        return None, f"Invalid input for {label}: value cannot be empty."
    
    try:
        # Check if it's a purely numeric arithmetic expression (without quotes)
        is_numeric_charset = bool(re.fullmatch(r"[0-9\.\+\-\*/\(\)\s\^]+", text))
        has_digit = bool(re.search(r"\d", text))
        
        if is_numeric_charset and has_digit:
            # Try to evaluate numeric expressions like 3+2 -> 5 (without quotes)
            try:
                # Use eval for simple arithmetic, then convert to sympy
                result = eval(text)
                # Check for division by zero or infinity
                if result == float('inf') or result == float('-inf'):
                    return None, f"Invalid input for {label}: division by zero is not allowed."
                return sp.sympify(result), None
            except ZeroDivisionError:
                return None, f"Invalid input for {label}: division by zero is not allowed."
            except:
                # If eval fails, treat as symbolic input (don't show error)
                pass
        else:
            # Handle symbolic expressions
            # If the input is quoted, treat it as a literal string
            if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
                # Remove quotes and treat as a literal string symbol
                content = text[1:-1]
                expr = sp.Symbol(content)
            else:
                normalized, local_dict = _normalize_expression_with_symbol_map(text)
                expr = sp.sympify(normalized, locals=local_dict, evaluate=False)

        if _has_non_finite(expr):
            if "/" in normalized:
                return None, f"Invalid input for {label}: division by zero is not allowed."
            return None, f"Invalid input for {label}: expression evaluates to a non-finite value."
        return expr, None
    except Exception:
        # Final fallback: accept any non-empty raw token as a symbolic label.
        # This keeps the app permissive for special inputs like "+", "-", "/", etc.
        return sp.Symbol(text), None


def _is_numeric_expr(expr: sp.Expr) -> bool:
    return not expr.free_symbols


def _to_float(expr: sp.Expr) -> float:
    return float(sp.N(expr))


def _is_real_finite_numeric(expr: sp.Expr) -> bool:
    if expr.free_symbols:
        return False
    v = sp.N(expr)
    return bool(v.is_real and v.is_finite)


def _has_non_finite(expr: sp.Expr) -> bool:
    v = sp.simplify(expr)
    return bool(v.has(sp.zoo) or v.has(sp.oo) or v.has(-sp.oo) or v.has(sp.nan))


def _latex_symbol_name(raw: str) -> str:
    replacements = {
        "\\": r"\backslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "#": r"\#",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    escaped = "".join(replacements.get(ch, ch) for ch in raw)
    return r"\text{" + escaped + "}"


def _round_numerical_coeffs(expr: sp.Expr) -> sp.Expr:
    """Round numerical coefficients in symbolic expressions intelligently."""
    def round_atom(atom):
        if isinstance(atom, sp.Float):
            val = float(atom)
            # For reasonable-sized numbers, use 6 significant figures then format cleanly
            # For very large/small numbers, let SymPy choose scientific notation
            if abs(val) > 1e-4 and abs(val) < 1e10:
                # Round to 6 sig figs for display, but show as regular decimal if reasonable
                rounded = float(f"{val:.6g}")
                return sp.Float(rounded)
            else:
                return sp.N(atom, 6)
        return atom
    return expr.replace(lambda atom: isinstance(atom, sp.Float), round_atom)


def _latex_expr(expr: sp.Expr, **kwargs) -> str:
    # Round numerical coefficients before converting to LaTeX
    rounded_expr = _round_numerical_coeffs(expr)
    symbol_names = {s: _latex_symbol_name(str(s)) for s in sorted(rounded_expr.free_symbols, key=lambda x: str(x))}
    return sp.latex(rounded_expr, symbol_names=symbol_names, **kwargs)


def _convert_angle_to_deg(expr: sp.Expr, unit: str) -> sp.Expr:
    if unit == "rad":
        return expr * 180 / sp.pi
    return expr


def _render_failure_report(items: list[str]):
    st.subheader("Failure Report")
    if not items:
        st.success("No failure conditions detected.")
        return
    st.error(f"{len(items)} failure condition(s) detected.")
    for item in items:
        st.markdown(f"- [x] {item}")


def _run_centroid_problem():
    """
    Problem 5/53 — y-coordinate of centroid of the shaded composite area:
      Semicircle (radius R) minus a centred rectangle (half-width w, height h) at the base.
    Follows the same input / error-handling pattern as the equilibrium problems.
    """
    st.sidebar.subheader("Dimensions (mm) — Problem 5/53")
    R_raw = st.sidebar.text_input("R — semicircle radius [mm]", value="74")
    w_raw = st.sidebar.text_input("w — rectangle half-width [mm]", value="32")
    h_raw = st.sidebar.text_input("h — rectangle height [mm]", value="32")

    # --- Parse inputs (identical helper used by the other two problems) ---
    parse_errors: list[str] = []
    parsed: dict[str, sp.Expr] = {}
    for name, raw in [("R", R_raw), ("w", w_raw), ("h", h_raw)]:
        expr, err = _parse_expr(name, raw)
        if err:
            parse_errors.append(err)
        else:
            parsed[name] = expr

    if parse_errors:
        _render_failure_report(parse_errors)
        st.stop()

    R_expr = sp.simplify(parsed["R"])
    w_expr = sp.simplify(parsed["w"])
    h_expr = sp.simplify(parsed["h"])

    # --- Validation (same pattern as other scenarios) ---
    validation_failures: list[str] = []

    for label, expr in [("R", R_expr), ("w", w_expr), ("h", h_expr)]:
        if _is_numeric_expr(expr) and _has_non_finite(expr):
            validation_failures.append(
                f"Invalid input: {label} results in division by zero or non-finite value."
            )
        if _is_numeric_expr(expr) and not _is_real_finite_numeric(expr):
            validation_failures.append(
                f"Invalid numeric input: {label} must be real and finite."
            )
        if _is_numeric_expr(expr) and _to_float(expr) <= 0:
            validation_failures.append(
                f"Invalid geometry: {label} must be > 0."
            )

    # Domain checks: rectangle must fit inside the semicircle
    if all(_is_numeric_expr(e) for e in [R_expr, w_expr, h_expr]) and not validation_failures:
        R_v = _to_float(R_expr)
        w_v = _to_float(w_expr)
        h_v = _to_float(h_expr)
        if h_v > R_v:
            validation_failures.append(
                "SYSTEM COLLAPSED: INVALID GEOMETRY — rectangle height h must be ≤ R "
                "(the rectangle cannot extend beyond the semicircle radius)."
            )
        if w_v > R_v:
            validation_failures.append(
                "SYSTEM COLLAPSED: INVALID GEOMETRY — rectangle half-width w must be ≤ R "
                "(the rectangle cannot be wider than the semicircle diameter)."
            )
        # Check net area > 0
        A_semi = sp.pi * R_v ** 2 / 2
        A_rect = 2 * w_v * h_v
        if A_rect >= A_semi:
            validation_failures.append(
                "SYSTEM COLLAPSED: INVALID GEOMETRY — rectangle area (2w·h) must be "
                "smaller than the semicircle area (πR²/2). Reduce w or h."
            )
        # Check that rectangle corners stay inside semicircle boundary
        # Rectangle corner (w, h) must satisfy: w² + h² ≤ R²
        if w_v ** 2 + h_v ** 2 > R_v ** 2:
            validation_failures.append(
                "SYSTEM COLLAPSED: INVALID GEOMETRY — rectangle corners extend outside "
                "the semicircle boundary. Reduce w or h to fit the curved shape."
            )

    # --- Stop immediately on any failure (same as the other two problems) ---
    if validation_failures:
        _render_failure_report(validation_failures)
        st.stop()

    # --- Symbolic formulation built from the user's own expressions ---
    # This ensures that if the user types e.g. "cars" as R, the result shows "cars".
    A_semi_display = sp.pi * R_expr ** 2 / 2
    y_semi_display = sp.Rational(4, 1) * R_expr / (3 * sp.pi)
    A_rect_display = 2 * w_expr * h_expr
    y_rect_display = h_expr / 2
    A_net_display = A_semi_display - A_rect_display
    numer_display = A_semi_display * y_semi_display - A_rect_display * y_rect_display
    try:
        y_bar_display = sp.simplify(numer_display / A_net_display)
    except Exception:
        y_bar_display = numer_display / A_net_display

    # --- Display layout ---
    colL, colR = st.columns((1, 1))

    with colL:
        st.subheader("Step 1 — composite-area centroid equations")

        st.code("A_semi = π·R² / 2", language="text")
        st.code("ȳ_semi = 4R / (3π)  [from base, standard result]", language="text")
        st.code("A_rect = 2·w·h", language="text")
        st.code("ȳ_rect = h / 2", language="text")
        st.code("ȳ = (A_semi·ȳ_semi − A_rect·ȳ_rect) / (A_semi − A_rect)", language="text")

        st.subheader("Symbolic result")
        st.latex(
            _latex_expr(
                sp.Eq(sp.Symbol(r"\bar{y}"), y_bar_display),
                mode="plain",
                mul_symbol="dot",
            )
        )

        # Numerical result (all inputs are numeric — passed validation above)
        if all(_is_numeric_expr(e) for e in [R_expr, w_expr, h_expr]):
            R_v = _to_float(R_expr)
            w_v = _to_float(w_expr)
            h_v = _to_float(h_expr)
            A_semi_n = float(sp.pi) * R_v ** 2 / 2
            y_semi_n = 4 * R_v / (3 * float(sp.pi))
            A_rect_n = 2 * w_v * h_v
            y_rect_n = h_v / 2
            A_net_n = A_semi_n - A_rect_n
            y_bar_n = (A_semi_n * y_semi_n - A_rect_n * y_rect_n) / A_net_n

            st.subheader("Numerical result")
            st.write(f"**A_semi** = {A_semi_n:.4f} mm²")
            st.write(f"**ȳ_semi** = {y_semi_n:.4f} mm")
            st.write(f"**A_rect** = {A_rect_n:.4f} mm²")
            st.write(f"**ȳ_rect** = {y_rect_n:.4f} mm")
            st.write(f"**A_net** = {A_net_n:.4f} mm²")
            st.metric("ȳ (y-coordinate of centroid) [mm]", f"{y_bar_n:.4f} mm")
        else:
            st.info(
                "Numerical result requires numeric inputs. "
                "You are in symbolic-variable mode."
            )

    with colR:
        st.subheader("Composite area diagram")
        # Determine what to draw
        all_numeric = all(_is_numeric_expr(e) and _is_real_finite_numeric(e) for e in [R_expr, w_expr, h_expr])

        if all_numeric:
            R_v = _to_float(R_expr)
            w_v = _to_float(w_expr)
            h_v = _to_float(h_expr)
            A_semi_n = float(sp.pi) * R_v ** 2 / 2
            y_semi_n = 4 * R_v / (3 * float(sp.pi))
            A_rect_n = 2 * w_v * h_v
            y_rect_n = h_v / 2
            A_net_n = A_semi_n - A_rect_n
            y_bar_n = (A_semi_n * y_semi_n - A_rect_n * y_rect_n) / A_net_n
            try:
                fig, _ = draw_centroid_diagram(
                    R=R_v, w=w_v, h=h_v,
                    y_bar=y_bar_n,
                    failure_msg=None,
                )
                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
                buf.seek(0)
                st.image(buf, use_container_width=True)
                plt.close(fig)
            except Exception as diagram_err:
                st.error(f"Could not render diagram: {diagram_err}")
        else:
            st.info("Diagram requires numeric geometry inputs.")

    with st.expander("Raw symbolic centroid formula"):
        st.latex(
            r"\bar{y} = "
            + _latex_expr(y_bar_display, mul_symbol="dot")
        )


def _run_parallel_axis_problem():
    """
    Problem A/9 — Parallel Axis Theorem (textbook geometry):
      From the diagram:
        s   = 25 mm  — perpendicular separation between p and p' axes
        d   = 50 mm  — perpendicular distance from p' (nearer axis) to centroid C
      Derived distances from C:
        d_pp  = d       = 50 mm   (C to p'-axis, nearer)
        d_p   = d + s   = 75 mm   (C to p-axis,  farther)
      Parallel Axis Theorem:
        I_p   = I_C + A·d_p²
        I_p'  = I_C + A·d_pp²
        I_p − I_p' = A(d_p² − d_pp²) = 15×10⁶ mm⁴  →  solve for A.
    Follows the same input / error-handling pattern as the other problems.
    """
    st.sidebar.subheader("Dimensions (mm) — Problem A/9")
    s_raw   = st.sidebar.text_input(
        "s — separation between p and p\u2019 axes [mm]",
        value="25",
        help="Perpendicular distance between the two parallel axes (25 mm in the textbook diagram)",
    )
    d_raw   = st.sidebar.text_input(
        "d — distance from p\u2019 to centroid C [mm]",
        value="50",
        help="Perpendicular distance from the nearer axis p\u2019 to centroid C (50 mm in the textbook diagram)",
    )
    delta_I_raw = st.sidebar.text_input(
        "\u0394I = I_p \u2212 I_p\u2019  [mm\u2074  \u00d7 10\u2076]",
        value="15",
        help="Difference in moments of inertia in units of 10\u2076 mm\u2074",
    )

    # --- Parse inputs (identical helper used by the other problems) ---
    parse_errors: list[str] = []
    parsed: dict[str, sp.Expr] = {}
    for name, raw in [("s", s_raw), ("d", d_raw), ("delta_I_millions", delta_I_raw)]:
        expr, err = _parse_expr(name, raw)
        if err:
            parse_errors.append(err)
        else:
            parsed[name] = expr

    if parse_errors:
        _render_failure_report(parse_errors)
        st.stop()

    s_expr       = sp.simplify(parsed["s"])
    d_expr       = sp.simplify(parsed["d"])
    # User enters ΔI in units of 10⁶ mm⁴; convert to mm⁴
    delta_I_expr = sp.simplify(parsed["delta_I_millions"] * sp.Integer(10)**6)

    # --- Validation (same pattern as other problems) ---
    validation_failures: list[str] = []

    for label, expr in [("s", s_expr), ("d", d_expr), ("delta_I", delta_I_expr)]:
        if _is_numeric_expr(expr) and _has_non_finite(expr):
            validation_failures.append(
                f"Invalid input: {label} results in division by zero or non-finite value."
            )
        if _is_numeric_expr(expr) and not _is_real_finite_numeric(expr):
            validation_failures.append(
                f"Invalid numeric input: {label} must be real and finite."
            )

    # s = 0 means axes coincide — the difference ΔI is always 0, unsolvable.
    if _is_numeric_expr(s_expr) and abs(_to_float(s_expr)) < 1e-12:
        validation_failures.append(
            "Invalid geometry: s cannot be zero — p and p\u2019 would be the same axis "
            "and ΔI = 0 for any area."
        )

    # Check equidistant degenerate case: |d| == |d + s| ⇒ denominator = 0.
    # This happens when s = -2d (C is the midpoint between p and p').
    if (
        all(_is_numeric_expr(e) for e in [s_expr, d_expr])
        and not validation_failures
    ):
        _d1_chk = abs(_to_float(d_expr))
        _d2_chk = abs(_to_float(d_expr) + _to_float(s_expr))
        if abs(_d1_chk - _d2_chk) < 1e-9:
            validation_failures.append(
                "Degenerate case: the two axes are equidistant from C — "
                "ΔI = A(d_p\u00b2 − d_p\u2019\u00b2) = 0 regardless of A. "
                "Choose different values of s and d."
            )

    if validation_failures:
        _render_failure_report(validation_failures)
        st.stop()

    # --- Derived distances from centroid C to each axis ---
    # Negative s or d means distance taken in opposite direction; physics only
    # depends on the magnitude of the perpendicular distance (d appears as d²).
    # So we use absolute values. We sort so d_p ≥ d_pp (farther ≥ nearer).
    d_pp_expr = sp.Abs(d_expr)                          # |d|   — C to p'
    d_p_expr  = sp.Abs(sp.simplify(d_expr + s_expr))    # |d+s| — C to p

    # --- Symbolic solution using the Parallel Axis Theorem ---
    # I_p  = I_C + A·d_p²
    # I_p' = I_C + A·d_pp²
    # |I_p − I_p'| = A·|d_p² − d_pp²|  =>  A = ΔI / |d_p² − d_pp²|
    denom_expr = sp.Abs(d_p_expr**2 - d_pp_expr**2)
    try:
        A_expr = sp.simplify(delta_I_expr / denom_expr)
    except Exception:
        A_expr = delta_I_expr / denom_expr

    # --- Display layout ---
    colL, colR = st.columns((1, 1))

    with colL:
        st.subheader("Step 1 — Parallel Axis Theorem equations")

        st.code("d_p  = d + s          (C to p,  farther axis)", language="text")
        st.code("d_p\u2019 = d              (C to p\u2019, nearer axis)", language="text")
        st.code("I_p  = I_C + A\u00b7d_p\u00b2", language="text")
        st.code("I_p\u2019 = I_C + A\u00b7d_p\u2019\u00b2", language="text")
        st.code("I_p \u2212 I_p\u2019 = A\u00b7(d_p\u00b2 \u2212 d_p\u2019\u00b2)", language="text")
        st.code("\u27f9  A = \u0394I / (d_p\u00b2 \u2212 d_p\u2019\u00b2)", language="text")

        st.subheader("Symbolic result")
        st.latex(
            _latex_expr(
                sp.Eq(sp.Symbol("A"), A_expr),
                mode="plain",
                mul_symbol="dot",
            )
        )

        # Numerical result
        all_numeric = all(
            _is_numeric_expr(e) for e in [s_expr, d_expr, delta_I_expr]
        )
        if all_numeric:
            s_v       = _to_float(s_expr)
            d_v       = _to_float(d_expr)
            dI_v      = _to_float(delta_I_expr)    # mm⁴
            # Negative s or d = opposite direction; distances are magnitudes
            _r1       = abs(d_v)                   # |d|   — C to p'
            _r2       = abs(d_v + s_v)             # |d+s| — C to p
            d_pp_v    = min(_r1, _r2)              # nearer axis
            d_p_v     = max(_r1, _r2)              # farther axis
            denom_v   = d_p_v**2 - d_pp_v**2
            A_val     = dI_v / denom_v

            st.subheader("Numerical result")
            st.write(f"**s** = {s_v:.4g} mm  (separation between p and p\u2019)")
            st.write(f"**d** = {d_v:.4g} mm  (p\u2019 to C, signed)")
            st.write(f"**|d|**   = {abs(d_v):.4g} mm  (C to p\u2019)")
            st.write(f"**|d+s|** = {abs(d_v + s_v):.4g} mm  (C to p)")
            st.write(f"**d_p\u00b2 \u2212 d_p\u2019\u00b2** = {denom_v:.4g} mm\u00b2")
            st.write(f"**\u0394I** = {dI_v:.6g} mm\u2074  ({dI_v/1e6:.4g} \u00d7 10\u2076 mm\u2074)")
            st.metric("Area A [mm\u00b2]", f"{A_val:,.2f} mm\u00b2")
        else:
            st.info(
                "Numerical result requires numeric inputs. "
                "You are in symbolic-variable mode."
            )

    with colR:
        st.subheader("Parallel axis diagram")
        all_numeric_draw = all(
            _is_numeric_expr(e) and _is_real_finite_numeric(e)
            for e in [s_expr, d_expr, delta_I_expr]
        )
        if all_numeric_draw:
            s_v   = _to_float(s_expr)
            d_v   = _to_float(d_expr)
            dI_v  = _to_float(delta_I_expr)
            # Negative s or d = opposite direction; use magnitudes, sort farther/nearer
            _r1   = abs(d_v)
            _r2   = abs(d_v + s_v)
            d_pp_v = min(_r1, _r2)   # nearer axis
            d_p_v  = max(_r1, _r2)   # farther axis
            A_val  = dI_v / (d_p_v**2 - d_pp_v**2)
            try:
                fig, _ = draw_parallel_axis_diagram(
                    v_pp=d_v,           # signed: d  (p' offset from C)
                    v_p=d_v + s_v,      # signed: d+s (p  offset from C)
                    A_val=A_val,
                    delta_I=dI_v,
                )
                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
                buf.seek(0)
                st.image(buf, use_container_width=True)
                plt.close(fig)
            except Exception as diagram_err:
                st.error(f"Could not render diagram: {diagram_err}")
        else:
            st.info("Diagram requires numeric geometry inputs.")

    with st.expander("Raw symbolic formula for A"):
        st.latex(
            r"A = \frac{\Delta I}{(d+s)^2 - d^2}"
        )


def main():

    st.set_page_config(page_title="Statics Presentation", layout="wide")
    st.title("MECHANICS STATICS (EXPERIENTIAL COMPONENT)")
    st.caption("Symbolic assembly of [A]{x}={b}; solve with SymPy or Wolfram Kernel if configured.")

    scenario = st.sidebar.selectbox(
        "Scenario",
        [
            "Flagpole & frame (2/49 style)",
            "Wood clamp (3/8 style)",
            "Centroid of shaded area (5/53 style)",
            "Parallel Axis Theorem (A/9 style)",
        ],
    )
    # ---- Route self-contained problems before the equilibrium setup ----
    if scenario.startswith("Centroid"):
        _run_centroid_problem()
        return
    if scenario.startswith("Parallel"):
        _run_parallel_axis_problem()
        return

    setup = _setup_for_choice(scenario)

    st.sidebar.subheader("Units")
    length_unit = st.sidebar.selectbox("Length unit", ["m", "mm"], index=0)
    force_unit = st.sidebar.selectbox("Force unit", ["N", "kN"], index=1 if setup.fbd_kind == "flagpole" else 0)
    angle_unit = st.sidebar.selectbox("Angle unit", ["deg", "rad"], index=0)

    L_factor = sp.Float(0.001) if length_unit == "mm" else sp.Float(1.0)
    F_factor = sp.Float(1000.0) if force_unit == "kN" else sp.Float(1.0)

    st.sidebar.subheader("Lengths / geometry (supports symbols)")
    if setup.fbd_kind == "flagpole":
        L_OA_raw = st.sidebar.text_input(f"OA [{length_unit}]", value="3")
        L_OB_raw = st.sidebar.text_input(f"OB [{length_unit}]", value="3")
        L_AB_raw = st.sidebar.text_input(f"AB [{length_unit}]", value="3")
    else:
        L1_raw = st.sidebar.text_input(f"L1 [{length_unit}]", value="0.15" if length_unit == "m" else "150")
        L2_raw = st.sidebar.text_input(f"L2 [{length_unit}]", value="0.10" if length_unit == "m" else "100")

    st.sidebar.subheader("Forces (supports symbols)")
    if setup.fbd_kind == "flagpole":
        T_raw = st.sidebar.text_input(f"T [{force_unit}]", value="3.2" if force_unit == "kN" else "3200")
    else:
        P_raw = st.sidebar.text_input(f"P [{force_unit}]", value="500")

    if setup.fbd_kind == "flagpole":
        st.sidebar.subheader("Angles (supports symbols)")
        theta_raw = st.sidebar.text_input(f"theta [{angle_unit}]", value="20" if angle_unit == "deg" else "pi/9")
    else:
        theta_raw = "0"  # Not used for wood clamp

    parse_errors = []
    parsed: dict[str, sp.Expr] = {}

    if setup.fbd_kind == "flagpole":
        for name, raw in [
            ("L_OA", L_OA_raw),
            ("L_OB", L_OB_raw),
            ("L_AB", L_AB_raw),
            ("T", T_raw),
            ("theta", theta_raw),
        ]:
            expr, err = _parse_expr(name, raw)
            if err:
                parse_errors.append(err)
            else:
                parsed[name] = expr
    else:
        for name, raw in [("L1", L1_raw), ("L2", L2_raw), ("P", P_raw)]:
            expr, err = _parse_expr(name, raw)
            if err:
                parse_errors.append(err)
            else:
                parsed[name] = expr

    if parse_errors:
        _render_failure_report(parse_errors)
        st.stop()

    # Convert to base units used in equations: m, N, deg
    subs: dict[sp.Symbol, sp.Expr] = {}
    validation_failures: list[str] = []

    if setup.fbd_kind == "flagpole":
        L_OA_s, L_OB_s, L_AB_s, T_s, th_s = setup.subs_keys
        L_OA_expr = sp.simplify(parsed["L_OA"] * L_factor)
        L_OB_expr = sp.simplify(parsed["L_OB"] * L_factor)
        L_AB_expr = sp.simplify(parsed["L_AB"] * L_factor)
        T_expr = sp.simplify(parsed["T"] * F_factor)
        th_expr = sp.simplify(_convert_angle_to_deg(parsed["theta"], angle_unit))
        # Normalize angle to [0, 360) for numeric inputs to prevent user confusion with wrapped angles
        if _is_numeric_expr(th_expr):
            th_expr = sp.simplify(th_expr % 360)

        for label, expr in [("OA", L_OA_expr), ("OB", L_OB_expr), ("AB", L_AB_expr), ("T", T_expr), ("theta", th_expr)]:
            if _is_numeric_expr(expr) and _has_non_finite(expr):
                validation_failures.append(f"Invalid input: {label} results in division by zero or non-finite value.")

        # Fool-proof geometry checks for numeric inputs.
        for label, expr in [("OA", L_OA_expr), ("OB", L_OB_expr), ("AB", L_AB_expr)]:
            if _is_numeric_expr(expr) and not _is_real_finite_numeric(expr):
                validation_failures.append(f"Invalid numeric input: {label} must be real and finite.")
            if _is_numeric_expr(expr) and _to_float(expr) <= 0:
                validation_failures.append(f"Invalid geometry: {label} must be > 0.")

        # Tension must be positive (cables cannot support compression).
        if _is_numeric_expr(T_expr) and not _is_real_finite_numeric(T_expr):
            validation_failures.append(f"Invalid numeric input: T must be real and finite.")
        if _is_numeric_expr(T_expr) and _to_float(T_expr) <= 0:
            validation_failures.append(
                f"Invalid tension: T must be > 0. Cables cannot support compressive stress; negative tension is not physical."
            )

        # Triangle inequality and realizability checks (numeric case).
        if all(_is_numeric_expr(v) for v in [L_OA_expr, L_OB_expr, L_AB_expr]):
            oa = _to_float(L_OA_expr)
            ob = _to_float(L_OB_expr)
            ab = _to_float(L_AB_expr)
            if not (oa + ob > ab and oa + ab > ob and ob + ab > oa):
                validation_failures.append(
                    "SYSTEM COLLAPSED: INVALID GEOMETRY (Triangle inequality violated for OA, OB, AB)."
                )
            else:
                x_a_expr = sp.simplify((L_OA_expr**2 + L_OB_expr**2 - L_AB_expr**2) / (2 * L_OB_expr))
                y2_expr = sp.simplify(L_OA_expr**2 - x_a_expr**2)
                if _is_numeric_expr(y2_expr) and _to_float(y2_expr) <= 1e-12:
                    validation_failures.append(
                        "SYSTEM COLLAPSED: GEOMETRIC INSTABILITY (A, O, B become collinear)."
                    )

        subs[L_OA_s] = L_OA_expr
        subs[L_OB_s] = L_OB_expr
        subs[L_AB_s] = L_AB_expr
        subs[T_s] = T_expr
        subs[th_s] = th_expr

        # Visualization-only cable extension from A toward D.
        L_D_draw_expr = sp.simplify(sp.Float(1.25) * L_OA_expr)
    else:
        L1_s, L2_s, P_s = setup.subs_keys
        L1_expr = sp.simplify(parsed["L1"] * L_factor)
        L2_expr = sp.simplify(parsed["L2"] * L_factor)
        P_expr = sp.simplify(parsed["P"] * F_factor)

        for label, expr in [("L1", L1_expr), ("L2", L2_expr), ("P", P_expr)]:
            if _is_numeric_expr(expr) and _has_non_finite(expr):
                validation_failures.append(f"Invalid input: {label} results in division by zero or non-finite value.")
        for label, expr in [("L1", L1_expr), ("L2", L2_expr)]:
            if _is_numeric_expr(expr) and not _is_real_finite_numeric(expr):
                validation_failures.append(f"Invalid numeric input: {label} must be real and finite.")
            # L1 = 0 is physically valid (load applied at screw A's position).
            # L2 must be strictly > 0 (A and B cannot share the same position).
            if label == "L1":
                if _is_numeric_expr(expr) and _to_float(expr) < 0:
                    validation_failures.append(
                        "Invalid geometry: L1 must be ≥ 0 "
                        "(negative distance from tip to screw A is not physical)."
                    )
            else:  # L2
                if _is_numeric_expr(expr) and _to_float(expr) <= 0:
                    validation_failures.append(
                        "Invalid geometry: L2 must be > 0 "
                        "(screws A and B cannot be at the same position — system is singular)."
                    )

        subs[L1_s] = L1_expr
        subs[L2_s] = L2_expr
        subs[P_s] = P_expr

    if validation_failures:
        _render_failure_report(validation_failures)
        st.stop()

    one_way_supports = dict(setup.one_way)

    try:
        sol = build_and_solve(setup.A, setup.b, setup.unknowns, subs, equation_rows_meta=setup.equation_meta)
    except ZeroDivisionError:
        _render_failure_report(["Division by zero detected while solving equations. Please revise denominator values."])
        st.stop()
    except Exception:
        _render_failure_report(["Could not solve the system for current inputs. Please verify expression domains."])
        st.stop()

    stability_ready = sol.is_numeric_case
    rep = None
    if stability_ready:
        try:
            rep = check_stability(
                node_ids=setup.node_ids,
                structural_edges=setup.structural_edges,
                A_sym=setup.A,
                b_sym=setup.b,
                unknown_labels=[str(u) for u in setup.unknowns],
                subs=subs,
                one_way_supports=one_way_supports,
            )
        except ZeroDivisionError:
            _render_failure_report(["Division by zero detected during stability checks."])
            st.stop()

    colL, colR = st.columns((1, 1))

    with colL:
        st.subheader("Step 1 — equilibrium equations")
        for line in sol.equations_display:
            st.code(line, language="text")
        st.markdown(sol.wolfram_note)

        st.subheader("Stability core")
        if not stability_ready:
            st.info("Stability checks require numeric inputs. You are in symbolic-variable mode.")
        else:
            if rep and rep.determinant is not None:
                st.write(f"det(A) = {rep.determinant:.2f}")
            if rep:
                for m in rep.messages:
                    if "COLLAPSED" in m:
                        st.error(m)
                    else:
                        st.success(m)

        runtime_failures: list[str] = []
        if rep and not rep.ok:
            runtime_failures.extend(rep.messages)

        if setup.fbd_kind == "flagpole":
            st.caption("Moment-only interpretation: M_O from cable force depends on OA/OB/AB, T, θ.")
            try:
                oa_s, ob_s, ab_s, t_s, th_s = setup.subs_keys
                x_a = (subs[oa_s] ** 2 + subs[ob_s] ** 2 - subs[ab_s] ** 2) / (2 * subs[ob_s])
                y_a = sp.sqrt(subs[oa_s] ** 2 - x_a**2)
                th = sp.pi * subs[th_s] / 180
                fx = -subs[t_s] * sp.cos(th)
                fy = -subs[t_s] * sp.sin(th)
                m_t_expr = sp.simplify(x_a * fy - y_a * fx)
                if _has_non_finite(m_t_expr):
                    runtime_failures.append("Division by zero detected while computing moment about O.")
                elif not m_t_expr.free_symbols:
                    m_val = float(sp.N(m_t_expr))
                    direction = "Anti-clockwise" if m_val > 0 else ("Clockwise" if m_val < 0 else "Zero")
                    st.metric("Moment of cable tension about O [N·m]", f"{abs(m_val):.2f} ({direction})")
                else:
                    st.write("Moment of cable tension about O:")
                    st.latex(_latex_expr(sp.Eq(sp.Symbol("M_O"), m_t_expr), mode="plain", mul_symbol="dot"))
            except ZeroDivisionError:
                runtime_failures.append("Division by zero detected while computing moment about O.")

        if runtime_failures:
            _render_failure_report(runtime_failures)

        st.subheader("Symbolic solution (algebraic formulas with parameters)")
        st.markdown("_Shows the equilibrium solution formulas. When parameters have numeric values, they are substituted below:_")
        for k, expr in sol.solution_symbolic.items():
            # For clamp: negate F_A and F_B to show correct sign convention (up=positive)
            if setup.fbd_kind == "clamp" and k in ["F_A", "F_B"]:
                expr = -sp.simplify(expr)
            st.latex(_latex_expr(sp.Eq(sp.Symbol(k), expr), mode="plain", mul_symbol="dot"))

        if sol.solution_numeric:
            st.subheader("Numerical unknowns (with all parameters substituted)")
            for k, v in sol.solution_numeric.items():
                # For clamp: negate F_A and F_B to show correct sign convention (up=positive)
                if setup.fbd_kind == "clamp" and k in ["F_A", "F_B"]:
                    v = -v
                st.write(f"**{k}** = {v:.2f}")

        if stability_ready and rep and not rep.ok:
            st.subheader("Collapse mode")
            st.warning(rep.collapse_mode or "Unstable or ill-conditioned.")

        # ── Physics Engine: equilibrium verification (clamp only) ──────────────
        if setup.fbd_kind == "clamp" and sol.solution_numeric:
            st.subheader("⚙️ Physics Engine — Equilibrium Verification")
            try:
                import math as _math
                L1_v = _to_float(subs[setup.subs_keys[0]])
                L2_v = _to_float(subs[setup.subs_keys[1]])
                P_v  = _to_float(subs[setup.subs_keys[2]])
                # For clamp: use original solution values; display will negate them for clamping view
                FA_v = sol.solution_numeric.get("F_A", float("nan"))
                FB_v = sol.solution_numeric.get("F_B", float("nan"))
                # Convert to clamping force view (negate to flip from up=positive to down=positive)
                FA_clamp = -FA_v if not _math.isnan(FA_v) else float("nan")
                FB_clamp = -FB_v if not _math.isnan(FB_v) else float("nan")

                if any(_math.isnan(x) or _math.isinf(x) for x in [FA_v, FB_v]):
                    st.error("⚠️ Physics engine: solved forces are non-finite. "
                             "Check your inputs for singularities.")
                else:
                    # For clamp verification: use original (non-negated) solutions
                    FA_orig = sol.solution_numeric.get("F_A", float("nan"))
                    FB_orig = sol.solution_numeric.get("F_B", float("nan"))
                    res_fy  = FA_orig + FB_orig - P_v          # should be ≈ 0
                    res_ma  = FA_orig * L2_v - P_v * (L1_v + L2_v)   # should be ≈ 0
                    tol     = max(abs(P_v) * 1e-6, 1e-9)

                    fy_ok = abs(res_fy) < tol
                    ma_ok = abs(res_ma) < tol

                    col1, col2 = st.columns(2)
                    with col1:
                        if fy_ok:
                            st.success(f"✔ ΣFy = 0 ✔  (residual ≈ {res_fy:.2e})")
                        else:
                            st.error(f"❌ ΣFy residual = {res_fy:.4g} (expected ≈ 0)")
                    with col2:
                        if ma_ok:
                            st.success(f"✔ ΣM_B = 0 ✔  (residual ≈ {res_ma:.2e})")
                        else:
                            st.error(f"❌ ΣM_B residual = {res_ma:.4g} (expected ≈ 0)")

                    st.markdown("**Screw clamping forces (downward = positive in clamping view):")
                    st.markdown("_F_A (Screw A): positive = pushes down (clamps); negative = pulls up_")
                    st.markdown("_F_B (Screw B): positive = pushes down (clamps); negative = pulls up_")
                    for name, val_orig, val_clamp in [("F_A (Screw A)", FA_v, FA_clamp), ("F_B (Screw B)", FB_v, FB_clamp)]:
                        if abs(val_clamp) < tol:
                            st.info(f"▪️ {name} = {val_clamp:.2f} N  → No force")
                        elif val_clamp > 0:
                            st.success(f"↓ {name} = {val_clamp:.2f} N (downward) → Screw clamps")
                        else:
                            st.info(f"↑ {name} = {val_clamp:.2f} N (upward) → Screw pulls/releases")

                    if not (fy_ok and ma_ok):
                        st.error("🚨 Physics engine detected equilibrium residuals — "
                                 "the solved forces do not satisfy equilibrium. "
                                 "Possible numerical issue in solver.")
                    else:
                        st.success("✅ System passes all equilibrium checks.")
            except Exception as _phys_err:
                st.warning(f"Physics engine could not complete verification: {_phys_err}")

    with colR:
        st.subheader("Free-body diagram")
        can_draw = False
        if setup.fbd_kind == "flagpole":
            draw_exprs = [
                subs[setup.subs_keys[0]],
                subs[setup.subs_keys[1]],
                subs[setup.subs_keys[2]],
                L_D_draw_expr,
                subs[setup.subs_keys[3]],
                subs[setup.subs_keys[4]],
            ]
            can_draw = all(_is_numeric_expr(e) and _is_real_finite_numeric(e) for e in draw_exprs)
            if can_draw:
                vals = sol.solution_numeric
                fig, _ = draw_flagpole_fbd(
                    L_OA=_to_float(subs[setup.subs_keys[0]]),
                    L_OB=_to_float(subs[setup.subs_keys[1]]),
                    L_AB=_to_float(subs[setup.subs_keys[2]]),
                    L_D_vis=_to_float(L_D_draw_expr),
                    T=_to_float(subs[setup.subs_keys[3]]),
                    theta_deg=_to_float(subs[setup.subs_keys[4]]),
                    R_Ox=vals.get("R_Ox", 0.0),
                    R_Oy=vals.get("R_Oy", 0.0),
                    stability=rep,
                    length_unit=length_unit,
                )
        else:
            draw_exprs = [subs[setup.subs_keys[0]], subs[setup.subs_keys[1]], subs[setup.subs_keys[2]]]
            can_draw = all(_is_numeric_expr(e) and _is_real_finite_numeric(e) for e in draw_exprs)
            if can_draw:
                vals = sol.solution_numeric
                try:
                    # For clamp: negate to flip from standard coords (up=positive) to clamping view (down=positive)
                    fa_display = -vals.get("F_A", 0.0) if setup.fbd_kind == "clamp" else vals.get("F_A", 0.0)
                    fb_display = -vals.get("F_B", 0.0) if setup.fbd_kind == "clamp" else vals.get("F_B", 0.0)
                    fig, _ = draw_clamp_fbd(
                        L1=_to_float(subs[setup.subs_keys[0]]),
                        L2=_to_float(subs[setup.subs_keys[1]]),
                        P=_to_float(subs[setup.subs_keys[2]]),
                        F_A=fa_display,
                        F_B=fb_display,
                        stability=rep,
                    )
                except Exception as _draw_err:
                    st.warning(f"⚠️ Could not render Free-Body Diagram: {_draw_err}")
                    can_draw = False

        if can_draw:
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
            buf.seek(0)
            st.image(buf, use_container_width=True)
            plt.close(fig)
        else:
            st.info("FBD drawing requires numeric geometry inputs for this scenario.")

    with st.expander("Raw symbolic A and b"):
        st.latex(
            r"A = "
            + _latex_expr(sol.matrix_A, mul_symbol="dot")
            + r", \quad b = "
            + _latex_expr(sol.vector_b, mul_symbol="dot")
        )


if __name__ == "__main__":
    main()
