"""
Test runner for VTMS tests
"""

import sys
import os
import subprocess
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def run_tests():
    """Run all tests"""
    print("Running VTMS Test Suite...")
    print("=" * 50)
    
    test_files = [
        "tests/test_config.py",
        "tests/test_mqtt_handlers.py", 
        "tests/test_myobd.py",
        "tests/test_client.py"
    ]
    
    total_passed = 0
    total_failed = 0
    
    for test_file in test_files:
        print(f"\nRunning {test_file}...")
        print("-" * 30)
        
        try:
            # Try to run with pytest first
            result = subprocess.run([
                sys.executable, "-m", "pytest", test_file, "-v"
            ], capture_output=True, text=True, cwd=project_root)
            
            if result.returncode == 0:
                print("✅ PASSED")
                lines = result.stdout.split('\n')
                for line in lines:
                    if '::' in line and ('PASSED' in line or 'FAILED' in line):
                        print(f"  {line}")
                total_passed += 1
            else:
                print("❌ FAILED")
                print(result.stdout)
                print(result.stderr)
                total_failed += 1
                
        except FileNotFoundError:
            # Fallback to running as Python module
            try:
                result = subprocess.run([
                    sys.executable, test_file
                ], capture_output=True, text=True, cwd=project_root)
                
                if result.returncode == 0:
                    print("✅ PASSED (manual run)")
                    total_passed += 1
                else:
                    print("❌ FAILED (manual run)")
                    print(result.stdout)
                    print(result.stderr)
                    total_failed += 1
            except Exception as e:
                print(f"❌ ERROR running {test_file}: {e}")
                total_failed += 1
    
    print("\n" + "=" * 50)
    print(f"Test Summary: {total_passed} passed, {total_failed} failed")
    print("=" * 50)
    
    return total_failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
