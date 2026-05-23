import os
import re

roots = ['OMEGA_QUANT/packages', 'OMEGA_QUANT/tests', 'docs']
pat = re.compile(r'(Task State Machine|state machine|scheduler|event bus|checkpoint|worker lifecycle|CREATED|DISPATCHED|VERIFYING)', re.I)

for root in roots:
    if not os.path.exists(root):
        continue
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not (fn.endswith('.py') or fn.endswith('.md')):
                continue
            p = os.path.join(dp, fn)
            try:
                with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, l in enumerate(f, 1):
                        if pat.search(l):
                            print(f"{p}:{i}:{l.strip()[:180]}")
            except Exception:
                pass
