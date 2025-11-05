"""
Tests pour les fonctionnalités avancées Corsair (Phase 3-5)
Date création: 2025-10-08
"""

import sys
import time
import json
from pathlib import Path

class TestAdvancedFeatures:
    """Tests des 10 fonctionnalités avancées Corsair"""
    
    def __init__(self, output_file="test_results_advanced.txt"):
        self.output_file = output_file
        self.results = []
        self.test_count = 0
        self.passed_count = 0
        self.failed_count = 0
        self.doc_name = None
        
    def log(self, message):
        """Enregistre un message dans les résultats"""
        print(message)
        self.results.append(message)
    
    def setup_document(self):
        """Crée un document de test"""
        self.log("\n=== SETUP: Création du document ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            self.doc_name = f"AdvancedTest_{int(time.time())}"
            result = server.create_document(self.doc_name)
            
            if result.get("success"):
                self.log(f"[OK] Document '{self.doc_name}' cree")
                return True
            else:
                self.log(f"[FAIL] Echec creation document: {result.get('error')}")
                return False
                
        except Exception as e:
            self.log(f"[FAIL] Exception setup: {str(e)}")
            return False
    
    def test_add_fillet(self):
        """Test 1: Add fillet (arrondir arêtes)"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: ADD_FILLET ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            # Créer un cube
            code_setup = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
box = doc.addObject('Part::Box', 'TestBox')
box.Length = 100
box.Width = 100
box.Height = 100
doc.recompute()
print('SUCCESS: Box created')
"""
            result = server.execute_code(code_setup)
            if not result.get("success") or "SUCCESS" not in result.get("message", ""):
                self.log(f"❌ FAIL: Impossible de créer le cube de test")
                self.failed_count += 1
                return False
            
            # Appliquer fillet
            code_fillet = f"""
import sys
sys.path.insert(0, r'c:\\Users\\marti\\AppData\\Roaming\\Python\\Python313\\site-packages')

import FreeCAD as App
doc = App.getDocument('{self.doc_name}')
obj = doc.getObject('TestBox')

if not obj:
    print('ERROR: Object TestBox not found')
else:
    try:
        fillet = doc.addObject('Part::Fillet', 'TestBox_filleted')
        fillet.Base = obj
        
        # Arrondir 4 arêtes avec rayon 10
        edges_to_fillet = [(1, 10.0, 10.0), (2, 10.0, 10.0), (3, 10.0, 10.0), (4, 10.0, 10.0)]
        fillet.Edges = edges_to_fillet
        doc.recompute()
        
        obj.Visibility = False
        
        if fillet.Shape.isValid():
            print(f'SUCCESS: Fillet added to 4 edges with radius 10')
        else:
            print('ERROR: Fillet operation produced invalid shape')
    except Exception as e:
        print(f'ERROR: Fillet failed - {{str(e)}}')
"""
            
            result = server.execute_code(code_fillet)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Fillet ajouté - {result.get('message')}")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error', result.get('message'))}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_mirror_object(self):
        """Test 2: Mirror object (symétrie)"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: MIRROR_OBJECT ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            # Créer un cylindre décentré
            code_setup = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
cylinder = doc.addObject('Part::Cylinder', 'TestCylinder')
cylinder.Radius = 25
cylinder.Height = 50
cylinder.Placement.Base = App.Vector(100, 0, 0)
doc.recompute()
print('SUCCESS: Cylinder created at (100,0,0)')
"""
            result = server.execute_code(code_setup)
            if not result.get("success") or "SUCCESS" not in result.get("message", ""):
                self.log(f"❌ FAIL: Impossible de créer le cylindre de test")
                self.failed_count += 1
                return False
            
            # Appliquer miroir plan YZ
            code_mirror = f"""
import FreeCAD as App
doc = App.getDocument('{self.doc_name}')
src = doc.getObject('TestCylinder')

if not src:
    print('ERROR: Source object TestCylinder not found')
else:
    try:
        mirror = doc.addObject('Part::Mirroring', 'TestCylinder_mirrored')
        mirror.Source = src
        mirror.Base = App.Vector(0, 0, 0)
        mirror.Normal = App.Vector(1, 0, 0)  # Plan YZ
        
        doc.recompute()
        
        # Fusionner
        fusion = doc.addObject('Part::MultiFuse', 'TestCylinder_mirrored_fused')
        fusion.Shapes = [src, mirror]
        doc.recompute()
        
        if fusion.Shape.isValid():
            mirror.Visibility = False
            src.Visibility = False
            print(f'SUCCESS: Mirror created and fused into symmetric object')
        else:
            print('ERROR: Fusion produced invalid shape')
    except Exception as e:
        print(f'ERROR: Mirror failed - {{str(e)}}')
"""
            
            result = server.execute_code(code_mirror)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Miroir créé - {result.get('message')}")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error', result.get('message'))}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_circular_pattern(self):
        """Test 3: Circular pattern (répétition circulaire)"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: CIRCULAR_PATTERN ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            # Créer un petit cylindre
            code_setup = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
cyl = doc.addObject('Part::Cylinder', 'PatternCylinder')
cyl.Radius = 10
cyl.Height = 30
cyl.Placement.Base = App.Vector(50, 0, 0)  # Décentré
doc.recompute()
print('SUCCESS: Pattern cylinder created')
"""
            result = server.execute_code(code_setup)
            if not result.get("success") or "SUCCESS" not in result.get("message", ""):
                self.log(f"❌ FAIL: Impossible de créer le cylindre de test")
                self.failed_count += 1
                return False
            
            # Pattern circulaire 8 instances
            code_pattern = f"""
import FreeCAD as App
import Part
import math

doc = App.getDocument('{self.doc_name}')
src = doc.getObject('PatternCylinder')

if not src:
    print('ERROR: Source object PatternCylinder not found')
else:
    try:
        objects = [src]
        axis_point = App.Vector(0, 0, 0)
        axis_dir = App.Vector(0, 0, 1)  # Axe Z
        axis_dir.normalize()
        count = 8
        angle_step = 360.0 / count
        
        # Créer copies rotées
        for i in range(1, count):
            angle_deg = i * angle_step
            rot = App.Rotation(axis_dir, angle_deg)
            
            copy = doc.addObject('Part::Feature', 'PatternCylinder_copy_' + str(i))
            
            original_center = src.Placement.Base
            vec_from_axis = original_center - axis_point
            rotated_vec = rot.multVec(vec_from_axis)
            new_center = axis_point + rotated_vec
            
            new_rotation = rot.multiply(src.Placement.Rotation)
            
            copy.Shape = src.Shape.copy()
            copy.Placement = App.Placement(new_center, new_rotation)
            objects.append(copy)
        
        # Fusionner
        if len(objects) > 1:
            pattern = doc.addObject('Part::MultiFuse', 'CircularPattern')
            pattern.Shapes = objects
            doc.recompute()
            
            if pattern.Shape.isValid():
                for obj in objects:
                    obj.Visibility = False
                print(f'SUCCESS: Circular pattern created with {{count}} instances')
            else:
                print('ERROR: Pattern fusion produced invalid shape')
    except Exception as e:
        print(f'ERROR: Circular pattern failed - {{str(e)}}')
"""
            
            result = server.execute_code(code_pattern)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Pattern circulaire créé - {result.get('message')}")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error', result.get('message'))}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_linear_pattern(self):
        """Test 4: Linear pattern (répétition linéaire)"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: LINEAR_PATTERN ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            # Créer un petit cube
            code_setup = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
box = doc.addObject('Part::Box', 'LinearBox')
box.Length = 20
box.Width = 20
box.Height = 20
doc.recompute()
print('SUCCESS: Linear box created')
"""
            result = server.execute_code(code_setup)
            if not result.get("success") or "SUCCESS" not in result.get("message", ""):
                self.log(f"❌ FAIL: Impossible de créer le cube de test")
                self.failed_count += 1
                return False
            
            # Pattern linéaire 5 instances le long de X
            code_pattern = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
src = doc.getObject('LinearBox')

if not src:
    print('ERROR: Source object LinearBox not found')
else:
    try:
        objects = [src]
        direction = App.Vector(1, 0, 0)  # Direction X
        direction.normalize()
        spacing = 50.0
        count = 5
        
        # Créer copies
        for i in range(1, count):
            offset = direction * (spacing * i)
            
            copy = doc.addObject('Part::Feature', 'LinearBox_copy_' + str(i))
            copy.Shape = src.Shape.copy()
            
            new_placement = src.Placement.copy()
            new_placement.Base = src.Placement.Base + offset
            copy.Placement = new_placement
            
            objects.append(copy)
        
        # Fusionner
        if len(objects) > 1:
            pattern = doc.addObject('Part::MultiFuse', 'LinearPattern')
            pattern.Shapes = objects
            doc.recompute()
            
            if pattern.Shape.isValid():
                for obj in objects:
                    obj.Visibility = False
                print(f'SUCCESS: Linear pattern created with {{count}} instances, spacing {{spacing}}')
            else:
                print('ERROR: Pattern fusion produced invalid shape')
    except Exception as e:
        print(f'ERROR: Linear pattern failed - {{str(e)}}')
"""
            
            result = server.execute_code(code_pattern)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Pattern linéaire créé - {result.get('message')}")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error', result.get('message'))}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_import_airfoil_naca(self):
        """Test 5: Import NACA airfoil profile"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: IMPORT_AIRFOIL_NACA ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            # Import profil NACA 2412
            code_naca = f"""
import FreeCAD as App
import Part
import Sketcher
import math

doc = App.getDocument('{self.doc_name}')

def naca_4digit(code, chord, num_points=50):
    m = int(code[0]) / 100.0
    p = int(code[1]) / 10.0
    t = int(code[2:4]) / 100.0
    
    beta = [i * math.pi / num_points for i in range(num_points + 1)]
    x = [(1 - math.cos(b)) / 2 * chord for b in beta]
    
    yt = []
    for xi in x:
        xc = xi / chord
        yt_val = 5 * t * chord * (0.2969 * math.sqrt(xc) - 0.1260 * xc - 
                                   0.3516 * xc**2 + 0.2843 * xc**3 - 0.1015 * xc**4)
        yt.append(yt_val)
    
    yc = []
    dyc_dx = []
    for xi in x:
        xc = xi / chord
        if xc < p:
            yc_val = m * (2 * p * xc - xc**2) / (p**2) * chord if p > 0 else 0
            dyc_val = 2 * m * (p - xc) / (p**2) if p > 0 else 0
        else:
            yc_val = m * ((1 - 2*p) + 2*p*xc - xc**2) / ((1-p)**2) * chord if p < 1 else 0
            dyc_val = 2 * m * (p - xc) / ((1-p)**2) if p < 1 else 0
        yc.append(yc_val)
        dyc_dx.append(dyc_val)
    
    xu = [x[i] - yt[i] * math.sin(math.atan(dyc_dx[i])) for i in range(len(x))]
    yu = [yc[i] + yt[i] * math.cos(math.atan(dyc_dx[i])) for i in range(len(x))]
    xl = [x[i] + yt[i] * math.sin(math.atan(dyc_dx[i])) for i in range(len(x))]
    yl = [yc[i] - yt[i] * math.cos(math.atan(dyc_dx[i])) for i in range(len(x))]
    
    return xu, yu, xl, yl

try:
    xu, yu, xl, yl = naca_4digit('2412', 1000)
    
    sketch = doc.addObject('Sketcher::SketchObject', 'NACA2412')
    sketch.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation())
    
    # Ajouter points
    upper_points = [App.Vector(xu[i], yu[i], 0) for i in range(0, len(xu), 5)]
    lower_points = [App.Vector(xl[i], yl[i], 0) for i in range(0, len(xl), 5)]
    
    # Créer polylignes
    for i in range(len(upper_points)-1):
        sketch.addGeometry(Part.LineSegment(upper_points[i], upper_points[i+1]))
    
    for i in range(len(lower_points)-1):
        sketch.addGeometry(Part.LineSegment(lower_points[i], lower_points[i+1]))
    
    doc.recompute()
    print(f'SUCCESS: NACA 2412 airfoil imported with chord 1000mm')
except Exception as e:
    print(f'ERROR: Failed to import airfoil - {{str(e)}}')
"""
            
            result = server.execute_code(code_naca)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Profil NACA importé - {result.get('message')}")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error', result.get('message'))}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_reference_plane(self):
        """Test 6: Create reference plane"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: CREATE_REFERENCE_PLANE ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            # Créer plan de référence point + normale
            code_plane = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')

try:
    pos = App.Vector(0, 0, 100)
    norm = App.Vector(0, 0, 1)
    norm.normalize()
    
    plane_shape = Part.makePlane(500, 500, pos, norm)
    plane_obj = doc.addObject('Part::Feature', 'RefPlane')
    plane_obj.Shape = plane_shape
    
    doc.recompute()
    print('SUCCESS: Reference plane created from point and normal')
except Exception as e:
    print(f'ERROR: Failed to create reference plane - {{str(e)}}')
"""
            
            result = server.execute_code(code_plane)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Plan de référence créé - {result.get('message')}")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error', result.get('message'))}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def run_all_tests(self):
        """Exécute tous les tests avancés"""
        self.log("=" * 60)
        self.log("TESTS DES FONCTIONNALITÉS AVANCÉES CORSAIR")
        self.log(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)
        
        if self.setup_document():
            self.test_add_fillet()
            time.sleep(1)
            
            self.test_mirror_object()
            time.sleep(1)
            
            self.test_circular_pattern()
            time.sleep(1)
            
            self.test_linear_pattern()
            time.sleep(1)
            
            self.test_import_airfoil_naca()
            time.sleep(1)
            
            self.test_reference_plane()
        else:
            self.log("\n❌ ERREUR: Impossible de créer le document de test")
        
        self.print_summary()
        self.save_results()
    
    def print_summary(self):
        """Affiche le résumé des tests"""
        self.log("\n" + "=" * 60)
        self.log("RÉSUMÉ DES TESTS AVANCÉS")
        self.log("=" * 60)
        self.log(f"Total tests: {self.test_count}")
        self.log(f"✅ Réussis: {self.passed_count}")
        self.log(f"❌ Échoués: {self.failed_count}")
        
        if self.test_count > 0:
            success_rate = (self.passed_count / self.test_count) * 100
            self.log(f"Taux de réussite: {success_rate:.1f}%")
            
            if success_rate == 100:
                self.log("\n🎉 PARFAIT ! Toutes les fonctionnalités avancées fonctionnent !")
            elif success_rate >= 80:
                self.log("\n👍 Très bon ! La plupart des fonctionnalités fonctionnent")
            elif success_rate >= 50:
                self.log("\n⚠️ Moyen - Des corrections sont nécessaires")
            else:
                self.log("\n❌ Attention - Beaucoup de corrections nécessaires")
        
        self.log("=" * 60)
    
    def save_results(self):
        """Sauvegarde les résultats dans un fichier"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.results))
            self.log(f"\nRésultats sauvegardés dans: {self.output_file}")
        except Exception as e:
            self.log(f"\n❌ Erreur sauvegarde résultats: {str(e)}")


if __name__ == "__main__":
    print("Démarrage des tests des fonctionnalités avancées Corsair...")
    print("IMPORTANT: Assurez-vous que FreeCAD et le serveur XML-RPC sont lancés!")
    print("Attente 3 secondes avant démarrage...\n")
    time.sleep(3)
    
    tester = TestAdvancedFeatures()
    tester.run_all_tests()

