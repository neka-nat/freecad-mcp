"""
Tests pour les opérations de base du serveur MCP FreeCAD
Date création: 2025-10-08
"""

import sys
import time
import json
from pathlib import Path

class TestBasicOperations:
    """Tests des opérations de base FreeCAD"""
    
    def __init__(self, output_file="test_results_basic.txt"):
        self.output_file = output_file
        self.results = []
        self.test_count = 0
        self.passed_count = 0
        self.failed_count = 0
        
    def log(self, message):
        """Enregistre un message dans les résultats"""
        print(message)
        self.results.append(message)
        
    def test_create_document(self):
        """Test création de document"""
        self.test_count += 1
        test_name = "CREATE_DOCUMENT"
        self.log(f"\n=== Test {self.test_count}: {test_name} ===")
        
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            doc_name = f"TestDoc_{int(time.time())}"
            result = server.create_document(doc_name)
            
            if result.get("success"):
                self.log(f"✅ PASS: Document '{doc_name}' créé avec succès")
                self.passed_count += 1
                return doc_name
            else:
                self.log(f"❌ FAIL: {result.get('error', 'Unknown error')}")
                self.failed_count += 1
                return None
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return None
    
    def test_create_basic_objects(self, doc_name):
        """Test création d'objets basiques"""
        self.test_count += 1
        test_name = "CREATE_BASIC_OBJECTS"
        self.log(f"\n=== Test {self.test_count}: {test_name} ===")
        
        if not doc_name:
            self.log("❌ SKIP: Pas de document disponible")
            return False
            
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            objects_to_create = [
                {
                    "Name": "TestBox",
                    "Type": "Part::Box",
                    "Properties": {
                        "Length": 100,
                        "Width": 50,
                        "Height": 30
                    }
                },
                {
                    "Name": "TestCylinder",
                    "Type": "Part::Cylinder",
                    "Properties": {
                        "Radius": 25,
                        "Height": 50
                    }
                },
                {
                    "Name": "TestSphere",
                    "Type": "Part::Sphere",
                    "Properties": {
                        "Radius": 30
                    }
                }
            ]
            
            all_success = True
            for obj_data in objects_to_create:
                result = server.create_object(doc_name, obj_data)
                if result.get("success"):
                    self.log(f"  ✅ Objet '{obj_data['Name']}' créé")
                else:
                    self.log(f"  ❌ Échec création '{obj_data['Name']}': {result.get('error')}")
                    all_success = False
            
            if all_success:
                self.log(f"✅ PASS: Tous les objets basiques créés")
                self.passed_count += 1
            else:
                self.log(f"❌ FAIL: Certains objets n'ont pas été créés")
                self.failed_count += 1
                
            return all_success
            
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_get_objects(self, doc_name):
        """Test récupération de la liste des objets"""
        self.test_count += 1
        test_name = "GET_OBJECTS"
        self.log(f"\n=== Test {self.test_count}: {test_name} ===")
        
        if not doc_name:
            self.log("❌ SKIP: Pas de document disponible")
            return False
            
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            objects = server.get_objects(doc_name)
            
            if objects and len(objects) > 0:
                self.log(f"✅ PASS: {len(objects)} objet(s) trouvé(s)")
                for obj in objects:
                    self.log(f"  - {obj.get('Name')} ({obj.get('Type')})")
                self.passed_count += 1
                return True
            else:
                self.log(f"❌ FAIL: Aucun objet trouvé")
                self.failed_count += 1
                return False
                
        except Exception as e:
            self.log(f"❌ FAIL: Exception - {str(e)}")
            self.failed_count += 1
            return False
    
    def test_edit_object(self, doc_name):
        """Test modification d'objet"""
        self.test_count += 1
        test_name = "EDIT_OBJECT"
        self.log(f"\n=== Test {self.test_count}: {test_name} ===")
        
        if not doc_name:
            self.log("❌ SKIP: Pas de document disponible")
            return False
            
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            result = server.edit_object(doc_name, "TestBox", {
                "Properties": {
                    "Length": 150,
                    "ViewObject": {
                        "ShapeColor": [1.0, 0.0, 0.0, 1.0]
                    }
                }
            })
            
            if result.get("success"):
                self.log(f"✅ PASS: Objet 'TestBox' modifié avec succès")
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
    
    def test_execute_code(self, doc_name):
        """Test exécution de code Python personnalisé"""
        self.test_count += 1
        test_name = "EXECUTE_CODE"
        self.log(f"\n=== Test {self.test_count}: {test_name} ===")
        
        if not doc_name:
            self.log("❌ SKIP: Pas de document disponible")
            return False
            
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            code = f"""
import FreeCAD as App
doc = App.getDocument('{doc_name}')
obj_count = len(doc.Objects)
print(f'Document contient {{obj_count}} objets')
"""
            
            result = server.execute_code(code)
            
            if result.get("success"):
                self.log(f"✅ PASS: Code exécuté - {result.get('message')}")
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
    
    def test_delete_object(self, doc_name):
        """Test suppression d'objet"""
        self.test_count += 1
        test_name = "DELETE_OBJECT"
        self.log(f"\n=== Test {self.test_count}: {test_name} ===")
        
        if not doc_name:
            self.log("❌ SKIP: Pas de document disponible")
            return False
            
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            
            result = server.delete_object(doc_name, "TestSphere")
            
            if result.get("success"):
                self.log(f"✅ PASS: Objet 'TestSphere' supprimé")
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
    
    def run_all_tests(self):
        """Exécute tous les tests basiques"""
        self.log("=" * 60)
        self.log("TESTS DES OPÉRATIONS DE BASE - FreeCAD MCP")
        self.log(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("=" * 60)
        
        doc_name = self.test_create_document()
        
        if doc_name:
            self.test_create_basic_objects(doc_name)
            self.test_get_objects(doc_name)
            self.test_edit_object(doc_name)
            self.test_execute_code(doc_name)
            self.test_delete_object(doc_name)
        
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
    print("Démarrage des tests des opérations de base...")
    print("IMPORTANT: Assurez-vous que FreeCAD et le serveur XML-RPC sont lancés!")
    print("Attente 3 secondes avant démarrage...\n")
    time.sleep(3)
    
    tester = TestBasicOperations()
    tester.run_all_tests()



