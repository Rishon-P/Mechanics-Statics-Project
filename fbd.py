"""
Matplotlib free-body diagrams; red emphasis for failed members/supports.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

import matplotlib.pyplot as plt
import numpy as np

if TYPE_CHECKING:
    from stability import StabilityReport


def _scale_arrow(ax, x, y, dx, dy, color, label: str, lw: float = 2.0):
    mag = math.hypot(dx, dy)
    if mag < 1e-12:
        return
    s = 0.35 / mag if mag > 0 else 1.0
    ax.annotate(
        "",
        xy=(x + dx * s * 2.2, y + dy * s * 2.2),
        xytext=(x, y),
        arrowprops=dict(arrowstyle="->", color=color, lw=lw),
    )
    ax.text(x + dx * s * 2.4, y + dy * s * 2.4, label, fontsize=9, color=color)


def draw_flagpole_fbd(
    *,
    L_OA: float,
    L_OB: float,
    L_AB: float,
    L_D_vis: float,
    T: float,
    theta_deg: float,
    R_Ox: float,
    R_Oy: float,
    stability: Optional["StabilityReport"] = None,
    figsize=(9, 5),
):
    """θ = angle of D→A with +x (deg). T signed flips cable force direction."""
    fig, ax = plt.subplots(figsize=figsize)
    th = math.radians(theta_deg)
    cos_t, sin_t = math.cos(th), math.sin(th)

    O = np.array([0.0, 0.0])
    B = np.array([L_OB, 0.0])
    C = np.array([L_OB + max(0.35 * L_OB, 0.6), 0.0])
    x_a = (L_OA**2 + L_OB**2 - L_AB**2) / (2.0 * L_OB)
    y2 = max(L_OA**2 - x_a**2, 0.0)
    A = np.array([x_a, math.sqrt(y2)])
    # D lies from A along −(cos θ, sin θ) (toward D)
    D = A - L_D_vis * np.array([cos_t, sin_t])

    def edge_color(n1: str, n2: str) -> str:
        if stability and not stability.ok:
            bad = {(a, b) for a, b in stability.highlight_edges} | {(b, a) for a, b in stability.highlight_edges}
            if (n1, n2) in bad or (n2, n1) in bad:
                return "red"
        return "black"

    def node_color(n: str) -> str:
        if stability and not stability.ok and n in stability.highlight_nodes:
            return "red"
        return "black"

    segments = [
        ("O", "B", O, B),
        ("O", "A", O, A),
        ("A", "B", A, B),
    ]
    for n1, n2, p1, p2 in segments:
        c = edge_color(n1, n2)
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=c, lw=2.5 if c == "red" else 1.8)

    # Cable A–D
    ax.plot([A[0], D[0]], [A[1], D[1]], color="steelblue", lw=2, linestyle="--")
    ax.text(D[0] - 0.15, D[1], "D", fontsize=10)
    pulley_r = max(0.08 * L_OB, 0.12)
    pulley = plt.Circle((D[0], D[1]), pulley_r, fill=False, color="dimgray", lw=2)
    ax.add_patch(pulley)
    ax.plot([D[0] - 1.8 * pulley_r, D[0] + 1.8 * pulley_r], [D[1] - 1.6 * pulley_r, D[1] - 1.6 * pulley_r], color="dimgray", lw=2)

    # Joints
    for name, pt in [("O", O), ("A", A), ("B", B), ("C", C)]:
        ax.scatter([pt[0]], [pt[1]], c=node_color(name), s=80, zorder=5)
        ax.text(pt[0] + 0.08, pt[1] + 0.08, name, fontsize=11, color=node_color(name))

    # Hinge / roller
    ax.plot([O[0] - 0.12, O[0] + 0.12], [O[1] - 0.08, O[1] - 0.08], "k", lw=1.5)
    ax.text(O[0] - 0.2, O[1] - 0.35, "hinge", fontsize=8)
    # Draw pole extension to C as context only.
    ax.plot([B[0], C[0]], [B[1], C[1]], color="black", lw=1.8)
    ax.text(C[0] + 0.08, C[1] - 0.08, "pole end", fontsize=8, color="gray")

    # Applied tension at A (on structure: components Fx, Fy)
    Fx = -T * cos_t
    Fy = -T * sin_t
    _scale_arrow(ax, A[0], A[1], Fx, Fy, "darkgreen", f"T ({T:.3g} kN)" if abs(T) < 100 else f"T ({T:.3g} N)")

    # Reactions
    _scale_arrow(ax, O[0], O[1], R_Ox, R_Oy, "purple", "R_O")

    # Ensure full scene (including pulley D) is visible.
    x_all = [O[0], A[0], B[0], C[0], D[0]]
    y_all = [O[1], A[1], B[1], C[1], D[1]]
    x_min, x_max = min(x_all), max(x_all)
    y_min, y_max = min(y_all), max(y_all)
    pad_x = max(0.15 * (x_max - x_min + 1e-9), 0.6)
    pad_y = max(0.2 * (y_max - y_min + 1e-9), 0.6)
    ax.set_xlim(x_min - pad_x, x_max + pad_x)
    ax.set_ylim(min(y_min - pad_y, -0.5), y_max + pad_y)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Free-body: flagpole + frame")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="k", lw=0.5)
    ax.axvline(0, color="k", lw=0.5)
    fig.tight_layout()
    return fig, ax


def draw_clamp_fbd(
    *,
    L1: float,
    L2: float,
    P: float,
    F_A: float,
    F_B: float,
    stability: Optional["StabilityReport"] = None,
    figsize=(10, 6),
):
    """
    Polished textbook-style FBD for the wood-clamp top jaw (Problem 3/8).

    Layout (all coordinates in the user's length units, e.g. metres):
      - Thick rectangular jaw beam drawn from x=0 (tip/load end) to x=L1+L2
      - Screw A at x=L1, Screw B at x=L1+L2 (right end)
      - Applied load P acts downward at x=0 (tip)
      - Screw reaction forces F_A, F_B act vertically at their positions
      - Dimension brackets with L1 and L2 shown below the beam
      - Wall fixture (hatched block) at the tip end (x=0)
    """
    # ------------------------------------------------------------------ setup
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor("#f7f9fc")
    ax.set_facecolor("#f7f9fc")

    Ltot  = L1 + L2
    # beam half-height (visual only)
    bh    = Ltot * 0.055
    # extra horizontal padding on each side
    pad_x = Ltot * 0.25
    pad_y = Ltot * 0.55

    # key x-positions
    x_tip = 0.0
    x_A   = L1
    x_B   = L1 + L2
    y_mid = 0.0  # beam centreline

    # ------------------------------------------------------------------ helpers
    def _fail_color(label: str, default: str) -> str:
        if stability and not stability.ok:
            if label in getattr(stability, "highlight_nodes", []):
                return "#e74c3c"
        return default

    arrow_kw = dict(
        length_includes_head=True,
        head_width=bh * 0.55,
        head_length=bh * 0.65,
        linewidth=2.2,
        zorder=6,
    )

    def draw_arrow(x, y, dx, dy, color, label, label_side="top"):
        """Draw a clean FBD force arrow with a value label."""
        ax.arrow(x, y, dx, dy, color=color, fc=color, **arrow_kw)
        # label offset
        off = bh * 1.4
        if label_side == "top":
            lx, ly = x + dx * 0.5, y + dy + off
            va = "bottom"
        else:
            lx, ly = x + dx * 0.5, y + dy - off
            va = "top"
        ax.text(
            lx, ly, label,
            ha="center", va=va,
            fontsize=10, fontweight="bold",
            color=color, zorder=7,
            bbox=dict(boxstyle="round,pad=0.18", fc="white", ec=color, lw=0.8, alpha=0.85),
        )

    # ------------------------------------------------------------------ wall fixture at x=0
    wall_w  = Ltot * 0.06
    wall_h  = bh * 3.8
    wall_x  = x_tip - wall_w
    wall_y  = y_mid - wall_h / 2
    wall_patch = plt.Rectangle(
        (wall_x, wall_y), wall_w, wall_h,
        color="#bdc3c7", zorder=1,
    )
    ax.add_patch(wall_patch)
    # hatch lines
    for yi in np.linspace(wall_y, wall_y + wall_h, 9):
        ax.plot(
            [wall_x - wall_w * 0.6, wall_x],
            [yi, yi + wall_h * 0.12],
            color="#95a5a6", lw=0.9, zorder=1,
        )
    ax.plot(
        [wall_x, wall_x], [wall_y, wall_y + wall_h],
        color="#7f8c8d", lw=2.2, zorder=2,
    )

    # ------------------------------------------------------------------ beam body
    beam = plt.Rectangle(
        (x_tip, y_mid - bh), Ltot, 2 * bh,
        linewidth=2.0, edgecolor="#2c3e50",
        facecolor="#d5e8f5", zorder=2,
    )
    ax.add_patch(beam)

    # centreline (dashed)
    ax.plot(
        [x_tip - wall_w * 0.4, x_B + pad_x * 0.08],
        [y_mid, y_mid],
        color="#aab4c4", lw=1.0, linestyle="--", zorder=3,
    )

    # ------------------------------------------------------------------ screw symbols at A and B
    screw_r = bh * 0.75
    for x_pos, label in [(x_A, "A"), (x_B, "B")]:
        col = _fail_color(label, "#2c3e50")
        # vertical screw shaft through beam
        ax.plot(
            [x_pos, x_pos],
            [y_mid - bh * 2.5, y_mid + bh * 2.5],
            color=col, lw=2.5, zorder=4,
        )
        # screw circle (head)
        screw_circle = plt.Circle(
            (x_pos, y_mid + bh * 2.0), screw_r,
            linewidth=1.8, edgecolor=col, facecolor="#ecf0f1",
            zorder=5,
        )
        ax.add_patch(screw_circle)
        # crosshair inside circle
        ax.plot(
            [x_pos - screw_r * 0.6, x_pos + screw_r * 0.6],
            [y_mid + bh * 2.0, y_mid + bh * 2.0],
            color=col, lw=1.2, zorder=5,
        )
        ax.plot(
            [x_pos, x_pos],
            [y_mid + bh * 2.0 - screw_r * 0.6, y_mid + bh * 2.0 + screw_r * 0.6],
            color=col, lw=1.2, zorder=5,
        )
        # label
        ax.text(
            x_pos, y_mid + bh * 3.5, label,
            ha="center", va="bottom",
            fontsize=12, fontweight="bold",
            color=col, zorder=6,
        )

    # ------------------------------------------------------------------ force arrows
    arrow_len = bh * 3.8   # visual length of each arrow

    # Applied load P — downward at the tip
    p_col = "#27ae60"
    draw_arrow(
        x_tip, y_mid + arrow_len, 0, -arrow_len,
        p_col,
        f"P = {P:.3g}",
        label_side="top",
    )

    # Screw forces F_A and F_B — upward (positive convention)
    fa_col = _fail_color("A", "#2980b9")
    fb_col = _fail_color("B", "#8e44ad")

    fa_dir = 1 if F_A >= 0 else -1
    fb_dir = 1 if F_B >= 0 else -1

    draw_arrow(
        x_A, y_mid - bh - arrow_len * abs(fa_dir),
        0, fa_dir * arrow_len,
        fa_col,
        f"F_A = {F_A:.3g}",
        label_side="bottom",
    )
    draw_arrow(
        x_B, y_mid - bh - arrow_len * abs(fb_dir),
        0, fb_dir * arrow_len,
        fb_col,
        f"F_B = {F_B:.3g}",
        label_side="bottom",
    )

    # ------------------------------------------------------------------ dimension brackets
    dim_y    = y_mid - bh * 5.5
    tick_h   = bh * 0.5
    dim_col  = "#555e6e"

    # L1 bracket (0 → x_A)
    for x_brk in [x_tip, x_A]:
        ax.plot([x_brk, x_brk], [dim_y - tick_h, dim_y + tick_h], color=dim_col, lw=1.4)
    ax.annotate(
        "", xy=(x_A, dim_y), xytext=(x_tip, dim_y),
        arrowprops=dict(arrowstyle="<->", color=dim_col, lw=1.4),
    )
    ax.text(
        (x_tip + x_A) / 2, dim_y - bh * 1.5,
        f"L₁ = {L1:.4g}",
        ha="center", va="top", fontsize=10, color=dim_col, fontweight="bold",
    )

    # L2 bracket (x_A → x_B)
    for x_brk in [x_A, x_B]:
        ax.plot([x_brk, x_brk], [dim_y - tick_h, dim_y + tick_h], color=dim_col, lw=1.4)
    ax.annotate(
        "", xy=(x_B, dim_y), xytext=(x_A, dim_y),
        arrowprops=dict(arrowstyle="<->", color=dim_col, lw=1.4),
    )
    ax.text(
        (x_A + x_B) / 2, dim_y - bh * 1.5,
        f"L₂ = {L2:.4g}",
        ha="center", va="top", fontsize=10, color=dim_col, fontweight="bold",
    )

    # ------------------------------------------------------------------ title / labels / limits
    ax.set_title(
        "Free-Body Diagram — Top Jaw (Wood Clamp, Problem 3/8)",
        fontsize=13, fontweight="bold", color="#2c3e50", pad=10,
    )
    ax.set_xlabel("Position along jaw axis (same units as inputs)", fontsize=10, color="#555")
    ax.tick_params(left=False, labelleft=False)     # hide y-axis ticks; FBD is schematic
    ax.set_yticks([])

    x_lo = wall_x - wall_w * 1.2
    x_hi = x_B + pad_x * 0.45
    y_lo = dim_y - bh * 3.5
    y_hi = y_mid + arrow_len + bh * 5.5

    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)
    ax.set_aspect("equal")
    ax.grid(True, color="#dce3ec", linewidth=0.6, linestyle="--", alpha=0.7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#c5cdd8")

    fig.tight_layout()
    return fig, ax


def draw_centroid_diagram(
    *,
    R: float,
    w: float,
    h: float,
    y_bar: Optional[float] = None,
    failure_msg: Optional[str] = None,
    figsize=(8, 6),
):
    """
    Draw the composite area for Problem 5/53:
      - Semicircle of radius R (base at y=0, flat side along x-axis)
      - Minus a centred rectangle of width 2w and height h cut from the base
    Marks the centroid ȳ on the y-axis when y_bar is provided.
    Highlights in red / shows failure_msg when geometry is invalid.
    """
    fig, ax = plt.subplots(figsize=figsize)

    accent = "#c0392b" if failure_msg else "#2c3e50"
    shade_color = "#e74c3c" if failure_msg else "#7f8c8d"

    # --- Filled semicircle ---
    theta_vals = np.linspace(0, np.pi, 300)
    x_semi = R * np.cos(theta_vals)
    y_semi = R * np.sin(theta_vals)
    x_poly = np.concatenate([x_semi, [x_semi[-1], x_semi[0]]])
    y_poly = np.concatenate([y_semi, [0.0, 0.0]])
    ax.fill(x_poly, y_poly, color=shade_color, alpha=0.55, zorder=1)
    ax.plot(x_semi, y_semi, color=accent, lw=2, zorder=2)
    ax.plot([-R, R], [0, 0], color=accent, lw=2, zorder=2)

    # --- White rectangular cutout (only if geometry is plausible) ---
    if w > 0 and h > 0:
        rect_x = [-w, w, w, -w, -w]
        rect_y = [0, 0, h, h, 0]
        ax.fill(rect_x, rect_y, color="white", zorder=3)
        ax.plot(rect_x, rect_y, color=accent, lw=1.5, linestyle="--", zorder=4)

    # --- Dimension annotations ---
    dim_color = "#2980b9" if not failure_msg else "#c0392b"

    # Radius label along a diagonal
    mid_angle = np.pi * 0.65
    rx, ry = 0.55 * R * np.cos(mid_angle), 0.55 * R * np.sin(mid_angle)
    ax.annotate(
        "",
        xy=(R * np.cos(mid_angle), R * np.sin(mid_angle)),
        xytext=(0.0, 0.0),
        arrowprops=dict(arrowstyle="-", color=dim_color, lw=1.2),
        zorder=5,
    )
    ax.text(rx - 0.05 * R, ry + 0.04 * R, f"R = {R:.4g}", fontsize=9, color=dim_color, zorder=6)

    # Half-width labels below the base
    if w > 0:
        for sign in (1, -1):
            ax.annotate(
                "",
                xy=(sign * w, -0.06 * R),
                xytext=(0.0, -0.06 * R),
                arrowprops=dict(arrowstyle="<->", color=dim_color, lw=1.2),
                zorder=5,
            )
            ax.text(sign * w / 2, -0.12 * R, f"w={w:.4g}", ha="center", fontsize=9, color=dim_color, zorder=6)

    # Height label on right side of rectangle
    if h > 0 and w > 0:
        ax.annotate(
            "",
            xy=(w + 0.08 * R, h),
            xytext=(w + 0.08 * R, 0.0),
            arrowprops=dict(arrowstyle="<->", color=dim_color, lw=1.2),
            zorder=5,
        )
        ax.text(w + 0.12 * R, h / 2, f"h={h:.4g}", ha="left", va="center", fontsize=9, color=dim_color, zorder=6)

    # --- Reference axis lines ---
    ax.axhline(0, color="#555", lw=0.8, zorder=0)
    ax.axvline(0, color="#555", lw=0.8, zorder=0)
    ax.text(R * 1.05, -0.04 * R, "x", fontsize=11, color="#555")
    ax.text(0.02 * R, R * 1.05, "y", fontsize=11, color="#555")

    # --- Centroid marker ---
    if y_bar is not None and failure_msg is None:
        cen_color = "#e67e22"
        ax.axhline(y_bar, color=cen_color, lw=1.5, linestyle=":", zorder=7)
        ax.scatter([0], [y_bar], color=cen_color, s=150, zorder=8, marker="+", linewidths=2.5)
        ax.text(
            0.06 * R, y_bar + 0.03 * R,
            f"ȳ = {y_bar:.4f} mm",
            fontsize=10, color=cen_color, fontweight="bold", zorder=9,
        )

    # --- Failure overlay ---
    if failure_msg:
        ax.text(
            0, R * 0.5, failure_msg,
            ha="center", va="center", fontsize=11,
            color="#c0392b", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.4", fc="#fadbd8", ec="#c0392b", lw=1.5),
            zorder=10,
        )

    pad = R * 0.25
    ax.set_xlim(-R - pad, R + pad * 2.5)
    ax.set_ylim(-R * 0.25, R + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    title = "Centroid of shaded area — Problem 5/53"
    if failure_msg:
        title += "  ⚠ INVALID GEOMETRY"
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    return fig, ax
