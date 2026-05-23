import json, subprocess, sys

# Get schema via openclaw config schema
res = subprocess.run(['openclaw','config','schema'], capture_output=True, text=True)
if res.returncode!=0:
    print('ERR', res.stderr)
    sys.exit(1)

schema=json.loads(res.stdout)

# Recursively find keys of interest
def walk(obj, path=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            lk = k.lower()
            if any(t in lk for t in ['external','bind','sandbox','openshell','allowpath','path','dangerous']):
                if isinstance(v, dict) and ('type' in v or 'description' in v or 'title' in v):
                    print(f'PATH: {p}')
                    for fld in ['type','title','description','enum','default']:
                        if fld in v:
                            val = v[fld]
                            if isinstance(val, str) and len(val) > 200:
                                val = val[:200] + '...'
                            print(f'  {fld}: {val}')
                    print()
            walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]")

walk(schema)
