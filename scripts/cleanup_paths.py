"""Cleanup script to systematically fix hardcoded openclaw and packages paths."""
import re
import pathlib

# Exclude archive directory
EXCLUDE_DIRS = {'archive', '.git', '.pytest_cache', '.ly_state'}

def process_file(path: pathlib.Path):
    try:
        content = path.read_text(encoding='utf-8')
        encoding = 'utf-8'
    except Exception:
        try:
            content = path.read_text(encoding='latin-1')
            encoding = 'latin-1'
        except Exception:
            return

    abs_path = path.resolve()
    abs_root = pathlib.Path('.').resolve()
    depth = len(abs_path.parts) - len(abs_root.parts) - 1
    if depth < 0:
        return

    lines = content.splitlines()
    modified = False
    new_lines = []
    
    skip_mode = False
    i = 0
    while i < len(lines):
        line = lines[i]
        
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))
            if not skip_mode:
                new_lines.append("from pathlib import Path")
                new_lines.append("import sys")
                new_lines.append(f"_REPO_ROOT = Path(__file__).resolve().parents[{depth}]")
                new_lines.append("if str(_REPO_ROOT / 'src') not in sys.path:")
                new_lines.append("    sys.path.insert(0, str(_REPO_ROOT / 'src'))")
                skip_mode = True
                modified = True
            i += 1
            continue
            
        if skip_mode:
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))
                i += 1
                continue
            else:
                skip_mode = False
                
        # Fix read_parquet paths to market_2015_now.parquet
        if 'pd.read_parquet' in line and ('.openclaw' in line or 'packages' in line) and 'market_2015_now.parquet' in line:
            # Replace the string argument with dynamic path
            # Look for r'...' or '...'
            pattern = r'r?[\'"]C:\\\\Users\\\\GHC\\\\\.openclaw\\\\workspace\\\\data\\\\market_2015_now\.parquet[\'"]'
            line_replaced = re.sub(pattern, f"str(Path(__file__).resolve().parents[{depth}] / 'data' / 'market_2015_now.parquet')", line)
            
            pattern_2 = r'r?[\'"]C:\\Users\\GHC\\\.openclaw\\workspace\\data\\market_2015_now\.parquet[\'"]'
            line_replaced = re.sub(pattern_2, f"str(Path(__file__).resolve().parents[{depth}] / 'data' / 'market_2015_now.parquet')", line_replaced)
            
            if line_replaced != line:
                line = line_replaced
                modified = True
                print(f"[{path.name}] Replaced read_parquet path")
                
        # Fix risk_status.json path
        if 'risk_status.json' in line and '.openclaw' in line:
            pattern = r'r?[\'"]C:\\\\Users\\\\GHC\\\\\.openclaw\\\\workspace\\\\OMEGA_QUANT\\\\(OMEGA_QUANT\\\\)?\.ly_state\\\\session\\\\risk_status\.json[\'"]'
            line_replaced = re.sub(pattern, f"str(Path(__file__).resolve().parents[{depth}] / '.ly_state' / 'session' / 'risk_status.json')", line)
            
            pattern_2 = r'r?[\'"]C:\\Users\\GHC\\\.openclaw\\workspace\\OMEGA_QUANT\\(OMEGA_QUANT\\)?\.ly_state\\session\\risk_status\.json[\'"]'
            line_replaced = re.sub(pattern_2, f"str(Path(__file__).resolve().parents[{depth}] / '.ly_state' / 'session' / 'risk_status.json')", line_replaced)
            
            if line_replaced != line:
                line = line_replaced
                modified = True
                print(f"[{path.name}] Replaced risk_status.json path")

        # Replace packages/.../src with src
        if 'packages/' in line or 'packages\\' in line:
            line_replaced = re.sub(
                r'packages/(quant|core|data|risk|observability|infra|governance)/src',
                'src',
                line
            )
            line_replaced = re.sub(
                r'packages\\(quant|core|data|risk|observability|infra|governance)\\src',
                'src',
                line_replaced
            )
            if line_replaced != line:
                line = line_replaced
                modified = True
                print(f"[{path.name}] Fixed packages/.../src in line")

        new_lines.append(line)
        i += 1

    if modified:
        path.write_text('\n'.join(new_lines) + '\n', encoding=encoding)
        print(f"[{path.name}] Successfully refactored and saved")

def main():
    root = pathlib.Path('.')
    for path in root.rglob('*.py'):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        process_file(path)

if __name__ == '__main__':
    main()
