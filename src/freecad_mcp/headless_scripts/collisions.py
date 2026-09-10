"""Pairwise intersection report. argv: file, comma-separated object names[, min_volume]."""
import sys
import FreeCAD as App

FILE = sys.argv[1]
NAMES = sys.argv[2].split(",")
MIN_VOL = float(sys.argv[3]) if len(sys.argv) > 3 else 1e-3
d = App.openDocument(FILE)
shapes = {}
for n in NAMES:
    o = d.getObject(n)
    if o is None or not hasattr(o, "Shape"):
        print(f"object not found: {n}")
        continue
    shapes[n] = o.Shape
names = list(shapes)
clean = True
for i, a in enumerate(names):
    for b in names[i + 1:]:
        c = shapes[a].common(shapes[b])
        if c.isNull() or c.Volume < MIN_VOL:
            print(f"{a} x {b}: 0")
            continue
        clean = False
        print(f"{a} x {b}: {c.Volume:.3f} mm3 in {len(c.Solids)} region(s)")
        for s in sorted(c.Solids, key=lambda s: -s.Volume)[:10]:
            bb = s.BoundBox
            print(f"   X {bb.XMin:.2f}..{bb.XMax:.2f} Y {bb.YMin:.2f}..{bb.YMax:.2f} Z {bb.ZMin:.2f}..{bb.ZMax:.2f} vol {s.Volume:.3f}")
print("RESULT: no collisions" if clean else "RESULT: collisions found")
