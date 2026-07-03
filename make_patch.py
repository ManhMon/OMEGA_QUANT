
import sys
sys.path.insert(0, '.')
import scripts.sod_gate_enforcer as sg

import inspect
source = inspect.getsource(sg.check_sod_compliance)

with open('patched_sod.py', 'w') as f:
    f.write(source.replace('all_pass = False', 'print(f"Failed at line {sys._getframe().f_lineno} for {phase_name}"); all_pass = False'))
