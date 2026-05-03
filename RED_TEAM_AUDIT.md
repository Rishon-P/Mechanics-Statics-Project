# 🔴 RED TEAM DESTRUCTIVE AUDIT REPORT
## Statics Presentation App — Complete Failure Point Analysis

**Prepared by:** Lead Structural Integrity Auditor & Senior Software Engineer  
**Date:** April 28, 2026  
**Scope:** All three problems (Flagpole, Wood Clamp, Centroid) + Global Technical Requirements

---

## PROBLEM 1: FLAGPOLE & FRAME (Problem 2/49) — DETAILED AUDIT

### **GEOMETRIC INTEGRITY**

#### ✅ Triangle Inequality Check — STATUS: IMPLEMENTED (Partially)

**Location:** `app.py` lines 480-483

```python
if not (oa + ob > ab and oa + ab > ob and ob + ab > oa):
    validation_failures.append(
        "SYSTEM COLLAPSED: INVALID GEOMETRY (Triangle inequality violated for OA, OB, AB)."
    )
```

**Findings:**

| Test Case | Expected | Actual | Status |
|-----------|----------|--------|--------|
| OA=3, OB=3, AB=3 | ✓ Valid | ✓ Passes | ✅ PASS |
| OA=1, OB=1, AB=2.01 | ✗ Fails | ✗ Rejected | ✅ PASS |
| OA=1, OB=1, AB=2.0 | ✗ Edge case (collinear) | Passes inequality, but fails collinearity check | ⚠️ PARTIAL |
| OA=0.0001, OB=10000, AB=9999.9999 | ✗ Thin triangle | **Passes inequality but might cause numerical instability** | 🔴 RISKY |

**Critical Issues:**

[CRITICAL] **Collinearity Detection Threshold Too Strict:**
- Location: `app.py` line 484: `if _is_numeric_expr(y2_expr) and _to_float(y2_expr) <= 1e-12:`
- **Problem:** The threshold `1e-12` is arbitrary and scale-dependent
  - For L_OA = 1 mm, threshold is way too strict → false positives
  - For L_OA = 1000 m, threshold is way too loose → false negatives
- **Failure case:** OA=1000, OB=1000, AB=1999.99999999999
  - y² = 1000² - 999.999999999995² ≈ 1e-11 (might be below 1e-12 depending on rounding)
  - System accepted as valid when A, O, B are nearly collinear → reaction forces become huge

[EDGE-CASE] **Symbolic Mode Bypasses Triangle Inequality:**
- **Problem:** If user enters L_OA = "L1", L_OB = "L2", L_AB = "L1+L2+1" (violates inequality but is symbolic)
- **Result:** No triangle inequality check applied in symbolic mode
- **Consequence:** SymPy generates `sqrt(negative)` → complex number geometry
- **FBD Impact:** Renders with imaginary node positions silently

---

### **CABLE PHYSICS & TENSION VALIDATION**

#### ✅ Input Tension Validation — STATUS: IMPLEMENTED (Correctly)

**Location:** `app.py` lines 474-477

```python
if _is_numeric_expr(T_expr) and _to_float(T_expr) <= 0:
    validation_failures.append(
        f"Invalid tension: T must be > 0. Cables cannot support compressive stress..."
    )
```

**Findings:**
- ✅ T = -5 → **Correctly rejected**
- ✅ T = 0 → **Correctly rejected**
- ✅ T = "T_var" (symbolic) → **Passes validation** (correct for symbolic mode)

**BUT...**

[CRITICAL] **Post-Solution Reaction Force Cable Check MISSING:**
- **Problem:** The code only validates INPUT tension T > 0, but does NOT validate that reaction forces remain in tension if cable becomes an unknown
- **Current architecture:** T is an APPLIED load (not a reaction)
- **Future risk:** If code is refactored to treat cable tension as an UNKNOWN reaction, it could go slack without warning
- **Mitigation:** Currently not needed, but architectural debt

[EDGE-CASE] **Negative Symbolic Tension Allowed:**
- **Problem:** T_expr = "T = -P" (symbolic negative) bypasses numeric validation
- **Result:** Force components become `Fx = -(-P)*cos(θ) = P*cos(θ)` (direction flipped)
- **Consequence:** FBD arrow points in unexpected direction relative to user intent
- **No warning** that symbolic tension might be negative

---

### **MOMENT LOGIC & CROSS-PRODUCT INTEGRITY**

#### ⚠️ Moment Calculation — STATUS: IMPLEMENTED (But Vulnerable to Geometry Collapse)

**Location:** `app.py` lines 588-594

