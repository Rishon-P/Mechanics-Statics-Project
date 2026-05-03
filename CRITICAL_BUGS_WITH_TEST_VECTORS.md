# 🔴 CRITICAL BUGS — VISUAL REFERENCE & TEST VECTORS

## TOP 13 CRITICAL FAILURES

---

## **FAILURE #1: CLAMP SCREWS CAN PULL (Two-Way Modeled as Screws)**

```
PROBLEM: Screws modeled as two-way supports (can push AND pull)
PHYSICAL REALITY: Screws can only PUSH on beam; cannot PULL

TEST VECTOR:
  L1 = 0.3 m      (load at 0.3m from tip)
  L2 = 0.1 m      (screw separation = 0.1m)
  P = 100 N       (downward load)

EXPECTED RESULT:
  F_A = 100 * (0.1 - 0.3) / 0.1 = -200 N   ← PULLING UPWARD
  F_B = 100 * 0.3 / 0.1 = 300 N            ← PUSHING UPWARD
  
  Status: 🔴 SYSTEM FAILS (screw A cannot pull)
  Expected output: "SYSTEM COLLAPSED: SUPPORT FAILURE (Lift-off at A)"

ACTUAL RESULT:
  App displays: F_A = -200 N, F_B = 300 N  ✓ (values correct)
  But: NO RED HIGHLIGHTING, NO COLLAPSE WARNING             ← BUG
  App treats as valid solution

ROOT CAUSE:
  models.py line 93: one_way={}  (empty! no one-way constraints)
  stability.py: one_way checks skipped because dict is empty

IMPACT: Student thinks negative screw reaction is acceptable; learns wrong physics
```

---

## **FAILURE #2: DETERMINANT TOLERANCE IS SCALE-DEPENDENT**

```
PROBLEM: Hardcoded absolute tolerance det_tol = 1e-9 (not relative)

TEST VECTOR A (TINY GEOMETRY):
  L_OA = 0.0001 m, L_OB = 0.0001 m, L_AB = 0.0001 m
  Expected det(A): ~ 1e-12 (valid triangle)
  Threshold: 1e-9
  Result: 🔴 FALSE COLLAPSE (det < tol incorrectly triggers)

TEST VECTOR B (HUGE GEOMETRY):
  L_OA = 1000 m, L_OB = 1000 m, L_AB = 1999.99 m
  Expected det(A): ~ 1e-4 (nearly singular, but technically valid)
  Threshold: 1e-9
  Result: ✓ PASSED (but should warn about near-singularity)

PROBLEM: Same triangle geometry + same quality
  → Different result depending on scale/unit choice!

ROOT CAUSE:
  stability.py line 111: det_tol = 1e-9  (absolute tolerance)
  Should use: det_tol_rel = 1e-9 * max(|det(scaled A)|)

IMPACT: 
  - Geometry that's valid in meters might collapse in mm
  - Users can't trust stability analysis across unit systems
```

---

## **FAILURE #3: CENTROID HOLE EXTENDS OUTSIDE SEMICIRCLE**

```
PROBLEM: Rectangle can have corners OUTSIDE the semicircle base shape

TEST VECTOR:
  R = 10 mm        (semicircle radius)
  w = 8 mm         (hole half-width)  
  h = 8 mm         (hole height)
  
  Rectangle dimensions: x ∈ [-8, 8], y ∈ [0, 8]
  Rectangle corners: (±8, 0) and (±8, 8)
  
  At y = 8: semicircle radius = √(100 - 64) = 6 mm
            So semicircle only extends to x ∈ [-6, 6] at y = 8
            Rectangle corners (±8, 8) are OUTSIDE!

VALIDATION CHECKS:
  ✓ h ≤ R: 8 ≤ 10 (PASS)
  ✓ w ≤ R: 8 ≤ 10 (PASS)
  ✓ A_rect < A_semi: 128 < 157 (PASS)
  ✓ All numeric checks PASS
  
BUT:
  ✗ Rectangle corners extend outside semicircle boundary (FAIL)
  ✗ No boundary containment check performed

EXPECTED: 🔴 SYSTEM COLLAPSED: INVALID GEOMETRY
ACTUAL: App calculates centroid with WRONG assumption

ROOT CAUSE:
  app.py lines 261-275: Only checks dimensions, not containment
  Missing check: For each corner (x_corner, y_corner), verify
    x_corner² + (R - y_corner)² ≤ R²  (must be inside semicircle)

IMPACT:
  Calculated centroid = WRONG
  Student learns incorrect answer
  Problem appears valid but math is invalid
```

---

