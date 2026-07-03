import glob
import os

files = glob.glob('src/omega/quant/alpha/*.py') + ['src/omega/quant/ultimate_alpha_arsenal.py']
for f in files:
    if not os.path.exists(f):
        continue
    with open(f, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    for i, line in enumerate(lines):
        length = len(line.rstrip('\r\n'))
        if length > 79:
            stripped = line.strip()
            is_comment = stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'") or '"""' in line or "'''" in line
            print(f"{f}:{i+1} ({length}): {stripped[:40]}... (is_comment={is_comment})")
