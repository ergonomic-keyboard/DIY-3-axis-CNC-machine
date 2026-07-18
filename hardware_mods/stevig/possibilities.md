**Yes to both, with some practical details.**

### 1. Including Bolts (and Fasteners) in FEM Analysis
FreeCAD’s FEM workbench supports bolted connections, but it’s not fully automated like in high-end commercial FEA software. You can do it reliably with these approaches:

- **Use the Fasteners Workbench** (add-on) to easily insert realistic bolts, nuts, washers, etc., into your assembly.

- **For simulation**:
  - Model the bolts as solid geometry (or simplify them).
  - Use **Contact Constraints** (`FEM_ConstraintContact`) between bolt/nut/threaded holes and the connected plates. This allows separation, sliding, and friction.
  - **Tie Constraints** for permanently bonded (welded-like) behavior.
  - **Pretension** (bolt preload) is possible but more advanced — often simulated by making the bolt slightly shorter and letting it stretch during the analysis, or through manual `.inp` file edits for CalculiX *PRE-TENSION SECTION*.

**Tips for good results**:
- Use a **non-conformal mesh** (parts in a Compound, not fused).
- Refine the mesh around contact areas.
- Contact analysis is nonlinear and more computationally intensive — start with simpler linear static runs.

Many users successfully simulate bolted joints, flanges, and assemblies this way.

### 2. Applying Force at a Specific 3D Coordinate and Viewing Deflection
**Yes** — this is straightforward.

- Use the **Force Load** constraint (`FEM_ConstraintForce`).
- You can apply it to:
  - Faces
  - Edges
  - **Vertices** (points) — perfect for a true point load at exact coordinates.

**How to do it**:
1. Create your geometry.
2. In FEM workbench → New Analysis.
3. Add material and mesh.
4. Add **Force Load** → Select a vertex (or create a construction point/vertex at the exact coordinate if needed).
5. Specify the force magnitude (in Newtons) and direction (you can pick an edge/face for reference or use vector components).
6. Run the solver (CalculiX is best for this).
7. View results: displacement field (deflection), with color scale, warping, etc.

You can also use **Rigid Body Constraint** or **Displacement Boundary Condition** tied to a reference point for more control in complex cases.

This works great for beams, plates, or full assemblies — you’ll see deflection exactly as expected.

---

Both features are well-supported for static structural analysis. Contact + bolts adds complexity (longer solve times, potential convergence issues), but it’s doable. Point loads are simple and direct.

If you describe your specific model (e.g., a beam with bolted supports and a point load somewhere), I can give more targeted steps or point to example files!