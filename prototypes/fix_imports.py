import os

files = [
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\tests\phase2\test_model_registry.py',
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\tests\phase2\test_model_trainer.py',
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\tests\phase2\test_model_validator.py',
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\tests\phase2\test_promotion_gate.py'
]

insert_code = """import sys\nimport os\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))\n"""

for f in files:
    try:
        with open(f, 'r') as file:
            content = file.read()
        
        # Remove old sys.path hacks if any
        content = content.replace("sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))\n", '')
        
        # Replace 'from omega.core' to 'from src.omega.core'
        content = content.replace('from omega.core.', 'from src.omega.core.')
        content = content.replace('import omega.core.', 'import src.omega.core.')
        
        if 'sys.path.insert(0' not in content:
            new_content = insert_code + content
            with open(f, 'w') as file:
                file.write(new_content)
            print(f"Fixed {f}")
    except Exception as e:
        print(f"Error {f}: {e}")
