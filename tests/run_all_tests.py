"""
Script principal d'exécution de tous les tests FreeCAD MCP
Date création: 2025-10-08
"""

import sys
import time
import subprocess
from pathlib import Path

class TestRunner:
    """Exécute tous les tests et génère un rapport consolidé"""
    
    def __init__(self):
        self.tests_dir = Path(__file__).parent
        self.results = []
        self.total_tests = 0
        self.total_passed = 0
        self.total_failed = 0
        
    def log(self, message):
        """Enregistre et affiche un message"""
        print(message)
        self.results.append(message)
    
    def run_test_file(self, test_file, timeout=120):
        """Exécute un fichier de test avec timeout"""
        self.log(f"\n{'='*60}")
        self.log(f"Exécution: {test_file.name}")
        self.log(f"{'='*60}")
        
        try:
            # Créer fichier de sortie temporaire
            output_file = self.tests_dir / f"temp_output_{int(time.time())}.txt"
            
            # Préparer commande
            cmd = [sys.executable, str(test_file)]
            
            # Exécuter avec timeout
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                
                # Afficher sortie
                if stdout:
                    self.log(stdout)
                
                if stderr and process.returncode != 0:
                    self.log(f"STDERR: {stderr}")
                
                # Nettoyer fichier temporaire
                if output_file.exists():
                    output_file.unlink()
                
                return process.returncode == 0
                
            except subprocess.TimeoutExpired:
                process.kill()
                self.log(f"❌ TIMEOUT: Test dépassé {timeout} secondes")
                return False
                
        except Exception as e:
            self.log(f"❌ ERREUR EXÉCUTION: {str(e)}")
            return False
    
    def parse_results(self, test_name):
        """Parse les résultats d'un test depuis son fichier"""
        result_file = self.tests_dir / f"test_results_{test_name}.txt"
        
        if not result_file.exists():
            self.log(f"⚠️ Fichier résultats non trouvé: {result_file}")
            return 0, 0, 0
        
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extraire statistiques
            tests = passed = failed = 0
            
            for line in content.split('\n'):
                if 'Total tests:' in line:
                    tests = int(line.split(':')[1].strip())
                elif 'Réussis:' in line:
                    passed = int(line.split(':')[1].strip())
                elif 'Échoués:' in line:
                    failed = int(line.split(':')[1].strip())
            
            return tests, passed, failed
            
        except Exception as e:
            self.log(f"⚠️ Erreur lecture résultats: {str(e)}")
            return 0, 0, 0
    
    def run_all_tests(self):
        """Exécute tous les tests disponibles"""
        self.log("="*60)
        self.log("SUITE DE TESTS COMPLÈTE - FreeCAD MCP")
        self.log(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("="*60)
        
        # Vérifier connexion FreeCAD
        self.log("\n🔍 Vérification de la connexion FreeCAD...")
        if not self.check_freecad_connection():
            self.log("\n❌ ERREUR CRITIQUE: FreeCAD non connecté!")
            self.log("Lancez FreeCAD avec le serveur XML-RPC avant les tests.")
            return False
        
        self.log("✅ FreeCAD connecté et prêt")
        
        # Liste des tests à exécuter
        test_files = [
            ('basic', 'test_basic_operations.py'),
            ('sketch', 'test_sketch_workflow.py'),
            ('boolean', 'test_boolean_operations.py'),
        ]
        
        results_summary = []
        
        for test_name, test_file in test_files:
            test_path = self.tests_dir / test_file
            
            if not test_path.exists():
                self.log(f"\n⚠️ SKIP: {test_file} non trouvé")
                continue
            
            # Exécuter le test
            success = self.run_test_file(test_path)
            
            # Parser résultats
            tests, passed, failed = self.parse_results(test_name)
            
            self.total_tests += tests
            self.total_passed += passed
            self.total_failed += failed
            
            results_summary.append({
                'name': test_name,
                'file': test_file,
                'success': success,
                'tests': tests,
                'passed': passed,
                'failed': failed
            })
            
            # Pause entre tests
            time.sleep(2)
        
        # Afficher résumé consolidé
        self.print_consolidated_summary(results_summary)
        
        # Sauvegarder rapport
        self.save_consolidated_report(results_summary)
        
        return self.total_failed == 0
    
    def check_freecad_connection(self):
        """Vérifie que FreeCAD est accessible"""
        try:
            import xmlrpc.client
            server = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            result = server.ping()
            return result is True
        except Exception as e:
            self.log(f"❌ Erreur connexion: {str(e)}")
            return False
    
    def print_consolidated_summary(self, results_summary):
        """Affiche le résumé consolidé de tous les tests"""
        self.log("\n" + "="*60)
        self.log("RÉSUMÉ CONSOLIDÉ DE TOUS LES TESTS")
        self.log("="*60)
        
        for result in results_summary:
            status = "✅ PASS" if result['success'] and result['failed'] == 0 else "❌ FAIL"
            self.log(f"\n{status} {result['name'].upper()}")
            self.log(f"  Fichier: {result['file']}")
            self.log(f"  Tests: {result['tests']}")
            self.log(f"  Réussis: {result['passed']}")
            self.log(f"  Échoués: {result['failed']}")
            if result['tests'] > 0:
                rate = (result['passed'] / result['tests']) * 100
                self.log(f"  Taux: {rate:.1f}%")
        
        self.log("\n" + "-"*60)
        self.log("TOTAUX GLOBAUX")
        self.log("-"*60)
        self.log(f"Total tests exécutés: {self.total_tests}")
        self.log(f"✅ Total réussis: {self.total_passed}")
        self.log(f"❌ Total échoués: {self.total_failed}")
        
        if self.total_tests > 0:
            global_rate = (self.total_passed / self.total_tests) * 100
            self.log(f"\n🎯 TAUX DE RÉUSSITE GLOBAL: {global_rate:.1f}%")
            
            if global_rate == 100:
                self.log("\n🎉 FÉLICITATIONS ! TOUS LES TESTS PASSENT !")
            elif global_rate >= 80:
                self.log("\n👍 Bon résultat, quelques corrections nécessaires")
            elif global_rate >= 50:
                self.log("\n⚠️ Résultat moyen, corrections importantes requises")
            else:
                self.log("\n❌ Résultat faible, révision majeure nécessaire")
        
        self.log("="*60)
    
    def save_consolidated_report(self, results_summary):
        """Sauvegarde le rapport consolidé"""
        report_file = self.tests_dir / f"TEST_REPORT_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.results))
            
            self.log(f"\n📄 Rapport consolidé sauvegardé: {report_file}")
            
            # Créer aussi un lien "latest"
            latest_link = self.tests_dir / "TEST_REPORT_LATEST.txt"
            try:
                if latest_link.exists():
                    latest_link.unlink()
                with open(latest_link, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(self.results))
                self.log(f"📄 Copie latest: {latest_link}")
            except:
                pass
                
        except Exception as e:
            self.log(f"\n❌ Erreur sauvegarde rapport: {str(e)}")


def main():
    """Point d'entrée principal"""
    print("\n" + "🚀 "*20)
    print("SUITE DE TESTS COMPLÈTE - FreeCAD MCP")
    print("🚀 "*20 + "\n")
    
    print("⚠️  IMPORTANT: Vérifications avant démarrage")
    print("   1. FreeCAD est lancé")
    print("   2. Le serveur XML-RPC FreeCAD est actif (port 9875)")
    print("   3. Aucun document important n'est ouvert (sera fermé)")
    print("\n⏳ Démarrage dans 5 secondes...\n")
    
    time.sleep(5)
    
    runner = TestRunner()
    success = runner.run_all_tests()
    
    # Code de sortie
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()