## **FAILURE #4: SYMBOLIC MODE SILENTLY SKIPS STABILITY**

```
PROBLEM: When ANY input is symbolic, stability checks don't run
         BUT no warning is displayed to user

TEST VECTOR:
  L_OA = "L" (symbolic variable)
  L_OB = 3 (numeric)
  L_AB = 3 (numeric)
  T = 5 (numeric)
  theta = 20 (numeric)

EXPECTED BEHAVIOR:
  If symbolic: Show message "Symbolic mode active; stability checks skipped"
  OR compute algebraic stability (advanced)

ACTUAL BEHAVIOR:
  App:
    ✓ Solves equations symbolically
    ✓ Shows symbolic results: R_Ox = -T*cos(θ), etc.
    ✓ Renders FBD
    ✗ NO MESSAGE that stability wasn't checked
    ✗ User assumes structure is stable

CONSEQUENCE:
  User enters: "Is this system deterministic?"
  App shows solution but never checks determinacy
  User might submit answer assuming stability was validated

ROOT CAUSE:
  app.py line 536: stability_ready = sol.is_numeric_case
  If False, check_stability() skipped silently
  No user notification

FIX:
  Add: if not stability_ready:
       st.info("⚠️ Symbolic mode: Stability checks skipped")

IMPACT: Student misunderstands when analysis is complete
```

---

## **FAILURE #5: ARROW SCALING IS INVERTED**

```
PROBLEM: Force arrows scaled INVERSELY to magnitude
         Large forces → small arrows; small forces → large arrows

TEST VECTOR:
  Cable tension: T = 100,000 N (huge)
  Hinge reaction: R_O ≈ 50,000 N (still large, but smaller)
  
  Expected: Cable tension arrow ≈ 2× longer than reaction
  Actual: Cable tension arrow ≈ ½ as long as reaction ← INVERTED!

CODE:
  _scale_arrow() in fbd.py line 17:
    s = 0.35 / mag    ← INVERSE proportional
    
  mag = 100,000 N → s = 3.5e-6 (TINY)
  mag = 50,000 N  → s = 7e-6  (MEDIUM)
  
  Visually: 50,000 N arrow is 2× longer!
  Semantically: Forces are backwards relative to magnitude

VISUAL CONSEQUENCE:
  Student looks at FBD and sees:
    - Tiny arrow labeled "T = 100 kN"
    - Huge arrow labeled "R_O = 50 kN"
  
  Conclusion: "The reaction is much bigger than the load?"
  Actual physics: Cable tension and reaction are comparable

ROOT CAUSE:
  fbd.py line 17: s = 0.35 / mag
  Should be: s = 0.35 (constant) or logarithmic scaling

IMPACT: FBD is pedagogically misleading about force magnitudes
```

---

## **FAILURE #6: COLLINEARITY THRESHOLD SCALE-DEPENDENT**

```
PROBLEM: Threshold y² ≤ 1e-12 is arbitrary, not scale-normalized

TEST VECTOR A (SMALL GEOMETRY):
  L_OA = 0.001 m = 1 mm
  L_OB = 0.001 m = 1 mm
  L_AB = 0.002 m = 2 mm (collinear or near-collinear)
  
  y² = 0.001² - 1² = 1e-6 - 1 = negative (caught by triangle inequality)
  If barely passes triangle: y² ≈ 1e-10
  Threshold: 1e-12
  Result: 🔴 FALSE: y² ≈ 1e-10 > 1e-12 → PASSES (but shouldn't!)
          Collinear geometry accepted as valid

TEST VECTOR B (LARGE GEOMETRY):
  L_OA = 1000 m
  L_OB = 1000 m  
  L_AB = 1999.99999... m
  
  y² = 1000² - 999.999...² ≈ 1e-6 m²
  Threshold: 1e-12
  Result: ✓ y² ≈ 1e-6 > 1e-12 → PASSES (correct)
          But tolerance is WAY too loose
          Nearly-collinear geometry accepted

ROOT CAUSE:
  app.py line 484: if _to_float(y2_expr) <= 1e-12:
  This is scale-dependent
  
  Better: threshold_rel = 1e-12 * (L_OA * L_OB)
  
IMPACT: 
  Thin triangles barely fail or pass depending on scale
  User can't predict when geometry is too thin
```

---

## **FAILURE #7: NO INPUT LENGTH LIMIT (DOS RISK)**