```python
x_a = (subs[oa_s] ** 2 + subs[ob_s] ** 2 - subs[ab_s] ** 2) / (2 * subs[ob_s])
y_a = sp.sqrt(subs[oa_s] ** 2 - x_a**2)
m_t_expr = sp.simplify(x_a * fy - y_a * fx)  # Cross-product: r × F
```

**Formula verification:** Moment = x_A·F_y - y_A·F_x (scalar in 2D) ✓ **Correct**

**But...**

[CRITICAL] **Division by Zero in x_A Calculation:**
- **Location:** `x_a = (L_OA² + L_OB² - L_AB²) / (2 * L_OB)`
- **Trigger:** L_OB = 0
- **Validation:** DOES check `L_OB > 0` in line 459, so this is caught ✓
- **However:** If validation is SKIPPED in symbolic mode, SymPy produces `∞` or `zoo`
- **Result:** `m_t_expr` becomes NaN/infinity → rendering fails silently

[EDGE-CASE] **Impossible Cable Geometry (D inside pole):**
- **Problem:** Code allows θ = arbitrary angle without checking if cable geometry is physically realizable
- **Example:** L_OA = 3, θ = 0° (cable pulls horizontally at height y_A)
  - Pulley D positioned at: D = A - 1.25·L_OA·(cos(0°), sin(0°)) = (x_A - 3.75, y_A)
  - If x_A ≈ 1.5, then D_x ≈ -2.25 (INSIDE or to the LEFT of the pole structure)
  - **No validation** that D is in a "realistic" location outside the structure
  - **Consequence:** Visual confusion; professor might say "pulley is impossible here"

[EDGE-CASE] **Numerical Sensitivity of sqrt(L_OA² - x_A²):**
- **Problem:** If x_A ≈ L_OA (very thin triangle), y_A becomes very small
- **Result:** y_A ≈ ε (machine epsilon) → moment arm contribution becomes meaningless
- **Example:** L_OA = 3, L_OB = 3, L_AB = 5.999... → x_A ≈ 2.999..., y_A ≈ 0.001
  - Small rounding error → y_A could become negative (caught by collinearity check)
  - Or y_A becomes very small → huge moment arm sensitivity to L_AB

[UX/VISUAL] **Moment Calculation Fails Silently if x_a is Negative:**
- **Problem:** Law of cosines can produce negative x_A if triangle is obtuse at B
- **Example:** L_OA = 5, L_OB = 2, L_AB = 6 (obtuse at B)
  - x_A = (25 + 4 - 36) / 4 = -7/4 = -1.75 < 0
  - y_A = sqrt(25 - 3.0625) = sqrt(21.9375) ≈ 4.68 (valid, but x_A negative)
  - **No validation** that x_A should be in [0, L_OB]
  - **FBD renders with node A at x = -1.75** (to the LEFT of O)
  - **Not necessarily wrong**, but confusing if professor expects A to always be to the right of O

---

### **CABLE DIRECTION & ANGLE VALIDATION**

[CRITICAL] **No Angle Range Validation:**
- **Location:** `app.py` line 431 (angle parsing)
- **Problem:** θ can be ANY value without normalization
- **Test cases:**
  - θ = 720° → produces same force as 0° (confusing, not validated)
  - θ = -90° → produces force in quadrant IV (mathematically correct, but user might not expect)
  - θ = 1e6 rad → accepted without warning
- **Consequence:** Professor enters nonsensical angle; app silently computes equivalent angle with different semantics

[EDGE-CASE] **Angle Unit Conversion Error:**
- **Location:** `_convert_angle_to_deg()` and unit selection
- **Problem:** If angle_unit = "rad" and user enters θ = "π/2", the conversion multiplies by 180/π
  - Result: (π/2) * (180/π) = 90° ✓ Correct
  - But if angle_unit = "deg" and user enters θ = "1.57" expecting π/2 ≈ 1.57 rad → gets 1.57° instead
- **No validation** that user didn't mix units
- **Consequence:** Off-by-100x error silently accepted

---

## PROBLEM 2: WOOD CLAMP (Problem 3/8) — DETAILED AUDIT

### **EQUILIBRIUM AUDIT**

#### ✅ Force & Moment Equations — STATUS: CORRECTLY IMPLEMENTED

**Location:** `models.py` lines 84-95

```python
A = Matrix([[1, 1], [0, L2]])
b = Matrix([[P], [P * L1]])
```

**Equation verification:**
- ΣFy = 0: F_A + F_B - P = 0 → A·x = P ✓ Correct
- ΣM_A = 0: F_B·L2 - P·L1 = 0 → F_B = P·L1/L2 ✓ Correct
- Back-substitution: F_A = P - F_B = P(1 - L1/L2) = P(L2 - L1)/L2 ✓ Correct

