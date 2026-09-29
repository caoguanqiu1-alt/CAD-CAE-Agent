# Single-solid axial-tension demonstration (2020 SP5)

The existing bridge now has `StaticAnalysisService.cs`, exposed by
`sw_simulation_static_step`. This is a bounded demonstration workflow, not the
complete general Phase 2 API. Supports one fixed face, one uniform +global-X total
force and linear elastic material properties. No coordinate picking or GUI clicks.

Each call requires exact `expected_document` and `study`, runs through the existing
cross-process COM lock, and executes one operation: state, material, fixture, force,
mesh, run, results or plot. Fixture/force setup rejects duplicate boundary counts.
Face arguments must be persistent IDs from the same document's inspection.

Verified case: 6061-T6 (SS) library E=69.000000666 GPa, nu=0.33, yield=275.000000856
MPa, explicitly converted to linear elastic isotropic. Simulation displays this
derived material as `User Defined`; it is not a different default material.
Large hole inner wall fixed; small hole inner wall receives +X total force 1000 N.
High-quality quadratic solid mesh: nominal 3 mm / 0.15 mm tolerance, 34596 nodes,
21908 elements. Maximum URES=0.007041338365525007 mm; fixed-face reaction
Fx=-999.9964599609375 N. Native plot units and extrema were inspected and matched.

Three observed SW2020 behaviors are handled explicitly:

1. SetLibraryMaterial returned 1 although the requested named material was assigned.
   The actual state was inspected before proceeding. Exact material-name readback
   is required; missing material never silently falls back to a default.
2. Changing ResultFolder after meshing returned RunAnalysis=0 but produced no
   readable results. Run now rejects folder changes and requires actual readable
   displacement results after RunAnalysis, rather than trusting its error code alone.
3. CreatePlot(URES, units=0) initially displayed Angstrom. The explicit
   SetComponentUnitAndValueByElem(URES,0,false) corrected this to mm. Plot extrema
   are compared with independent GetMinMaxDisplacement(mm) before export.

The physical case is an assumed demonstration load, not a known service load.
Fixed cylindrical wall and uniform force omit pin clearance/contact/friction.
Only a single mesh was solved; no mesh-convergence certification or strength
approval is implied. Save the .SLDPRT with its matching .CWR result file.
