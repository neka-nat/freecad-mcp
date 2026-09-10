"""DFM: internal radii < RMIN and sharp concave vertical edges. argv: file, object names, min radius."""
import FreeCAD as App, Part, math, sys
V=App.Vector
FILE=sys.argv[1]; NAMES=sys.argv[2].split(","); RMIN=float(sys.argv[3]) if len(sys.argv)>3 else 2.0
d=App.openDocument(FILE)
def analyse(name):
    s=d.getObject(name).Shape
    print("==",name)
    # 1) увігнуті циліндричні грані з віссю Z і R<2 (внутрішні радіуси)
    conc={}
    for f in s.Faces:
        surf=f.Surface
        if surf.__class__.__name__=="Cylinder" and surf.Radius<RMIN-0.01:
            u,v=f.ParameterRange[0],f.ParameterRange[2]
            p=f.valueAt((f.ParameterRange[0]+f.ParameterRange[1])/2,(f.ParameterRange[2]+f.ParameterRange[3])/2)
            n=f.normalAt((f.ParameterRange[0]+f.ParameterRange[1])/2,(f.ParameterRange[2]+f.ParameterRange[3])/2)
            ax=surf.Axis; pc=p-surf.Center; radial=pc-ax*pc.dot(ax)
            concave = n.dot(radial)<0  # outward normal points to the axis => material outside => internal radius
            if concave:
                axis="Z" if abs(ax.z)>0.9 else ("X" if abs(ax.x)>0.9 else "Y")
                key=(round(surf.Radius,2),axis); conc.setdefault(key,[]).append((round(surf.Center.x,1),round(surf.Center.y,1),round(f.BoundBox.ZMin,1),round(f.BoundBox.ZMax,1)))
    for (r,ax),lst in sorted(conc.items()): print(" internal R%.2f axis %s: %d faces, e.g. %s"%(r,ax,len(lst),lst[:3]))
    # 2) гострі увігнуті вертикальні ребра між двома площинами
    sharp=[]
    for e in s.Edges:
        if e.Curve.__class__.__name__!="Line": continue
        t=e.tangentAt(e.FirstParameter)
        if abs(abs(t.z)-1)>1e-6 or e.Length<0.5: continue
        fs=s.ancestorsOfType(e,Part.Face)
        if len(fs)!=2 or any(f.Surface.__class__.__name__!="Plane" for f in fs): continue
        n1,n2=[f.normalAt(*f.Surface.parameter(e.CenterOfMass)) for f in fs]
        if abs(n1.dot(n2))>0.999: continue
        # увігнутість: точка трохи всередину по бісектрисі нормалей ззовні -> для увігнутого ребра сума нормалей вказує від матеріалу і точка (центр - eps*(n1+n2)) НЕ всередині? простіше: перевірити точку центр + eps*(n1+n2): для увігнутого ребра вона всередині тіла
        b=(n1+n2); b.normalize(); p=e.CenterOfMass+b*0.05
        if s.isInside(p,1e-7,False):
            ang=math.degrees(math.acos(max(-1,min(1,n1.dot(n2)))))
            sharp.append((round(e.CenterOfMass.x,1),round(e.CenterOfMass.y,1),round(e.BoundBox.ZMin,1),round(e.BoundBox.ZMax,1),round(180-ang)))
    print(" sharp concave vertical edges:",len(sharp))
    from collections import Counter
    print("  by Z range:",Counter((z0,z1) for _,_,z0,z1,_ in sharp).most_common(12))
    for it in sharp[:60]: print("  ",it)
for n in NAMES: analyse(n)