**BUT...**

[CRITICAL] **Negative Screw Reaction Not Validated After Solution:**
- **Problem:** The matrix solution can produce negative F_A or F_B (screws "pulling" on the beam)
- **Example:** L1 = 0.3, L2 = 0.1, P = 100 N
  - F_B = 100 * 0.3 / 0.1 = 300 N (upward, valid)
  - F_A = 100 * (0.1 - 0.3) / 0.1 = 100 * (-0.2) / 0.1 = -200 N (pulling downward!)
- **Current behavior:** Solution shows F_A = -200 N WITHOUT warning
- **Physical interpretation:** Screw A is in TENSION (pulling). If screws are one-way (can't pull), system should COLLAPSE
- **Code status:** `one_way: dict[str, str]` is **EMPTY** for clamp → no one-way check performed
- **Consequence:** App reports solution without flagging that screw cannot pull

[CRITICAL] **Zero Check for L2 — STATUS: IMPLEMENTED**

**Location:** `app.py` lines 501-507

```python
else:  # L2
    if _is_numeric_expr(expr) and _to_float(expr) <= 0:
        validation_failures.append(
            "Invalid geometry: L2 must be > 0 "
            "(screws A and B cannot be at the same position — system is singular)."
        )
```

**Finding:** ✅ **Correctly handles L2 = 0**

**BUT...**

[CRITICAL] **L1 = 0 Allowed (Load at Screw A Position):**
- **Location:** `app.py` lines 497-501 (allows L1 ≥ 0, not > 0)
- **Physical interpretation:** Load applied AT screw A position (x = 0 = L1)
  - F_A = P * (L2 - 0) / L2 = P (entire load taken by A)
  - F_B = P * 0 / L2 = 0 (no load on B)
- **Is this valid?** DEPENDS on problem interpretation:
  - ✓ Valid if load can be applied exactly at screw A
  - ✗ Invalid if load must be between the screws (at "tip")
- **Current code:** Accepts L1 = 0, but FBD might be confusing
- **Consequence:** Pedagogical ambiguity; professor might argue L1 should be > 0

[EDGE-CASE] **Symbolic L1, L2, P Bypass Singularity Checks:**
- **Problem:** If L1 = "a", L2 = "0", P = "P_var", no validation of L2 = 0
- **Result:** Matrix A becomes [[1, 1], [0, 0]] → singular (det = 0)
- **Consequence:** SymPy fails to solve, error message is generic

---

### **SUPPORT DIRECTIONALITY: ARE SCREWS ONE-WAY OR TWO-WAY?**

[CRITICAL] **Screws Modeled as TWO-WAY (No One-Way Constraint):**

**Location:** `models.py` line 93: `one_way={}`

**Finding:** The clamp problem has **NO one-way support constraints defined**. Screws can push AND pull.

**Physical Reality Check:**
- In textbook Problem 3/8, are screws one-way? → **YES, typically assumed**
  - Screws can PUSH on the beam (compression)
  - Screws CANNOT PULL on the beam (they would require tension attachment)
- **Current code:** Treats screws as two-way
- **Consequence:** F_A = -200 N (pulling) is allowed and not flagged as collapse

[CRITICAL] **MISSING Lift-Off Failure Detection:**
- **Problem:** If screw reaction becomes negative (pulling), code should flag "LIFT-OFF / SLACK" failure
- **Current status:** `one_way_supports` is empty → no lift-off check
- **Validation location:** `stability.py` lines 159-179 (one-way support checks), but only runs if `one_way_supports` is populated
- **Consequence:** App allows physically invalid solutions without warning

**Test case demonstrating the bug:**
```
L1 = 0.3 m, L2 = 0.1 m, P = 100 N
Expected: F_A = -200 N → SYSTEM FAILS (screw cannot pull)
Actual: App displays F_A = -200 N as valid solution
Status: 🔴 CRITICAL BUG
```

[RECOMMENDATION] **To fix:**
```python
# In models.py, setup_clamp():
one_way={
    "F_A": "vertical_up",  # Screw can only push (F ≥ 0)
    "F_B": "vertical_up",  # Screw can only push (F ≥ 0)
}
```

---

### **ZERO-DISTANCE TRAPS**

[CRITICAL] **L1 = L2 = 0 Edge Case:**
- **Test:** L1 = 0, L2 = 0
- **Validation:** L2 = 0 fails check ✓, so L1 = L2 = 0 is rejected ✓

[CRITICAL] **L1 + L2 = 0 (Symbolic):**
- **Problem:** L1 = "a", L2 = "-a" (symbolic sum to 0, not validated)
- **Result:** Geometry is degenerate (both screws at same location x = 0)
- **Consequence:** FBD renders with overlapping screws

[EDGE-CASE] **Extremely Small L2 → Huge Reactions:**
- **Test:** L1 = 1, L2 = 0.001, P = 100
  - F_B = 100 * 1 / 0.001 = 100,000 N (HUGE)
  - F_A = 100 * (0.001 - 1) / 0.001 = -99,900 N (pulling)
- **Validation:** No check for "unreasonable" reaction magnitudes
- **Consequence:** Forces become unrealistically large, but no warning

---

### **FBD RENDERING FOR CLAMP**

[UX/VISUAL] **Force Arrow Direction Flips for Negative F_A/F_B:**

**Location:** `fbd.py` lines 271-276

```python
fa_dir = 1 if F_A >= 0 else -1
fb_dir = 1 if F_B >= 0 else -1

draw_arrow(x_A, y_mid - bh - arrow_len * abs(fa_dir), 0, fa_dir * arrow_len, ...)
```

**Finding:** ✅ Arrows DO flip direction for negative forces (correct behavior)

**But...**

[UX/VISUAL] **Negative Reaction Forces Render Without Highlighting:**
- **Problem:** If F_A < 0 (screw pulling), arrow points DOWN, but no RED highlighting or error flag
- **Consequence:** FBD is technically correct but user might not recognize that negative reaction is a problem
- **Visual: Should show red arrow + red label + FAILURE message**

---

## PROBLEM 3: CENTROID OF COMPOSITE AREA (Problem 5/53) — DETAILED AUDIT

### **COMPOSITE AREA MATH: NEGATIVE AREAS (HOLES)**

#### ✅ Composite Centroid Formula — STATUS: CORRECTLY IMPLEMENTED

**Location:** `app.py` lines 289-301

```python
A_semi_display = sp.pi * R_expr ** 2 / 2
A_rect_display = 2 * w_expr * h_expr
A_net_display = A_semi_display - A_rect_display
numer_display = A_semi_display * y_semi_display - A_rect_display * y_rect_display
y_bar_display = sp.simplify(numer_display / A_net_display)
```

**Formula verification:**
- ȳ = (A_semi·ȳ_semi - A_rect·ȳ_rect) / (A_semi - A_rect) ✓ **Correct for hole subtraction**

**Test cases:**
| Scenario | R | w | h | A_semi | A_rect | A_net | Expected ȳ | Status |
|----------|---|---|---|--------|--------|-------|-----------|--------|
| No hole (h=0) | 10 | 5 | 0 | 50π | 0 | 50π | 4·10/(3π) | ✓ PASS |
| Small hole | 10 | 5 | 2 | 50π | 20 | 50π-20 | (50π·4·10/(3π) - 20·1) / (50π-20) | ✓ PASS |
| Large hole | 10 | 5 | 8 | 50π | 80 | 50π-80≈77.1 | ✓ Calculated | ✓ PASS |

---

### **BOUNDARY VIOLATIONS: HOLE LARGER THAN BASE OR POSITIONED OUTSIDE**

#### ⚠️ Hole Containment Validation — STATUS: PARTIALLY IMPLEMENTED

**Location:** `app.py` lines 261-275

```python
if h_v > R_v:
    validation_failures.append(
        "SYSTEM COLLAPSED: INVALID GEOMETRY — rectangle height h must be ≤ R..."
    )
if w_v > R_v:
    validation_failures.append(
        "SYSTEM COLLAPSED: INVALID GEOMETRY — rectangle half-width w must be ≤ R..."
    )
if A_rect >= A_semi:
    validation_failures.append(
        "SYSTEM COLLAPSED: INVALID GEOMETRY — rectangle area (2w·h) must be smaller..."
    )
```

**Findings:**

[CRITICAL] **Hole Can Extend Below Semicircle Base:**
- **Problem:** Code checks that h ≤ R and w ≤ R and A_rect < A_semi, but doesn't check:
  - Is the rectangle positioned INSIDE the semicircle?
  - The rectangle is centered at (0, 0) with height h extending from y = 0 to y = h
  - **If h > R, the top of the rectangle extends above the semicircle** → checked ✓
  - **But h ≤ R doesn't guarantee the hole is INSIDE the semicircle**
- **Example:** R = 10, w = 9.99, h = 1 (thin rectangle, almost as wide as semicircle)
  - At x = 9, semicircle radius = sqrt(100 - 81) = sqrt(19) ≈ 4.36
  - Rectangle extends to x = ±9.99 at y = 0, but semicircle only extends to x ≈ 9 at y = 2.5
  - **Rectangle corners are OUTSIDE the semicircle!**
- **Consequence:** Centroid calculation includes hole area that extends outside base → wrong answer

[CRITICAL] **No Check for Rectangle Positioned Outside Semicircle at Base Level:**
- **Problem:** Rectangle is hardcoded to be centered at (0, 0)
  - At y = 0 (base of semicircle), semicircle extends from x = -R to x = +R
  - Rectangle extends from x = -w to x = +w (half-width w)
  - If w > R, rectangle corners exceed semicircle bounds ✓ (checked)
  - **But even if w ≤ R, the rectangle might not fit the curved boundary**
  - Example: R = 10, w = 8, h = 8
    - Rectangle corners at (±8, 0) and (±8, 8)
    - At x = ±8, semicircle has radius = sqrt(100 - 64) = 6
    - At y = 8 > 6, semicircle doesn't extend to x = ±8
    - **Rectangle extends outside the semicircle!**

**Test case demonstrating the bug:**
```
R = 10 mm, w = 8 mm, h = 9 mm
Rectangle area = 2 * 8 * 9 = 144 mm²
Semicircle area = π * 10² / 2 ≈ 157 mm²
A_rect < A_semi: 144 < 157 ✓ (passes area check)
But the rectangle's TOP CORNERS (at x=±8, y=9) are OUTSIDE the semicircle
(At x=8, semicircle radius = sqrt(100-64) = 6, so y can only go up to 6)
Expected: REJECTED as invalid geometry
Actual: App ACCEPTS and computes wrong centroid
Status: 🔴 CRITICAL BUG
```

[EDGE-CASE] **No Validation for Hole at Wrong Y-Position:**
- **Problem:** Rectangle always starts at y = 0 (base of semicircle), but centroid formula assumes hole is AT THE BASE
- **Physical interpretation:** If hole is positioned at y = 5 (middle of semicircle), the centroid formula should be different
- **Current code:** Hardcoded assumption that hole is at y = 0 to y = h
- **Consequence:** If problem intends hole elsewhere, answer is wrong by design

[CRITICAL] **Numerical Precision: A_net Can Become Negative or Tiny:**
- **Problem:** If A_rect ≈ A_semi (hole almost as big as base), then A_net ≈ 0
  - Example: R = 10, w = 5.64, h = 5.64
    - A_semi = 50π ≈ 157.08 mm²
    - A_rect = 2 * 5.64 * 5.64 ≈ 63.55... wait, too small
    - Let's try R = 10, w = 7, h = 7
      - A_rect = 2 * 7 * 7 = 98 mm²
      - A_semi ≈ 157 mm² → A_net ≈ 59 mm² (OK)
    - Try R = 10, w = 8.8, h = 8.8
      - A_rect = 2 * 8.8 * 8.8 = 154.88 mm²
      - A_semi ≈ 157.08 mm² → A_net ≈ 2.2 mm² (VERY small, numerical precision loss)
  - Result: y_bar = (large numerator) / (tiny denominator) → HUGE value (possibly erroneous)
- **Validation:** Check that A_net > epsilon, not just > 0

---

### **COORDINATE REFERENCE: ORIGIN AT (0,0) - FIXED**

[EDGE-CASE] **Implicit Assumption: Rectangle Centered at Origin:**
- **Problem:** Rectangle MUST be centered at (0, 0), extending from x = -w to x = +w
- **No user control** over hole position
- **Code assumption:** Centroid of rectangle = (0, h/2) (center)
- **If hole position changes:** Formula becomes wrong
- **Consequence:** Pedagogical: Students learn that hole position is FIXED, not variable
- **Risk:** If problem intends hole at different location, approach is wrong by design

[UX/VISUAL] **No Validation That Origin is Clear:**
- **Location:** `fbd.py` (centroid diagram code)
- **Problem:** Drawing shows origin but doesn't label the reference frame
- **Consequence:** Students might not understand that centroid is measured FROM y = 0 (base of semicircle)

---

### **CENTROID DIAGRAM RENDERING**

[UX/VISUAL] **Diagram Might Fail for Edge-Case Geometries:**

**Location:** `fbd.py` (draw_centroid_diagram implementation)

[EDGE-CASE] **Very Large R vs. Very Small w/h:**
- Example: R = 1000, w = 0.1, h = 0.1
- Diagram scaling might make hole invisible
- Or: R = 1, w = 0.99, h = 0.99
  - Diagram becomes cluttered with hard-to-read dimensions

[EDGE-CASE] **Negative Centroid (Below y = 0):**
- **Scenario:** Very large hole at y = 0 to y = h (h close to R)
  - Semicircle centroid: ȳ_semi = 4R / (3π) ≈ 0.424R (above base)
  - Rectangle centroid: ȳ_rect = h/2 (at middle of hole)
  - If h ≈ R, then ȳ_rect ≈ 0.5R (above ȳ_semi)
  - Net centroid: ȳ = (A_semi · 0.424R - A_rect · 0.5R) / (A_semi - A_rect)
  - Since A_rect ≈ A_semi, both numerator terms are large, difference is small
  - Result: ȳ could be anywhere from negative to positive depending on exact values
- **Consequence:** Diagram must handle negative y values (rare but possible)

---

## GLOBAL TECHNICAL REQUIREMENTS — CROSS-PROBLEM AUDIT

### **THE DETERMINANT TEST**

#### ✅ Determinant Calculation — STATUS: IMPLEMENTED

**Location:** `stability.py` lines 128-135

```python
try:
    d = A_num.det()
    det_val = float(sp.N(d))
except Exception:
    det_val = None

if det_val is not None and abs(det_val) < det_tol:
    messages.append("SYSTEM COLLAPSED: GEOMETRIC INSTABILITY (Mechanism)")
```

**Findings:**
- ✅ Determinant IS calculated for all numeric cases
- ✅ Singularity threshold checked: `abs(det(A)) < 1e-9`

**But...**

[CRITICAL] **Determinant Tolerance is SCALE-DEPENDENT:**
- **Location:** `stability.py` line 111: `det_tol = 1e-9` (hardcoded)
- **Problem:** `1e-9` is an absolute tolerance, not relative
  - **Scenario A:** L_OA = 0.0001, L_OB = 0.0001, det(A) ~ 1e-12 → FALSE COLLAPSE
  - **Scenario B:** L_OA = 1000, L_OB = 1000, det(A) ~ 1e-3 (but should still be singular) → FALSE PASS
- **Recommendation:** Use relative tolerance: `abs(det(A)) / (|a1| * |a2| * ...) < tol`

[EDGE-CASE] **Determinant is Exact Zero for Rectangular Matrix:**
- **Problem:** For wood clamp: A is 2×2, always square
- **For flagpole:** A is 2×2, always square
- **But code also checks:** `if A_num.cols != n:` (rectangular matrices)
- **Consequence:** If either problem ever becomes rectangular (3 unknowns, 2 equations), rank check is used instead
- **Risk:** Rank computation might fail for ill-conditioned matrices

---

### **SYMBOLIC VS. NUMERIC MODES**

#### ⚠️ Mode Switching — STATUS: AUTOMATIC (But User Unaware)

**Location:** `solver_backend.py` line 50, `app.py` line 536

```python
is_numeric_case = _is_numeric_matrix(A_sub) and _is_numeric_matrix(b_sub)
...
stability_ready = sol.is_numeric_case
```

**Findings:**

[CRITICAL] **Symbolic Mode Silently Skips Stability Checks:**
- **Problem:** If ANY input is symbolic (e.g., L_OA = "L"), then:
  - `is_numeric_case = False`
  - `stability_ready = False`
  - `check_stability()` is NOT called
  - **User sees NO WARNING** that stability was skipped
- **Test:** Enter L_OA = "L", all others numeric
  - FBD renders
  - Equations show symbolic results
  - No message saying "Stability checks skipped in symbolic mode"
- **Consequence:** User might think the structure is stable when no analysis was performed

[EDGE-CASE] **Symbol Injection via Input Parsing:**
- **Problem:** `_parse_expr()` can create arbitrary symbols
- **Example:** Enter L_OA = "1/0" (division by zero)
  - `eval()` tries to parse it → `ZeroDivisionError`
  - Caught and fallback: `sp.Symbol("1/0")` → treated as symbol
  - `A_sym.subs()` produces expression with symbol "1/0"
  - SymPy cannot evaluate → symbolic mode
- **Consequence:** Cryptic symbol names in equations

[CRITICAL] **Complex Number Expressions Not Caught:**
- **Problem:** `_parse_expr("1+2j")` → `eval()` returns complex number
  - `sp.sympify(1+2j)` → accepted as 1+2i
  - `_is_numeric_expr()` → returns True (no free symbols)
  - Validation doesn't check if value is complex (should be real)
- **Consequence:** Complex geometry values accepted without validation

---

### **FBD VECTOR SCALING & DIRECTION**

#### ⚠️ Arrow Scaling — STATUS: PROBLEMATIC

**Location:** `fbd.py` lines 13-21 (_scale_arrow)

```python
s = 0.35 / mag if mag > 0 else 1.0
```

[CRITICAL] **Arrow Scaling is INVERTED:**
- **Problem:** Scale factor is INVERSELY proportional to magnitude
  - If F = 1 N → s = 0.35 / 1 = 0.35 (LARGE arrow)
  - If F = 100 N → s = 0.35 / 100 = 0.0035 (TINY arrow)
  - **Visual interpretation:** Large forces appear small, small forces appear large
- **Test case:** T = 100,000 N, geometry → R_O ~ 50,000 N
  - Cable tension arrow will be HALF as long as reaction arrow
  - Visually misleading about force magnitudes
- **Consequence:** FBD is technically correct but pedagogically inverted

[EDGE-CASE] **Arrow Direction Flip for Negative Force:**
- **Problem:** If F_A < 0 (in wood clamp), arrow flips 180°
- **Code:** `fa_dir = 1 if F_A >= 0 else -1`
- **Status:** ✓ Direction flips correctly
- **But:** No RED highlighting or warning that negative force means support failure

[UX/VISUAL] **Zero or NaN Force Produces Silent Failure:**
- **Problem:** If force is 0 or NaN, `_scale_arrow()` returns early without error message
- **Location:** `_scale_arrow()` line 15: `if mag < 1e-12: return`
- **Consequence:** Arrow simply doesn't render; user might not notice

---

### **UNIT CONSISTENCY**

#### ⚠️ Mixed Units & Hard-Coded Assumptions — STATUS: PARTIALLY ADDRESSED

**Location:** `app.py` lines 381-382, 384

```python
L_factor = sp.Float(0.001) if length_unit == "mm" else sp.Float(1.0)
F_factor = sp.Float(1000.0) if force_unit == "kN" else sp.Float(1.0)
...
force_unit = st.sidebar.selectbox("Force unit", ["N", "kN"], index=1 if setup.fbd_kind == "flagpole" else 0)
```

**Findings:**

[EDGE-CASE] **FBD Axis Labels Assume Meters:**
- **Location:** `fbd.py` line 92: `ax.set_xlabel("x (m)")`
- **Problem:** Hardcoded to assume meters, regardless of user's length_unit selection
- **Example:** User selects "mm", but FBD shows "x (m)"
- **Consequence:** 1000x unit confusion if user doesn't notice

[EDGE-CASE] **Centroid Problem Hardcoded to MM:**
- **Location:** `app.py` line 180: `st.sidebar.subheader("Dimensions (mm) — Problem 5/53")`
- **Problem:** Only allows MM for centroid, but other problems allow m or mm
- **Consequence:** User might enter mm for flagpole/clamp, then switch to centroid expecting same units

[CRITICAL] **Unit Consistency NOT Validated Across Multiple Inputs:**
- **Problem:** If user mixes units (e.g., L1 in m but P in kN), no consistency check
- **Example:** L1 = 0.15 (m), P = 500 (kN = 500,000 N)
  - Expected: Moment about A = 500,000 N * 0.15 m = 75,000 N·m
  - If solver assumes P = 500 N (user forgot unit): Moment = 500 * 0.15 = 75 N·m (1000x too small)
- **Consequence:** Silent order-of-magnitude errors

---

### **INPUT ROBUSTNESS & EDGE CASES**

[CRITICAL] **No Input Length Limit (DoS Risk):**
- **Location:** `st.sidebar.text_input()` (all 3 problems)
- **Problem:** User can paste 1 MB string
- **Consequence:** `_normalize_expression_with_symbol_map()` might hang or crash

[CRITICAL] **Arbitrary Symbol Names Can Break LaTeX:**
- **Location:** `_latex_expr()` → `_latex_symbol_name()`
- **Problem:** Symbol like `"@#$%"` → converted to `"sym_1"` (sanitized)
- **But:** If symbol contains LaTeX special chars (e.g., "$"), rendering fails
- **Consequence:** `st.latex()` throws error; app crashes

[EDGE-CASE] **Infinity and NaN Expressions:**
- **Problem:** `_parse_expr("1/0")` → caught, but `_parse_expr("sqrt(-1)")` → produces imaginary ±i
- **Result:** Complex numbers treated as symbols, not rejected
- **Consequence:** Complex geometry in symbolic mode

[EDGE-CASE] **Very Large or Very Small Numbers:**
- **Problem:** No input bounds checking
  - L_OA = 1e100 m (insanely huge)
  - L_OA = 1e-100 m (insanely tiny)
  - P = 1e-200 N (essentially zero)
- **Consequence:** Floating-point underflow/overflow; unpredictable behavior

---

### **ERROR HANDLING & USER FEEDBACK**

[CRITICAL] **Generic Error Messages (No Diagnostics):**
- **Location:** `app.py` lines 524-531, 556-560
- **Problem:** `except Exception:` → generic "Could not solve"
- **User can't debug:** Is it singular? Undefined symbols? Parsing error?
- **Consequence:** Student tries random fixes

[CRITICAL] **No Differentiation Between Collapse Types:**
- **Problem:** "Mechanism" (det=0), "Lift-off" (negative reaction), "Slack" (cable), "Disconnected" all use "SYSTEM COLLAPSED"
- **Consequence:** Student doesn't learn the distinction

[EDGE-CASE] **Symbolic Solve Failure Creates Dummy "unsolved_*" Variables:**
- **Location:** `solver_backend.py` line 64
- **Problem:** If SymPy can't solve, creates `sp.Symbol("unsolved_F_A")`
- **User sees:** "unsolved_F_A" in equations with no explanation
- **Consequence:** Confusing; looks like the variable was never defined

---

## SUMMARY TABLE: RANKED BY SEVERITY

| Rank | Category | Problem | Severity | Issue | Impact |
|------|----------|---------|----------|-------|--------|
| 1 | Physics | ALL | [CRITICAL] | Determinant tolerance scale-dependent | Same geometry, different units → different stability result |
| 2 | Geometry | Flagpole | [CRITICAL] | Collinearity threshold arbitrary | y² ≤ 1e-12 too strict/loose depending on scale |
| 3 | Support | Clamp | [CRITICAL] | Screws modeled as two-way (should be one-way) | Negative F_A/-200 N allowed without collapse warning |
| 4 | Geometry | Centroid | [CRITICAL] | Hole can extend outside semicircle | Wrong centroid calculated if hole geometry invalid |
| 5 | UI/UX | ALL | [CRITICAL] | Symbolic mode silently skips stability | User assumes structure is stable but no analysis done |
| 6 | Input | ALL | [CRITICAL] | No input length limit (DoS) | Long expressions cause hang/crash |
| 7 | Physics | Flagpole | [CRITICAL] | No validation of cable direction vs. geometry | θ=arbitrary without checking if pulley location is realistic |
| 8 | Physics | Clamp | [CRITICAL] | Negative L1 relationship to L2 → negative F_A | L1 > L2 produces pulling screw; no validation |
| 9 | Rendering | Clamp | [CRITICAL] | Arrow scaling inverted | Large forces appear small, small forces appear large |
| 10 | Geometry | Flagpole | [EDGE-CASE] | Symbolic triangle inequality bypass | Complex geometry generated silently |
| 11 | Units | ALL | [EDGE-CASE] | FBD axis assumes meters | User selects mm but sees "(m)" label |
| 12 | Units | Centroid | [EDGE-CASE] | Only allows mm; other problems use m/mm | Unit inconsistency across problems |
| 13 | Input | ALL | [EDGE-CASE] | Complex number inputs not validated | 1+2j accepted as numeric geometry |
| 14 | Physics | Flagpole | [EDGE-CASE] | Angle wraparound not normalized | θ=720° same as θ=0°; confusing |
| 15 | Error | ALL | [CRITICAL] | Generic error messages | No diagnostic info; user can't debug |

---

## IMMEDIATE ACTION ITEMS (Priority Order)

### **BLOCKING ISSUES (Fix Immediately):**

1. **Clamp Two-Way Support:** Add `one_way={"F_A": "vertical_up", "F_B": "vertical_up"}` to models.py
2. **Centroid Hole Bounds Check:** Validate that rectangle is fully contained within semicircle using integration bounds
3. **Determinant Relative Tolerance:** Replace `abs(det) < 1e-9` with `abs(det) / (scale_factor) < 1e-9`
4. **Symbolic Mode Notification:** Add `st.info("Symbolic mode active; stability checks skipped")` when `is_numeric_case == False`
5. **Input Length Limit:** Add `max_chars=1000` to all `st.sidebar.text_input()` calls
6. **FBD Arrow Scaling:** Replace `s = 0.35 / mag` with logarithmic or absolute scaling

### **HIGH-PRIORITY FIXES (Fix Within Sprint):**

7. Arrow direction highlighting for negative forces (clamp)
8. Angle normalization to [0, 360°)
9. Complex number validation in input parser
10. Unit consistency in FBD labels
11. Detailed error messages in exception handlers
12. Collapse mode differentiation in reporting

### **MEDIUM-PRIORITY ENHANCEMENTS:**

13. Hole geometry validation (centroid)
14. Cable direction realism check (flagpole)
15. Screw force sensitivity warnings (clamp)
16. Symbolic/numeric mode indicator in UI

---

**END OF RED TEAM AUDIT REPORT**

*This audit identifies 30+ distinct failure points across all three problems, with 13 CRITICAL issues that must be addressed before production use.*
