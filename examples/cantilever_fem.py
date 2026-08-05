"""End-to-end smoke test for `run_fem_analysis`.

Drives the FreeCAD MCP RPC server directly over XMLRPC (no Claude / no MCP layer
required). Builds a steel cantilever, fixes one face, applies a tip load,
runs CalculiX, and compares against beam-theory analytics.

Prereqs:
- FreeCAD is running with the FreeCADMCP addon loaded.
- "Start RPC Server" was clicked, or auto-start is enabled.

Run:
    python3 examples/cantilever_fem.py

Expected output: σ_max within ~50% of analytic and δ_tip within ~50% of
analytic — coarser-than-textbook because the default mesh is linear tets at
~5 mm size, which lock under bending. Refine the mesh or switch to second-
order elements for closer convergence; that is out of scope for the smoke
test, which only validates the pipeline end-to-end.
"""
from __future__ import annotations

import sys
import time
import xmlrpc.client


HOST = "localhost"
PORT = 9875

DOC = "MCPCantilever"
BEAM = "Beam"
ANALYSIS = "Analysis"
MATERIAL = "Steel"
MESH = "Mesh"
FIXED = "Fixed"
LOAD = "Load"

# Geometry: 100 x 10 x 10 mm bar along +X.
L = 100.0
B = 10.0
H = 10.0
# Material: structural steel.
E_GPA = 210.0
NU = 0.3
RHO = "7900 kg/m^3"
# Tip load: 100 N pulling -Z on the +X face.
F_N = 100.0


def analytic():
    """Closed-form cantilever beam predictions for sanity checking."""
    I = B * H**3 / 12.0  # mm^4, second moment of area
    sigma_max_MPa = (F_N * L) * (H / 2) / I  # N/mm^2 = MPa
    delta_tip_mm = (F_N * L**3) / (3 * (E_GPA * 1000.0) * I)  # mm
    return sigma_max_MPa, delta_tip_mm


def call(server, name, *args):
    print(f"-> {name}{args}")
    res = getattr(server, name)(*args)
    print(f"   {res}")
    return res


def main():
    server = xmlrpc.client.ServerProxy(f"http://{HOST}:{PORT}", allow_none=True)
    if not server.ping():
        print("RPC server is not responding. Start it from the FreeCAD MCP toolbar.")
        sys.exit(2)

    # Clean slate: drop the document if a previous run left it.
    try:
        if DOC in server.list_documents():
            server.execute_code(f"import FreeCAD; FreeCAD.closeDocument('{DOC}')")
    except Exception as e:
        print(f"(cleanup skipped: {e})")

    call(server, "create_document", DOC)

    call(server, "create_object", DOC, {
        "Name": BEAM,
        "Type": "Part::Box",
        "Properties": {"Length": L, "Width": B, "Height": H},
    })

    call(server, "create_object", DOC, {
        "Name": ANALYSIS,
        "Type": "Fem::AnalysisPython",
    })

    call(server, "create_object", DOC, {
        "Name": MATERIAL,
        "Type": "Fem::MaterialCommon",
        "Analysis": ANALYSIS,
        "Properties": {
            "Material": {
                "Name": "Steel",
                "Density": RHO,
                "YoungsModulus": f"{E_GPA} GPa",
                "PoissonRatio": str(NU),
            },
        },
    })

    call(server, "create_object", DOC, {
        "Name": MESH,
        "Type": "Fem::FemMeshGmsh",
        "Analysis": ANALYSIS,
        "Properties": {
            "Shape": BEAM,
            "CharacteristicLengthMax": 5.0,
            "CharacteristicLengthMin": 1.0,
        },
    })

    # Resolve the fixed and loaded faces by their X centroid rather than
    # relying on Part::Box's face enumeration, which is not part of the
    # public API.
    fixed_face_code = f"""
import FreeCAD
doc = FreeCAD.getDocument({DOC!r})
beam = doc.getObject({BEAM!r})
fixed = next(
    (i for i, f in enumerate(beam.Shape.Faces, start=1)
     if abs(f.CenterOfMass.x - 0.0) < 1e-6),
    None,
)
loaded = next(
    (i for i, f in enumerate(beam.Shape.Faces, start=1)
     if abs(f.CenterOfMass.x - {L}) < 1e-6),
    None,
)
print(f"FIXED_FACE=Face{{fixed}} LOADED_FACE=Face{{loaded}}")
"""
    res = call(server, "execute_code", fixed_face_code)
    msg = res.get("message", "") if isinstance(res, dict) else ""
    fixed_face = None
    loaded_face = None
    for token in msg.split():
        if token.startswith("FIXED_FACE="):
            fixed_face = token.split("=", 1)[1]
        elif token.startswith("LOADED_FACE="):
            loaded_face = token.split("=", 1)[1]
    if not fixed_face or not loaded_face or fixed_face == loaded_face:
        print(f"FATAL: face resolution failed (fixed={fixed_face!r}, loaded={loaded_face!r}). "
              f"execute_code output:\n{msg}")
        sys.exit(3)
    print(f"resolved: fixed={fixed_face}  loaded={loaded_face}")

    call(server, "create_object", DOC, {
        "Name": FIXED,
        "Type": "Fem::ConstraintFixed",
        "Analysis": ANALYSIS,
        "Properties": {"References": [(BEAM, fixed_face)]},
    })

    call(server, "create_object", DOC, {
        "Name": LOAD,
        "Type": "Fem::ConstraintForce",
        "Analysis": ANALYSIS,
        "Properties": {"References": [(BEAM, loaded_face)]},
    })

    # Force-magnitude and Direction for Fem::ConstraintForce can't be set via
    # the generic property setter: Force is a PropertyForce (needs a quantity
    # string with units), and Direction is a PropertyLinkSub bound to an Edge.
    # Set both via execute_code, picking a Z-tangent edge for shear loading.
    bind_load_code = f"""
import FreeCAD
doc = FreeCAD.getDocument({DOC!r})
beam = doc.getObject({BEAM!r})
load = doc.getObject({LOAD!r})
z_edge_idx = next(
    (i for i, e in enumerate(beam.Shape.Edges, start=1)
     if abs(e.tangentAt(0).z) > 0.99),
    None,
)
load.Direction = (beam, [f"Edge{{z_edge_idx}}"])
load.Reversed = True
load.Force = "{F_N} N"
doc.recompute()
print(f"Force={{load.Force}}  DirectionVector={{load.DirectionVector}}")
"""
    call(server, "execute_code", bind_load_code)

    print("\nRunning FEM analysis (CalculiX) ...")
    t0 = time.time()
    res = server.run_fem_analysis(DOC, ANALYSIS, 600)
    print(f"   completed in {time.time() - t0:.1f}s")
    print(f"   {res}")

    if not res.get("success"):
        print("\nFAILED.")
        sys.exit(1)

    sigma_pred, delta_pred = analytic()
    sigma_fem = res.get("max_von_mises_MPa")
    delta_fem = res.get("max_displacement_mm")

    print("\n=== Comparison vs. Euler-Bernoulli beam theory ===")
    print(f"  σ_max  predicted (Mc/I)   : {sigma_pred:8.3f} MPa")
    print(f"  σ_max  FEM (von Mises)    : {sigma_fem:8.3f} MPa  ratio {sigma_fem / sigma_pred:.2f}x")
    print(f"  δ_tip  predicted (FL³/3EI): {delta_pred:8.4f} mm")
    print(f"  δ_tip  FEM                : {delta_fem:8.4f} mm  ratio {delta_fem / delta_pred:.2f}x")


if __name__ == "__main__":
    main()
