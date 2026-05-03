# 🔴 RED TEAM AUDIT — QUICK REFERENCE SUMMARY

## Report Location
📄 **Full Report:** `RED_TEAM_AUDIT.md`

---

## CRITICAL FINDINGS BY PROBLEM

### **PROBLEM 1: FLAGPOLE & FRAME (2/49)**

| Finding | Severity | Test Case | Fix |
|---------|----------|-----------|-----|
| Collinearity threshold `1e-12` scale-dependent | [CRITICAL] | OA=1000, OB=1000, AB≈2000 → false pass | Replace with scale-normalized threshold |
| Symbolic triangle inequality bypass | [CRITICAL] | L_OA="L1", L_AB="L1+L2+1" → complex geometry | Add validation in symbolic mode |
| Negative x_A allowed (obtuse triangle) | [EDGE-CASE] | OA=5, OB=2, AB=6 → x_A=-1.75 | Document or validate x_A ∈ [0,L_OB] |
| Cable pulley D can be inside pole | [EDGE-CASE] | θ=0°, small L_OA → D_x < 0 | Add geometry feasibility check |
| Angle wraparound not normalized | [EDGE-CASE] | θ=720° ≡ θ=0° | Normalize θ to [0,360°) |
| Negative symbolic tension allowed | [EDGE-CASE] | T="−P" (symbolic) | Validate symbolic tension ≥ 0 (if numeric) |

---

### **PROBLEM 2: WOOD CLAMP (3/8)**

| Finding | Severity | Test Case | Fix |
|---------|----------|-----------|-----|
| Screws modeled as TWO-WAY (should be one-way) | [CRITICAL] | L1=0.3, L2=0.1, P=100 → F_A=−200N (pulling) | Add `one_way={"F_A": "vertical_up", "F_B": "vertical_up"}` |
| No lift-off/slack detection | [CRITICAL] | F_A < 0 → allowed without collapse warning | Enable one-way support checks in stability.py |
| L1 allowed at zero (load AT screw) | [EDGE-CASE] | L1=0, L2=0.1 → F_A=100N all load | Document pedagogical intent or enforce L1 > 0 |
| L2 can be arbitrarily small → huge reactions | [EDGE-CASE] | L1=1, L2=0.001, P=100 → F_B=100,000N | Add "reasonableness" warning for extreme reactions |
| Force arrow scaling inverted | [CRITICAL] | Scale ∝ 1/magnitude (small mag = big arrow) | Replace with logarithmic or absolute scaling |
| Negative reaction forces not highlighted | [UX/VISUAL] | F_A=−200N renders downward arrow without red flag | Add red highlighting + error message for negative reactions |

---

### **PROBLEM 3: CENTROID (5/53)**

| Finding | Severity | Test Case | Fix |
|---------|----------|-----------|-----|
| Hole can extend outside semicircle | [CRITICAL] | R=10, w=9, h=7 (corners outside bounds) | Add ellipse-boundary check for rectangle corners |
| Rectangle corners exceed semicircle at edges | [CRITICAL] | R=10, w=8, h=8 (top corners outside) | Validate `w² + (h/2−y)² ≤ R²` at corners |
| No check for net area singularity | [EDGE-CASE] | R=10, w=8.8, h=8.8 → A_net ≈ 2mm² (tiny) | Add warning for A_net < epsilon |
| Implicit assumption: hole centered at y=0 | [EDGE-CASE] | Problem definition assumes fixed hole position | Document or allow user-specified hole position |

---

## GLOBAL TECHNICAL FAILURES

| Issue | Severity | Impact |
|-------|----------|--------|
| **Determinant tolerance scale-dependent** | [CRITICAL] | Same geometry, different units → different stability; `abs(det) < 1e-9` is absolute, not relative |
| **Symbolic mode silently skips stability** | [CRITICAL] | User unaware that stability checks were not performed; structural integrity not validated |
| **No input length limit (DoS)** | [CRITICAL] | Arbitrary-length expressions cause hang/crash; parser can stack-overflow |
| **Arrow scaling inverted (all FBDs)** | [CRITICAL] | Large forces appear small; misleading FBD visualization |
| **Generic error messages** | [CRITICAL] | No diagnostic info; user can't debug failures |
| **Complex numbers accepted as geometry** | [CRITICAL] | `1+2j` parsed as valid length; produces nonsense geometry |
| **FBD axis labels hardcoded to meters** | [EDGE-CASE] | Mismatch if user selects mm; 1000x unit confusion |
| **Unit inconsistency** | [EDGE-CASE] | Centroid-only mm; other problems m/mm; mixing units silently accepted |
| **Angle unit conversion error** | [EDGE-CASE] | User enters `1.57` expecting π/2 rad but gets 1.57° (100x error) |

---

## IMMEDIATE ACTION ITEMS

### **BLOCKING (Must Fix):**

1. ✅ **Clamp two-way support** → Add one_way constraints (models.py line 93)
2. ✅ **Determinant relative tolerance** → Scale-normalized check (stability.py line 111)
3. ✅ **Symbolic mode notification** → Display warning when stability skipped (app.py line 536)
4. ✅ **Input length limit** → Add `max_chars=1000` (app.py lines 392-407)
5. ✅ **FBD arrow scaling** → Replace `s = 0.35 / mag` with logarithmic scale (fbd.py line 17)
6. ✅ **Centroid hole bounds** → Add ellipse containment validation (app.py line 261)

### **HIGH-PRIORITY (Within Sprint):**

7. Collapse mode differentiation (stability.py)
8. Angle normalization to [0, 360°) (app.py line 431)
9. Complex number validation (app.py _parse_expr)
10. Unit labels consistency (fbd.py)
11. Detailed error diagnostics (solver_backend.py)

### **MEDIUM-PRIORITY (Polish):**

12. Cable geometry realism check (flagpole)
13. Screw force sensitivity warnings (clamp)
14. Symbolic/numeric mode indicator (UI)

---

## HOW TO USE THIS AUDIT

1. **For Developers:** Open `RED_TEAM_AUDIT.md` for full details on each failure point
2. **For Testing:** Use the "Test Case" column to craft professor-proof test scenarios
3. **For Prioritization:** Focus on [CRITICAL] issues first; [EDGE-CASE] can be deferred
4. **For Validation:** After fixes, re-run all test cases to confirm failures are resolved

---

**Total Issues Found:** 30+  
**Critical Issues:** 13  
**Edge Cases:** 12  
**UX/Visual Issues:** 5+  

**Status:** App is **NOT production-ready** until critical issues are resolved.

---
