import json

path = r"C:\Users\GHC\repos\OMEGA_QUANT\.ly_state\session\phase_gates.json"
with open(path, "r", encoding="utf-8-sig") as f:
    gates = json.load(f)

gate_name = "HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623"
if gate_name in gates:
    print(json.dumps(gates[gate_name], indent=4))
else:
    print(f"Gate {gate_name} not found.")
