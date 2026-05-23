from pathlib import Path
import json

omega = Path(r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT')
gates = json.loads((omega / '.ly_state' / 'session' / 'phase_gates.json').read_text(encoding='utf-8'))

for label in ['PHASE 11', 'PHASE 13', 'PHASE 14']:
    print(f'=== {label} GATES ===')
    needle = label.replace(' ', '_')
    for k, v in gates.items():
        if needle in k or needle.replace('_', '') in k:
            status = v.get('status', 'N/A')
            print(f'{k}: {status}')
    print()