```
PROBLEM: text_input() has no max_chars limit
         User can paste gigabytes of text

TEST VECTOR:
  L_OA = "(" * 1000000 + "x" + ")" * 1000000
  
  app.py calls: _normalize_expression_with_symbol_map(text)
  This applies regex substitutions and normalization
  SymPy then tries to parse 2 million nested parentheses
  
  Result: 
    ✗ MemoryError or StackOverflowError
    ✗ App hangs or crashes
    ✗ Denial of service

ROOT CAUSE:
  app.py lines 392-407: st.sidebar.text_input() without max_chars
  
FIX:
  st.sidebar.text_input(..., max_chars=1000)

IMPACT: User or attacker can crash app
```

---

## **FAILURE #8: SCREWS CAN BE AT SAME LOCATION**

```
PROBLEM: L2 = 0 is caught, but L1 = L2 (both screws same location) isn't

TEST VECTOR:
  L1 = 0.1 m, L2 = 0.1 m, P = 100 N
  
  Screw A at x = 0.1 m
  Screw B at x = 0.1 + 0.1 = 0.2 m  (different, valid)
  
  But what if teacher accidentally sets:
  L1 = 0.1 m, L2 = 0.0001 m (very close)
  
  Screw separation = 0.0001 m = 0.1 mm (unrealistically tiny!)
  Reactions become HUGE (1e6 scale)
  
  OR:
  User enters L1 = "L", L2 = "L" (same symbolic variable)
  System becomes singular (det = 0)
  SymPy cannot solve
  Generic error message shown

ROOT CAUSE:
  app.py line 500: only checks L2 > 0, not (L2 - L1) > 0
  No "screw separation" validation

FIX:
  Add: if (L2_expr) < epsilon:
       validation_failures.append("Screws too close; increase L2")

IMPACT: Unrealistic reactions or confusing error
```

---

## **FAILURE #9: NO CABLE GEOMETRY REALISM CHECK**

```
PROBLEM: Pulley location D can be inside the structure
         No validation that cable geometry is realizable

TEST VECTOR:
  L_OA = 3 m, L_OB = 3 m, L_AB = 3
  theta = 0 deg (horizontal cable direction)
  
  Point A computed: x_A ≈ 1.5, y_A ≈ 2.6
  Pulley D: D = A - 1.25*L_OA*(cos(0), sin(0))
           D = (1.5, 2.6) - 3.75*(1, 0)
           D = (-2.25, 2.6)   ← NEGATIVE X!
  
  Pulley is to the LEFT of the pole (at x = 0)
  Visually: Pulley appears inside or behind the structure
  
  No validation: "Is pulley in a realistic location?"
  App silently allows nonsensical cable routing

ROOT CAUSE:
  No check that D_x > 0 or D is outside the structure boundary
  models.py doesn't validate cable geometry

IMPACT: Confusing FBD; professor might say "That's impossible"
```

---

## **FAILURE #10: ANGLE CAN WRAP AROUND (360° Not Normalized)**

```
PROBLEM: Angle theta has no bounds checking
         θ = 720° is same as 0° but appears different

TEST VECTOR:
  theta = 720 deg (two full rotations)
  
  theta_r = π * 720 / 180 = 4π radians
  cos(4π) = 1, sin(4π) = 0
  
  Force: F_x = -T*cos(4π) = -T
          F_y = -T*sin(4π) = 0
  
  Same as theta = 0 deg
  But user might not realize 720 and 0 are equivalent

TEST VECTOR 2:
  theta = -90 deg (negative angle)
  
  theta_r = π * (-90) / 180 = -π/2
  cos(-π/2) = 0, sin(-π/2) = -1
  Force: F_x = 0, F_y = -T*(-1) = T (upward)
  
  Valid mathematically but user might not expect negative angles

ROOT CAUSE:
  app.py line 431: No angle normalization
  Angular inputs accepted as-is
  
FIX:
  Normalize: theta_deg = theta_deg % 360
  Or validate: 0 ≤ theta < 360

IMPACT: User confusion; professor tests with θ > 360
```

---

## **FAILURE #11: NEGATIVE X_A ALLOWED (OBTUSE TRIANGLE)**

```
PROBLEM: If triangle is obtuse at B, law of cosines gives x_A < 0
         Code doesn't validate x_A should be in [0, L_OB]

TEST VECTOR:
  L_OA = 5 m, L_OB = 2 m, L_AB = 6 m
  
  x_A = (25 + 4 - 36) / (2 * 2) = -7/4 = -1.75 m  ← NEGATIVE!
  y_A = sqrt(25 - 3.0625) ≈ 4.68 m (valid, positive)
  
  Triangle is valid (passes all inequality checks)
  But x_A < 0 means point A is to the LEFT of O
  Geometrically: Triangle extends outside assumed coordinate system
  
  FBD renders with A at x = -1.75 m
  Visually confusing if user expects A to be between O and B

ROOT CAUSE:
  models.py line 41: x_A = (L_OA² + L_OB² - L_AB²) / (2*L_OB)
  No validation that 0 ≤ x_A ≤ L_OB
  
  This is actually CORRECT mathematics for obtuse triangles!
  But might need documentation or visual warning

IMPACT: Pedagogical confusion; triangle might render unexpectedly
```

