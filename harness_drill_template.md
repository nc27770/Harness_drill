# Harness Engineering Drill Template

Use this template to document a wire harness design exercise or project drill.

---

## Project Information

| Field | Value |
|-------|-------|
| Project Name | |
| Harness ID / Drawing Number | |
| Revision | |
| Engineer | |
| Date | |
| Application (Automotive / Aerospace / Industrial / Other) | |

---

## 1. Electrical Requirements

| Wire Ref | From (Component / Pin) | To (Component / Pin) | Signal Type | Voltage (V) | Current (A) | Wire Color | AWG / mm² | Shielded? |
|----------|------------------------|----------------------|-------------|-------------|-------------|------------|-----------|-----------|
| W001 | | | | | | | | |
| W002 | | | | | | | | |
| W003 | | | | | | | | |

---

## 2. Connector Schedule

| Connector Ref | Part Number | Gender | # Pins | Mating Connector | Location | Sealing (Y/N) | IP Rating |
|---------------|------------|--------|--------|-----------------|----------|---------------|-----------|
| J1 | | | | | | | |
| J2 | | | | | | | |

---

## 3. Wire Gauge Sizing Calculation

For each circuit, verify wire gauge using:

**Formula:** I_rated ≥ I_load × derating_factor

| Wire Ref | Load Current (A) | Derating Factor | Minimum Rated Current (A) | Selected AWG | Rated Current (A) | Pass/Fail |
|----------|-----------------|----------------|--------------------------|--------------|-------------------|-----------|
| W001 | | | | | | |
| W002 | | | | | | |

**Derating factors to consider:**
- Bundling derating (NEC / SAE J1292 tables)
- Temperature derating for ambient > 25 °C
- Conduit fill factor

---

## 4. Voltage Drop Calculation

**Formula:** V_drop = I × R = I × (ρ × L / A)

Where:
- I = current (A)
- ρ = resistivity of copper ≈ 1.72 × 10⁻⁸ Ω·m
- L = one-way wire length (m)
- A = cross-sectional area (m²)

| Wire Ref | Current (A) | Length (m) | AWG / mm² | Resistance (Ω) | Voltage Drop (V) | Max Allowed (V) | Pass/Fail |
|----------|------------|-----------|-----------|----------------|-----------------|----------------|-----------|
| W001 | | | | | | | |
| W002 | | | | | | | |

---

## 5. Bundle & Conduit Sizing

**Formula:** Bundle Diameter ≈ 1.1 × √(N) × d_wire (approximate for random fill)

| Bundle ID | Wire Count (N) | Largest Wire Dia. (mm) | Calculated Bundle Dia. (mm) | Conduit/Sleeve ID (mm) | Fill % | Pass/Fail |
|-----------|---------------|------------------------|----------------------------|------------------------|--------|-----------|
| B1 | | | | | | |
| B2 | | | | | | |

Recommended maximum conduit fill: **≤ 40%** cross-sectional area for serviceability.

---

## 6. Routing Notes

| Bundle ID | Routing Path Description | Bend Radius Required (mm) | Min. Bend Radius (mm) | Clearance from Heat Source (mm) | Pass/Fail |
|-----------|--------------------------|--------------------------|----------------------|--------------------------------|-----------|
| B1 | | | | | |
| B2 | | | | | |

---

## 7. Bill of Materials (BOM)

| Item | Part Number | Description | Qty | Unit | Supplier |
|------|------------|-------------|-----|------|---------|
| 1 | | Wire (AWG XX, color) | | m | |
| 2 | | Connector J1 | | ea | |
| 3 | | Terminal (for J1) | | ea | |
| 4 | | Corrugated conduit | | m | |
| 5 | | Heat-shrink tubing | | m | |
| 6 | | Cable ties | | ea | |

---

## 8. Test Specification

### 8.1 Continuity Test

| Test No. | From | To | Expected Resistance (Ω) | Pass Criteria | Result |
|----------|------|----|------------------------|---------------|--------|
| T001 | J1-1 | J2-1 | < 0.5 | Continuity | |
| T002 | J1-2 | J2-2 | < 0.5 | Continuity | |

### 8.2 Insulation Resistance (Hi-Pot)

| Test No. | Circuits Under Test | Test Voltage (VDC) | Duration (s) | Min. Insulation Resistance (MΩ) | Result |
|----------|---------------------|--------------------|--------------|---------------------------------|--------|
| H001 | All circuits vs. shield/ground | 500 | 60 | ≥ 100 | |

### 8.3 Visual Inspection

Inspect per **IPC/WHMA-A-620** Class ____ (1 / 2 / 3):

- [ ] No insulation damage or exposed conductors
- [ ] All terminals fully seated and locked
- [ ] Crimps meet pull-force requirement
- [ ] Sleeving and taping complete and neat
- [ ] Labeling correct and legible

---

## 9. Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Design Engineer | | | |
| Checker | | | |
| Manufacturing Engineer | | | |
| Quality | | | |
