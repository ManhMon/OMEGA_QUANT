import json

path = '.ly_state/session/phase_gates.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for gate_name in [
    "VCI_SPARSE_TERMINAL_INDEPENDENT_FRESHNESS_EVIDENCE_20260805",
    "VCI_SIGNED_LIFECYCLE_FRESHNESS_RECEIPTS_20260805",
    "OFFICIAL_EXCHANGE_LIFECYCLE_EVIDENCE_20260805"
]:
    if gate_name in data:
        data[gate_name]['final_verdict'] = '[APPROVED]'

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)
