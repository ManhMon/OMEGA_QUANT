import json
import numpy as np

path = '.ly_state/session/pipeline_state_hybrid/fold_9/pipeline_state_hybrid_fold9_Hybrid.json'
with open(path) as fh:
    data = json.load(fh)

print("Keys:", list(data.keys()))
if 'last_weights' in data:
    print("last_weights:", data['last_weights'])

# Let's inspect weights history if present, or other keys
for k, v in data.items():
    if isinstance(v, list):
        print(f"Key '{k}': list of length {len(v)}")
        if len(v) > 0:
            print("  First element type:", type(v[0]))
    elif isinstance(v, dict):
        print(f"Key '{k}': dict with keys {list(v.keys())[:10]}")
    else:
        print(f"Key '{k}': {type(v)} (value: {v})")
