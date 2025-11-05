"""
Tests pour les opérations booléennes du serveur MCP FreeCAD
Date création: 2025-10-08
"""

import sys
import time
import json
from pathlib import Path

class TestBooleanOperations:
    """Tests des opérations booléennes"""
    
    def __init__(self, output_file="test_results_boolean.txt"):
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
        """Crée un document et des objets de test"""
        self.log("\n=== SETUP: Création du document et objets ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            self.doc_name = f"BooleanTest_{int(time.time())}"
            result = server.create_document(self.doc_name)
            
            if not result.get("success"):
                self.log(f"❌ Échec création document: {result.get('error')}")
                return False
            
            self.log(f"✅ Document '{self.doc_name}' créé")
            
            # Créer deux cubes qui se chevauchent
            code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')

# Cube 1
box1 = doc.addObject('Part::Box', 'Box1')
box1.Length = 100
box1.Width = 100
box1.Height = 100
box1.Placement.Base = App.Vector(0, 0, 0)

# Cube 2 - chevauche Box1
box2 = doc.addObject('Part::Box', 'Box2')
box2.Length = 100
box2.Width = 100
box2.Height = 100
box2.Placement.Base = App.Vector(50, 50, 50)

doc.recompute()
print('SUCCESS: Test objects created')
"""
            
            result = server.execute_code(code)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ Objets de test créés (2 cubes)")
                return True
            else:
                self.log(f"❌ Échec création objets: {result.get('error', result.get('message'))}")
                return False
                
        except Exception as e:
            self.log(f"❌ Exception setup: {str(e)}")
            return False
    
    def test_boolean_union(self):
        """Test fusion booléenne (Union)"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: BOOLEAN_UNION ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
box1 = doc.getObject('Box1')
box2 = doc.getObject('Box2')

if box1 and box2:
    union = doc.addObject('Part::MultiFuse', 'Union')
    union.Shapes = [box1, box2]
    doc.recompute()
    
    # Vérifier que l'union existe et a un volume
    if hasattr(union.Shape, 'Volume') and union.Shape.Volume > 0:
        print(f'SUCCESS: Union created with volume={{union.Shape.Volume:.2f}}')
    else:
        print('ERROR: Union has no volume')
else:
    print('ERROR: Source objects not found')
"""
            
            result = server.execute_code(code)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Union booléenne réussie - {result.get('message')}")
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
    
    def test_boolean_cut(self):
        """Test soustraction booléenne (Cut)"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: BOOLEAN_CUT ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
box1 = doc.getObject('Box1')
box2 = doc.getObject('Box2')

if box1 and box2:
    cut = doc.addObject('Part::Cut', 'Cut')
    cut.Base = box1
    cut.Tool = box2
    doc.recompute()
    
    # Vérifier que le cut existe et a un volume
    if hasattr(cut.Shape, 'Volume') and cut.Shape.Volume > 0:
        print(f'SUCCESS: Cut created with volume={{cut.Shape.Volume:.2f}}')
    else:
        print('ERROR: Cut has no volume')
else:
    print('ERROR: Source objects not found')
"""
            
            result = server.execute_code(code)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Cut booléen réussi - {result.get('message')}")
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
    
    def test_boolean_intersection(self):
        """Test intersection booléenne (Common)"""
        self.test_count += 1
        self.log(f"\n=== Test {self.test_count}: BOOLEAN_INTERSECTION ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import FreeCAD as App
import Part

doc = App.getDocument('{self.doc_name}')
box1 = doc.getObject('Box1')
box2 = doc.getObject('Box2')

if box1 and box2:
    common = doc.addObject('Part::MultiCommon', 'Intersection')
    common.Shapes = [box1, box2]
    doc.recompute()
    
    # Vérifier que l'intersection existe et a un volume
    if hasattr(common.Shape, 'Volume') and common.Shape.Volume > 0:
        print(f'SUCCESS: Intersection created with volume={{common.Shape.Volume:.2f}}')
    else:
        print('ERROR: Intersection has no volume')
else:
    print('ERROR: Source objects not found')
"""
            
            result = server.execute_code(code)
            
            if result.get("success") and "SUCCESS" in result.get("message", ""):
                self.log(f"✅ PASS: Intersection booléenne réussie - {result.get('message')}")
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
        """Exécute tous les tests booléens"""
        self.log("=" * 60)
        self.log("TESTS DES OPÉRATIONS BOOLÉENNES - FreeCAD MCP")
        self.log(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)
        
        if self.setup_document():
            self.test_boolean_union()
            self.test_boolean_cut()
            self.test_boolean_intersection()
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
    print("Démarrage des tests des opérations booléennes...")
    print("IMPORTANT: Assurez-vous que FreeCAD et le serveur XML-RPC sont lancés!")
    print("Attente 3 secondes avant démarrage...\n")
    time.sleep(3)
    
    tester = TestBooleanOperations()
    tester.run_all_tests()



