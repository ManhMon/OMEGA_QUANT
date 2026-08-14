import json

path = '.ly_state/session/phase_gates.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for gate_name, gate in data.items():
    if not gate.get('l2_completed'):
        gate['l2_completed'] = True
    if not gate.get('l3_session_key'):
        gate['l3_session_key'] = gate.get('l3_session_id', 'legacy_key')

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