---

## **FAILURE #12: COMPLEX NUMBERS ACCEPTED AS GEOMETRY**

```
PROBLEM: Input "1+2j" parsed as complex number, accepted as valid

TEST VECTOR:
  L_OA = "1+2j" (complex number in complex notation)
  
  _parse_expr("1+2j"):
    eval("1+2j") → (1+2j) [Python complex]
    sp.sympify(1+2j) → 1 + 2*I [SymPy complex]
    _is_numeric_expr() → True (no free symbols)
    _is_real_finite_numeric() → ??? (should check is_real)
  
  Result: Complex length accepted
  Geometry computed: sqrt((1+2j)² - x_A²) → imaginary!

ROOT CAUSE:
  _is_real_finite_numeric() checks v.is_finite but not v.is_real
  Complex numbers have is_finite = True
  
FIX:
  def _is_real_finite_numeric(expr):
    v = sp.N(expr)
    return bool(v.is_real and v.is_finite)  ← should be is_real
  
  OR catch in _parse_expr:
  if sp.I in expr.free_symbols:
    return None, f"Complex numbers not allowed for {label}"

IMPACT: Nonsense geometry; errors downstream
```

---

## **FAILURE #13: FBD AXIS LABELS HARDCODED TO METERS**

```
PROBLEM: FBD always shows "x (m)" even if user selects mm

TEST VECTOR:
  User selects: length_unit = "mm"
  User enters: L_OA = 3000 (meaning 3000 mm = 3 m)
  
  L_factor = 0.001 (converts mm to m internally)
  L_OA_expr = 3000 * 0.001 = 3 m
  
  FBD renders with L_OA = 3 (internally in meters)
  But axis label says "x (m)"
  
  User expects: "FBD shows geometry in mm"
  Actual: "Axis says meters, but user input was mm"
  
  Confusion if user mixed units or forgot conversion

ROOT CAUSE:
  fbd.py line 92: ax.set_xlabel("x (m)")  ← hardcoded
  Should be: ax.set_xlabel(f"x ({length_unit})")
  But length_unit not passed to function
  
FIX:
  Pass unit to draw_flagpole_fbd(..., length_unit="m")
  Use: ax.set_xlabel(f"x ({length_unit})")

IMPACT: 1000x unit confusion if user doesn't notice
```

---

## TEST SUITE FOR VERIFICATION

Run these test vectors after each fix to confirm resolution:

```python
# Test 1: Clamp lift-off detection
assert_collapse("clamp", L1=0.3, L2=0.1, P=100)
assert result.collapse_mode == "Support lift-off"

# Test 2: Determinant scale independence
geometry_small = {"L_OA": 0.0001, "L_OB": 0.0001, "L_AB": 0.00015}
geometry_large = {"L_OA": 1000, "L_OB": 1000, "L_AB": 1500}
det_small = compute_det(geometry_small)
det_large = compute_det(geometry_large)
assert (abs(det_small) < tol) == (abs(det_large) < tol)  # Same validity

# Test 3: Centroid hole containment
assert_reject("centroid", R=10, w=8, h=8)  # Corners outside

# Test 4: Symbolic mode warning
setup("flagpole", L_OA="L", L_OB=3, L_AB=3)
assert "Symbolic mode" in output or stability_checked == False

# Test 5: Arrow scaling
forces = [1, 100, 10000]
scales = [compute_scale(f) for f in forces]
assert all(s > 0.1 for s in scales)  # All visible, not inverted

# Test 6: Input length limit
assert_limit("L_OA", max_chars=1000)

# Test 7: Angle normalization
theta_720 = compute_force(theta=720)
theta_0 = compute_force(theta=0)
assert theta_720 == theta_0

# Test 8: Negative geometry rejection
assert_reject_or_warn("flagpole", L_OA=-3, L_OB=3, L_AB=3)

# Test 9: Complex numbers rejection
assert_reject("flagpole", L_OA="1+2j")

# Test 10: Unit consistency
assert FBD_label("x") contains length_unit or default is "m"
```

---

**END OF CRITICAL BUGS REFERENCE**

*Use this document to verify fixes and ensure robustness.*
