"""
Tests simples pour les fonctionnalites avancees Corsair (Phase 3-5)
Date creation: 2025-10-08
Version sans emojis pour compatibilite Windows
"""

import sys
import time
import xmlrpc.client

def log(msg):
    print(msg)

def test_connection():
    log("\n[TEST] Connexion FreeCAD")
    try:
        server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        result = server.ping()
        if result:
            log("[OK] FreeCAD connecte")
            return True
        else:
            log("[FAIL] FreeCAD ne repond pas")
            return False
    except Exception as e:
        log(f"[FAIL] Erreur connexion: {e}")
        return False

def test_create_document():
    log("\n[TEST] Creation document")
    try:
        server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        doc_name = f"Test_{int(time.time())}"
        result = server.create_document(doc_name)
        if result.get("success"):
            log(f"[OK] Document '{doc_name}' cree")
            return doc_name
        else:
            log(f"[FAIL] {result.get('error')}")
            return None
    except Exception as e:
        log(f"[FAIL] Exception: {e}")
        return None

def test_fillet(doc_name):
    log("\n[TEST] Add Fillet (conges)")
    try:
        server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        
        # Creer un cube
        code = f"""
import FreeCAD as App
doc = App.getDocument('{doc_name}')
box = doc.addObject('Part::Box', 'TestBox')
box.Length = 100
box.Width = 100
box.Height = 100

# Ajouter fillet
fillet = doc.addObject('Part::Fillet', 'BoxFillet')
fillet.Base = box
fillet.Edges = [(1, 10.0, 10.0), (2, 10.0, 10.0)]
doc.recompute()

box.Visibility = False
print('SUCCESS')
"""
        result = server.execute_code(code)
        if result.get("success") and "SUCCESS" in result.get("message", ""):
            log("[OK] Fillet ajoute")
            return True
        else:
            log(f"[FAIL] {result.get('error', result.get('message'))}")
            return False
    except Exception as e:
        log(f"[FAIL] Exception: {e}")
        return False

def test_mirror(doc_name):
    log("\n[TEST] Mirror (symetrie)")
    try:
        server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        
        code = f"""
import FreeCAD as App
doc = App.getDocument('{doc_name}')
cyl = doc.addObject('Part::Cylinder', 'TestCyl')
cyl.Radius = 25
cyl.Height = 50
cyl.Placement.Base = App.Vector(100, 0, 0)

# Mirror plan YZ
mirror = doc.addObject('Part::Mirroring', 'CylMirror')
mirror.Source = cyl
mirror.Base = App.Vector(0, 0, 0)
mirror.Normal = App.Vector(1, 0, 0)
doc.recompute()

print('SUCCESS')
"""
        result = server.execute_code(code)
        if result.get("success") and "SUCCESS" in result.get("message", ""):
            log("[OK] Mirror cree")
            return True
        else:
            log(f"[FAIL] {result.get('error', result.get('message'))}")
            return False
    except Exception as e:
        log(f"[FAIL] Exception: {e}")
        return False

def test_circular_pattern(doc_name):
    log("\n[TEST] Circular Pattern")
    try:
        server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        
        code = f"""
import FreeCAD as App
doc = App.getDocument('{doc_name}')
cyl = doc.addObject('Part::Cylinder', 'PatCyl')
cyl.Radius = 10
cyl.Height = 20
cyl.Placement.Base = App.Vector(50, 0, 0)

# Pattern 6 instances
objects = [cyl]
for i in range(1, 6):
    angle = i * 60
    rot = App.Rotation(App.Vector(0, 0, 1), angle)
    copy = doc.addObject('Part::Feature', 'Copy' + str(i))
    copy.Shape = cyl.Shape.copy()
    vec = App.Vector(50, 0, 0)
    new_vec = rot.multVec(vec)
    copy.Placement = App.Placement(new_vec, rot)
    objects.append(copy)

doc.recompute()
print('SUCCESS')
"""
        result = server.execute_code(code)
        if result.get("success") and "SUCCESS" in result.get("message", ""):
            log("[OK] Pattern circulaire cree")
            return True
        else:
            log(f"[FAIL] {result.get('error', result.get('message'))}")
            return False
    except Exception as e:
        log(f"[FAIL] Exception: {e}")
        return False

def test_naca_profile(doc_name):
    log("\n[TEST] Import NACA Profile")
    try:
        server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        
        code = f"""
import FreeCAD as App
import Part
import math

doc = App.getDocument('{doc_name}')

# Creer profil NACA simple
points_upper = []
points_lower = []
for i in range(21):
    x = i * 50
    y_upper = 20 * math.sin(i * math.pi / 20)
    y_lower = -10 * math.sin(i * math.pi / 20)
    points_upper.append(App.Vector(x, y_upper, 0))
    points_lower.append(App.Vector(x, y_lower, 0))

sketch = doc.addObject('Sketcher::SketchObject', 'NACA_Test')
for i in range(len(points_upper)-1):
    sketch.addGeometry(Part.LineSegment(points_upper[i], points_upper[i+1]))

doc.recompute()
print('SUCCESS')
"""
        result = server.execute_code(code)
        if result.get("success") and "SUCCESS" in result.get("message", ""):
            log("[OK] Profil NACA cree")
            return True
        else:
            log(f"[FAIL] {result.get('error', result.get('message'))}")
            return False
    except Exception as e:
        log(f"[FAIL] Exception: {e}")
        return False

def main():
    log("=" * 60)
    log("TESTS FONCTIONNALITES AVANCEES CORSAIR")
    log("=" * 60)
    
    passed = 0
    failed = 0
    
    # Test connexion
    if not test_connection():
        log("\n[ERREUR] FreeCAD non connecte - Arret des tests")
        return
    
    # Creer document
    doc_name = test_create_document()
    if not doc_name:
        log("\n[ERREUR] Impossible de creer document - Arret des tests")
        return
    
    # Tests fonctionnalites
    tests = [
        ("Fillet", lambda: test_fillet(doc_name)),
        ("Mirror", lambda: test_mirror(doc_name)),
        ("Circular Pattern", lambda: test_circular_pattern(doc_name)),
        ("NACA Profile", lambda: test_naca_profile(doc_name))
    ]
    
    for test_name, test_func in tests:
        if test_func():
            passed += 1
        else:
            failed += 1
        time.sleep(1)
    
    # Résumé
    log("\n" + "=" * 60)
    log("RESUME")
    log("=" * 60)
    log(f"Tests reussis: {passed}")
    log(f"Tests echoues: {failed}")
    total = passed + failed
    if total > 0:
        rate = (passed / total) * 100
        log(f"Taux de reussite: {rate:.1f}%")
        
        if rate == 100:
            log("\n[EXCELLENT] Toutes les fonctionnalites marchent!")
        elif rate >= 75:
            log("\n[BON] La plupart des fonctionnalites marchent")
        elif rate >= 50:
            log("\n[MOYEN] Certaines corrections necessaires")
        else:
            log("\n[ATTENTION] Beaucoup de corrections necessaires")
    
    log("=" * 60)

if __name__ == "__main__":
    log("Demarrage tests...")
    log("Attente 2 secondes...")
    time.sleep(2)
    main()



