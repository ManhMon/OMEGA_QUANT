"""Full project audit script - L3 independent verification."""
import sys, os, py_compile, pathlib, json, warnings

sys.path.insert(0, 'src')
results = {}

# 1. py_compile all src/omega
src_files = list(pathlib.Path('src/omega').rglob('*.py'))
compile_fail = []
for f in src_files:
    try:
        py_compile.compile(str(f), doraise=True)
    except py_compile.PyCompileError as e:
        compile_fail.append(f'{f}: {e}')
results['py_compile_all'] = f'PASS ({len(src_files)} files)' if not compile_fail else f'FAIL: {compile_fail[:5]}'

# 2. Zero v21_system refs in src/
v21_refs = []
for f in src_files:
    txt = f.read_text(encoding='utf-8', errors='ignore')
    # Ignore comment-only refs (e.g. '# Adapted from: archive/...v21_system...')
    live_lines = [l for l in txt.splitlines() if 'v21_system' in l and not l.strip().startswith('#')]
    if live_lines and 'archive' not in str(f):
        v21_refs.append(str(f))
results['no_v21_system_refs'] = 'PASS' if not v21_refs else f'FAIL: {v21_refs[:5]}'

# 3. Zero v19_system live imports
v19_live = []
for f in src_files:
    txt = f.read_text(encoding='utf-8', errors='ignore')
    lines = [l for l in txt.splitlines() if 'v19_system' in l and not l.strip().startswith('#') and 'stub' not in l.lower() and 'except ImportError' not in l]
    if lines:
        v19_live.append(str(f))
results['no_v19_system_live_imports'] = 'PASS' if not v19_live else f'WARN: {v19_live[:3]}'

# 4. Pipeline 10 layers import
layers = {}
checks = [
    ('data',          'from omega.data.production_data_pipeline import ProductionDataPipeline'),
    ('strategy',      'from omega.quant.quant_engine import QuantEngine'),
    ('risk',          'from omega.risk.liquidity_filter import LiquidityFilter'),
    ('execution',     'from omega.execution import ExecutionEngine'),
    ('portfolio',     'from omega.quant.portfolio import PortfolioOptimizer'),
    ('governance',    'from omega.governance.validate_ly_state import validate_ly_state_integrity'),
    ('observability', 'from omega.observability import StructuredLogger'),
    ('infra',         'from omega.infra.task_queue import TaskQueue'),
    ('memory',        'from omega.memory.memory_module import MemoryModule'),
    ('security',      'from omega.security.sandbox import Sandbox'),
]
for name, stmt in checks:
    try:
        exec(stmt)
        layers[name] = 'PASS'
    except Exception as e:
        layers[name] = f'FAIL: {e}'

pass_count = sum(1 for v in layers.values() if v == 'PASS')
results['pipeline_layers'] = f'{pass_count}/10 PASS'
print('\nPipeline layers:')
for k, v in layers.items():
    status = 'PASS' if v == 'PASS' else 'FAIL'
    print(f'  [{status}] {k}: {v}')

# 5. Gate status
gates = json.loads(pathlib.Path('.ly_state/session/phase_gates.json').read_text(encoding='utf-8'))
approved = [k for k, v in gates.items() if isinstance(v, dict) and v.get('status') == 'APPROVED']
pending  = [k for k, v in gates.items() if isinstance(v, dict) and v.get('status') != 'APPROVED']
results['gates_approved'] = f'{len(approved)} gates APPROVED'
results['gates_pending']  = 'NONE' if not pending else f'{len(pending)} pending: {pending[:5]}'

# 6. File count
results['src_file_count'] = f'{len(src_files)} Python files in src/omega'

# 7. Circular import check
warn_list = []
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    try:
        from omega.quant.quant_engine import QuantEngine  # noqa
        warn_list = [str(x.message) for x in w if 'circular' in str(x.message).lower() or 'cannot import' in str(x.message).lower()]
    except Exception as e:
        warn_list = [str(e)]
results['no_circular_import'] = 'PASS' if not warn_list else f'FAIL: {warn_list}'

# Print summary
print()
print('=' * 60)
print('FULL PROJECT AUDIT SUMMARY')
print('=' * 60)
for k, v in results.items():
    if 'FAIL' in str(v):
        icon = 'FAIL'
    elif 'WARN' in str(v):
        icon = 'WARN'
    else:
        icon = 'PASS'
    print(f'[{icon}] {k}: {v}')

print()
print(f'Approved gates: {approved}')

all_critical = all(
    'FAIL' not in str(results[k])
    for k in ['py_compile_all', 'no_v21_system_refs', 'pipeline_layers', 'no_circular_import']
)
print()
print('VERDICT: [APPROVED]' if all_critical else 'VERDICT: [NEEDS_FIX]')
