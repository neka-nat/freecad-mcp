"""Regression suite for the FreeCAD MCP addon, run against a LIVE RPC server.

Originally written to *document* the bugs in docs/mcp-gap-analysis.md. Now that
C0, C1 and C2 are fixed it asserts the corrected behaviour instead, so a
regression fails loudly. Gaps that are still open (A1) are asserted as still
open, and will flag here when they get fixed.

Prereqs:
- FreeCAD running with the FreeCADMCP addon loaded.
- "Start RPC Server" clicked (or auto-start enabled).

Run:
    python3 docs/verify_gaps.py        # exit 0 = all good, 1 = a regression

Creates scratch documents named MCPProbe* and closes them at the end. It does
not touch any other open document.
"""
from __future__ import annotations

import sys
import xmlrpc.client

HOST, PORT = "localhost", 9875
DOC, DOC_TD = "MCPProbe", "MCPProbeTD"

results: list[tuple[str, str, bool]] = []


def check(tag: str, label: str, fn, predicate, expected: str):
    """Run fn, apply predicate to the result, record pass/fail."""
    try:
        value = fn()
        ok = predicate(value)
        detail = str(value)[:110]
    except xmlrpc.client.Fault as e:
        value, ok, detail = None, predicate(e), f"Fault: {str(e)[:90]}"
    except Exception as e:
        value, ok, detail = None, False, f"{type(e).__name__}: {str(e)[:90]}"
    results.append((tag, label, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {tag:<4} {label}")
    print(f"         expected: {expected}")
    print(f"         got     : {detail}")
    return value


def succeeded(r):
    return isinstance(r, dict) and r.get("success") is True


def refused(r):
    return isinstance(r, dict) and r.get("success") is False and bool(r.get("error"))


def main() -> int:
    s = xmlrpc.client.ServerProxy(f"http://{HOST}:{PORT}", allow_none=True)
    try:
        s.ping()
    except Exception as e:
        print(f"Cannot reach RPC server at {HOST}:{PORT} -- {e}")
        print("Start FreeCAD, load the MCP Addon workbench, click 'Start RPC Server'.")
        return 2
    print(f"Connected to {HOST}:{PORT}\n")

    s.create_document(DOC)

    print("BASELINE")
    check("", "create a healthy Part::Box",
          lambda: s.create_object(DOC, {"Name": "Box", "Type": "Part::Box",
                                        "Properties": {"Length": 20, "Width": 10, "Height": 5}}),
          succeeded, "success True")
    check("", "screenshot of the 3D view",
          lambda: s.get_active_screenshot("Isometric", None, None, None),
          lambda v: isinstance(v, str) and len(v) > 1000, "a base64 PNG")

    print("\nC1 -- a feature that fails to compute must NOT report success")
    check("C1", "Part::Cut with no Base/Tool is refused",
          lambda: s.create_object(DOC, {"Name": "BadCut", "Type": "Part::Cut", "Properties": {}}),
          refused, "success False with a reason from FreeCAD")

    print("\nC0 -- a broken object must not blind the whole document")
    check("C0", "get_objects still works with a broken object present",
          lambda: len(s.get_objects(DOC)),
          lambda v: isinstance(v, int) and v > 0, "an object count, NOT an XML-RPC Fault")
    check("C0", "get_object on the broken object itself",
          lambda: s.get_object(DOC, "BadCut"),
          lambda v: isinstance(v, dict) and v.get("Shape", {}).get("Valid") is False,
          'Shape reported as {"Valid": false, ...}')
    check("C0", "healthy object unaffected",
          lambda: s.get_object(DOC, "Box"),
          # OCCT returns 999.9999999999998 for a 20x10x5 box -- compare with a
          # tolerance, never for equality, on anything that came out of a kernel.
          lambda v: isinstance(v, dict)
                    and abs((v.get("Shape") or {}).get("Volume", 0) - 1000.0) < 1e-6,
          "Volume ~1000.0")

    print("\nC2 -- PartDesign features must go inside a Body")
    check("C2", "create the Body",
          lambda: s.create_object(DOC, {"Name": "Body", "Type": "PartDesign::Body", "Properties": {}}),
          succeeded, "success True")
    check("C2", "feature WITHOUT body_name is refused",
          lambda: s.create_object(DOC, {"Name": "Loose", "Type": "PartDesign::AdditiveBox",
                                        "Properties": {}}),
          refused, "success False telling the caller to pass body_name")
    check("C2", "feature WITH body_name succeeds",
          lambda: s.create_object(DOC, {"Name": "Base", "Type": "PartDesign::AdditiveBox",
                                        "Body": "Body",
                                        "Properties": {"Length": 20, "Width": 10, "Height": 5}}),
          succeeded, "success True")
    check("C2", "subtractive feature advances Tip and cuts the solid",
          lambda: s.create_object(DOC, {"Name": "Hole", "Type": "PartDesign::SubtractiveCylinder",
                                        "Body": "Body",
                                        "Properties": {"Radius": 3, "Height": 20}}) and
                  s.execute_code(f"import FreeCAD\nb=FreeCAD.getDocument('{DOC}').getObject('Body')\n"
                                 "print(b.Tip.Name, round(b.Shape.Volume,2))\n")["message"],
          lambda v: "Hole" in str(v) and "964.66" in str(v),
          "Tip=Hole, Volume=964.66 (1000 minus a quarter cylinder)")
    check("C2", "bad body name gives a clear error",
          lambda: s.create_object(DOC, {"Name": "X", "Type": "PartDesign::AdditiveBox",
                                        "Body": "NoSuchBody", "Properties": {}}),
          refused, "success False naming the missing Body")

    print("\nToggles -- the setting must flip on every click, never pin to one value")
    # The checkbox half is only asserted when the QAction exists. Toggle_Auto_Start
    # is created by Workbench.Initialize(), so it is absent until the user opens the
    # MCP workbench -- which is exactly why these settings also live in the gear
    # dialog, reachable from anywhere.
    check("UX", "four clicks alternate the stored setting",
          lambda: s.execute_code(
              "import rpc_server.commands as C\n"
              "from rpc_server.settings import load_settings, save_settings\n"
              "orig = load_settings()\n"
              "save_settings({**orig, 'auto_start_rpc': False})\n"
              "C._sync_toggle_states()\n"
              "def st():\n"
              "    a = C._find_action('Toggle_Auto_Start')\n"
              "    return (load_settings()['auto_start_rpc'], None if a is None else a.isChecked())\n"
              "seq = [st()]\n"
              "for _ in range(4):\n"
              "    C.ToggleAutoStartCommand().Activated(0)\n"
              "    seq.append(st())\n"
              "save_settings(orig)\n"
              "C._sync_toggle_states()\n"
              "settings_seq = [s for s, _ in seq]\n"
              "boxes = [b for _, b in seq if b is not None]\n"
              "print('settings:', settings_seq)\n"
              "print('checkboxes:', boxes if boxes else 'action absent (workbench not open)')\n"
              "print('OK:', settings_seq == [False, True, False, True, False]\n"
              "      and (not boxes or boxes == settings_seq))\n")["message"],
          lambda v: "OK: True" in str(v),
          "settings [F,T,F,T,F]; checkbox matches when the action exists")

    print("\nA1 -- TechDraw pages must be capturable")
    s.create_document(DOC_TD)
    s.execute_code(
        f"import FreeCAD, FreeCADGui\nd=FreeCAD.getDocument('{DOC_TD}')\n"
        "b=d.addObject('Part::Box','Blk')\n"
        "p=d.addObject('TechDraw::DrawPage','Page')\n"
        "t=d.addObject('TechDraw::DrawSVGTemplate','Tmpl')\np.Template=t\n"
        "v=d.addObject('TechDraw::DrawViewPart','View')\n"
        "p.addView(v); v.Source=[b]; v.Direction=FreeCAD.Vector(0,0,1)\nd.recompute()\n"
        "p.ViewObject.doubleClicked()\n")
    # A blank capture is the failure mode that matters here: the first attempt at
    # this fix grabbed the outer QMainWindow and produced an all-white PNG that
    # looked like success. A rendered page carries real ink, so assert on size.
    check("A1", "screenshot with a TechDraw page active",
          lambda: s.get_active_screenshot("Isometric", None, None, None),
          lambda v: isinstance(v, str) and len(v) > 1200,
          "a base64 PNG with actual content, not None and not a blank frame")

    print("\nCleanup")
    for doc in (DOC, DOC_TD):
        s.execute_code(f"import FreeCAD\nFreeCAD.closeDocument('{doc}')\n")
        print(f"  closed {doc}")

    failed = [r for r in results if not r[2]]
    print("\n" + "=" * 68)
    for tag, label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {tag:<4} {label}")
    print("=" * 68)
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
