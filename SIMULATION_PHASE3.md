# CAE Agent static workflow (SOLIDWORKS 2020 SP5)

`sw_simulation_run_plan` now executes a guarded, saved-copy static workflow through
the existing MCP server and process-wide COM lock. It uses the same short-lived
x64 STA bridge as Phase 1/2; MCP startup and `tools/list` do not attach to COM.
Compile the bridge with `powershell -File simulation/build.ps1` after source
changes, and reconnect existing MCP clients to refresh their tool list.
The plan prevalidates the active clean document, material file, all persistent
face IDs, load vectors, new output paths, and a strictly decreasing mesh sequence
before creating a study. A failed or ambiguous mutation stops the run and returns
the last step; the caller must inspect actual study state before retrying.
One plan call can include several long solver runs; client timeouts are not
evidence that the COM mutation failed or did not finish.

Plan schema:

```json
{
  "expected_document": "C:\\...\\copy.SLDPRT",
  "study": "New_Static_Study",
  "material": {"library": "D:\\...\\solidworks materials.sldmat", "name": "6061-T6 (SS)"},
  "fixture_face": "face_<persistent-reference-base64>",
  "loads": [{"face": "face_<id>", "force_N": [1000, 0, 0]}],
  "contacts": [{"link_face": "face_<id>", "pin_face": "face_<id>"}],
  "axial_roller_faces": ["face_<id>", "face_<id>"],
  "guide_face": "face_<id>",
  "mesh_sizes_mm": [4, 3, 2],
  "displacement_tolerance_percent": 1,
  "archive_directory": "C:\\...\\new_archive_directory",
  "plot_bmp": "C:\\...\\new_plot.bmp"
}
```

`contacts`, `axial_roller_faces`, and `guide_face` are optional. For a
multibody part, contact pairs are required. The runner assigns linear isotropic
material to all bodies, creates a fixed fixture, applies 1–16 simultaneous
total force vectors in global XYZ, and optionally adds two axial roller/slider
fixtures and one global-Z guide on a pin cap. It sets global contact to Free and
the specified cylindrical pairs to No Penetration, so incidental coincident
faces do not bond. The guide and rollers model *assumed external retention and
guidance*; they are not automatically inferred from the CAD part.

The tool meshes and solves 3–6 sizes, checks a readable native result after
each solve, copies each `.CWR` into the archive, creates a URES(mm) plot, and
saves the part. It reports both maximum-displacement and peak-stress relative
changes between adjacent meshes. A `displacement_converged` flag compares **each**
adjacent pair with the requested tolerance; it does not certify local contact
pressure or strength. Peak stress has its own flag and must not be silently
treated as converged with displacement.

`sw_simulation_general_step` exposes individual state/material/force/contact/
roller/guide/mesh/run/result operations. `sw_simulation_make_pin` adds one
separate cylindrical pin body from a saved part's negative-Y planar face; the
bridge converts global centre coordinates to sketch coordinates and verifies
the resulting body, radius and axis. This helper is intentionally bounded to
the demonstrated two-hole, Y-axis pin geometry. Existing Phase 2 single-body
operations remain available.

Live verification on fresh part copies:

* A plan with two non-collinear 3D load vectors on different faces solved at
  5/4/3 mm. Maximum URES was 0.138554/0.138939/0.139222 mm; both adjacent
  changes were below 1%. The generated `.SLDPRT`, `.CWR`, three CWR snapshots,
  and URES plot were saved. Peak stress did not meet the same 1% test.
* The same **one-call MCP plan tool** was then exercised with the three-body
  pin model, both No Penetration pairs, two axial rollers and a lateral guide.
  At 5/4/3 mm maximum URES was 0.0111578/0.0111879/0.0112147 mm;
  adjacent changes were 0.269%/0.239%. The resulting study and its two contact
  sets remained readable after close/reopen. Peak stress again failed the 1%
  change test.
* A three-body link plus Ø40/Ø25 pins had two real No Penetration cylindrical
  contact sets. With only one fixed pin and no external guides, 4/3/2 mm URES
  changed 0.373/52.032/31.793 mm, exposing a free axial mode. Adding only
  axial retention still left a lateral rotational mechanism. With two axial
  rollers and a small-pin global-Z guide, 4/3/2 mm URES became
  0.011188/0.011215/0.011234 mm; adjacent changes were 0.240%/0.172%.
  The 2 mm fixed-pin Fx reaction was -1000.000244 N for a +1000 N load.
  Peak von Mises stress rose 10.918/11.493/12.442 MPa and is **not**
  mesh-converged at 1%.
* The guided study was saved, closed, reopened, and read back with three solid
  bodies, two No Penetration contact pairs, five boundary objects, the same
  0.011234 mm maximum URES, and the same reaction. The desktop source part
  SHA-256 remained unchanged.

This is a demonstrated static CAE automation workflow, not engineering signoff.
The 1000 N load, zero pin clearance, frictionless contact, linear elastic
material, and external guide/retainer fixtures are assumptions. Housing
stiffness, clearance/friction, pin bending/fatigue and local contact-pressure
convergence remain outside this demonstration. The final displacement mesh
check does not make the rising peak stress safe for design approval.
