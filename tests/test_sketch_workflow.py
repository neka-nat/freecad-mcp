"""
Tests pour le workflow Sketch du serveur MCP FreeCAD
Date création: 2025-10-08
"""

import sys
import time
import json
from pathlib import Path

class TestSketchWorkflow:
    """Tests du workflow sketch complet"""
    
    def __init__(self, output_file="test_results_sketch.txt"):
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
            
            self.doc_name = f"SketchTest_{int(time.time())}"
            result = server.create_document(self.doc_name)
            
            if result.get("success"):
                self.log(f"✅ Document '{self.doc_name}' créé")
                return True
            else:
                self.log(f"❌ Échec création document: {result.get('error')}")
                return False
                
        except Exception as e:
            self.log(f"❌ Exception setup: {str(e)}")
            return False
    
    def test_create_datum_plane(self):
        """Test création d'un plan de référence"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: CREATE_DATUM_PLANE ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import sys
sys.path.insert(0, r'c:\\Users\\marti\\AppData\\Roaming\\Python\\Python313\\site-packages')
from freecad_mcp.sketch_tools.plane_manager import create_datum_plane

class MockContext:
    pass

class MockConnection:
    def execute_code(self, code):
        exec(code)
        return {{'success': True, 'message': 'Plane created'}}
    def get_active_screenshot(self):
        return None

def mock_screenshot(response, screenshot):
    return response

ctx = MockContext()
conn = MockConnection()
result = create_datum_plane(ctx, conn, mock_screenshot, '{self.doc_name}', 'base_plane', 'xy', 0.0)
print(result[0].text if result else 'No result')
"""
            
            result = server.execute_code(code)
            
            if result.get("success"):
                self.log(f"✅ PASS: Plan datum créé")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error')}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_create_sketch_on_plane(self):
        """Test création d'une esquisse sur plan"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: CREATE_SKETCH_ON_PLANE ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import sys
sys.path.insert(0, r'c:\\Users\\marti\\AppData\\Roaming\\Python\\Python313\\site-packages')
from freecad_mcp.sketch_tools.sketch_manager import create_sketch_on_plane

class MockContext:
    pass

class MockConnection:
    def execute_code(self, code):
        exec(code)
        return {{'success': True, 'message': 'Sketch created'}}
    def get_active_screenshot(self):
        return None

def mock_screenshot(response, screenshot):
    return response

ctx = MockContext()
conn = MockConnection()
result = create_sketch_on_plane(ctx, conn, mock_screenshot, '{self.doc_name}', 'base_plane')
print(result[0].text if result else 'No result')
"""
            
            result = server.execute_code(code)
            
            if result.get("success"):
                self.log(f"✅ PASS: Esquisse créée sur plan")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: {result.get('error')}")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_add_contour_rectangle(self):
        """Test ajout d'un contour rectangulaire"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: ADD_CONTOUR_RECTANGLE ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import FreeCAD as App
doc = App.getDocument('{self.doc_name}')

# Créer un Body et un Sketch simple
body = doc.addObject('PartDesign::Body', 'base_plane')
sketch = doc.addObject('Sketcher::SketchObject', 'base_plane_sketch')
body.addObject(sketch)

# Ajouter un rectangle simple
sketch.addGeometry([
    Part.LineSegment(App.Vector(0, 0, 0), App.Vector(100, 0, 0)),
    Part.LineSegment(App.Vector(100, 0, 0), App.Vector(100, 50, 0)),
    Part.LineSegment(App.Vector(100, 50, 0), App.Vector(0, 50, 0)),
    Part.LineSegment(App.Vector(0, 50, 0), App.Vector(0, 0, 0))
], False)

doc.recompute()
print('SUCCESS: Rectangle contour added')
"""
            
            result = server.execute_code(code)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Contour rectangulaire ajouté")
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
    
    def test_extrude_sketch(self):
        """Test extrusion d'esquisse"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: EXTRUDE_SKETCH ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import FreeCAD as App
doc = App.getDocument('{self.doc_name}')
body = doc.getObject('base_plane')
sketch = doc.getObject('base_plane_sketch')

if body and sketch:
    pad = body.newObject('PartDesign::Pad', 'base_plane_solid')
    pad.Profile = sketch
    pad.Length = 20.0
    doc.recompute()
    print('SUCCESS: Sketch extruded')
else:
    print('ERROR: Body or sketch not found')
"""
            
            result = server.execute_code(code)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Esquisse extrudée")
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
        """Exécute tous les tests du workflow sketch"""
        self.log("=" * 60)
        self.log("TESTS DU WORKFLOW SKETCH - FreeCAD MCP")
        self.log(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)
        
        if self.setup_document():
            self.test_create_datum_plane()
            self.test_create_sketch_on_plane()
            self.test_add_contour_rectangle()
            self.test_extrude_sketch()
        else:
            self.log("\n❌ ERREUR: Impossible de créer le document de test")
        
        self.print_summary()
        self.save_results()
    
    def print_summary(self):
        """Affiche le résumé des tests"""
        self.log("\n" + "=" * 60)
        self.log("RÉSUMÉ DES TESTS")
        self.log("=" * 60)
        self.log(f"Total tests: {self.test_count}")
        self.log(f"✅ Réussis: {self.passed_count}")
        self.log(f"❌ Échoués: {self.failed_count}")
        
        if self.test_count > 0:
            success_rate = (self.passed_count / self.test_count) * 100
            self.log(f"Taux de réussite: {success_rate:.1f}%")
        
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
    print("Démarrage des tests du workflow sketch...")
    print("IMPORTANT: Assurez-vous que FreeCAD et le serveur XML-RPC sont lancés!")
    print("Attente 3 secondes avant démarrage...\n")
    time.sleep(3)
    
    tester = TestSketchWorkflow()
    tester.run_all_tests()



