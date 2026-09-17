"""Fix writer_auditor_separated field for HYBRID_REGIME_FULL_BACKTEST_ADAPTER_FIX_20260621."""
import json
from pathlib import Path

REPO = Path(r'C:\Users\GHC\repos\OMEGA_QUANT')
GATES_FILE = REPO / '.ly_state' / 'session' / 'phase_gates.json'

raw = GATES_FILE.read_bytes()
gates = json.loads(raw.decode('utf-8-sig'))

gate_name = 'HYBRID_REGIME_FULL_BACKTEST_ADAPTER_FIX_20260621'
if gate_name in gates:
    gates[gate_name]['writer_auditor_separated'] = True
    print(f"Updated '{gate_name}' writer_auditor_separated to True")
else:
    print(f"Gate '{gate_name}' not found!")

output = json.dumps(gates, indent=2, ensure_ascii=False, sort_keys=False)
GATES_FILE.write_text(output, encoding='utf-8', newline='\n')
print(f"Saved phase_gates.json")
