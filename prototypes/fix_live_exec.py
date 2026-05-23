import re

f = 'OMEGA_QUANT/packages/quant/src/omega/quant/live_execution_bridge.py'
with open(f, 'r', encoding='utf-8') as src:
    content = src.read()

# FIX 1: Replace lambda in field(default_factory=...)
content = re.sub(
    r'field\(default_factory=lambda: datetime\.now\(UTC\)\)',
    'field(default_factory=_get_now_utc)',
    content
)

# FIX 2: Add _get_now_utc helper before ExecutionOrder class
if '_get_now_utc' not in content:
    insert_pos = content.find('@dataclass\nclass ExecutionOrder:')
    if insert_pos > 0:
        helper = 'def _get_now_utc() -> datetime:\n    return datetime.now(UTC)\n\n'
        content = content[:insert_pos] + helper + content[insert_pos:]

# Write the file
with open(f, 'w', encoding='utf-8') as dst:
    dst.write(content)

print('Fixed lambda violations in live_execution_bridge.py')
