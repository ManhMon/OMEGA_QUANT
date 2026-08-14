import json

path = '.ly_state/session/phase_gates.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

if 'macro_micro_data_v8_detailed_plan' in data:
    data['macro_micro_data_v8_detailed_plan']['timestamp'] = "2026-08-11T00:00:00Z"

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
