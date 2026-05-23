#!/usr/bin/env python3
"""Fix Task instantiations in test_worker.py to match actual Task signature."""

from pathlib import Path

test_file = Path("OMEGA_QUANT/tests/phase1/test_worker.py")
content = test_file.read_text()

# Replace all Task instantiations
old_patterns = [
    '''Task(
            task_id="task-001",
            task_type=TaskType.CODING,
            description="Implement worker lifecycle",
            assigned_to="Backend Engineer"
        )''',
    '''Task(
            task_id="task-001",
            task_type=TaskType.CODING,
            description="Test task",
            assigned_to="Backend Engineer"
        )'''
]

new_pattern = '''Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )'''

for old in old_patterns:
    content = content.replace(old, new_pattern)

test_file.write_text(content)
print(f"Fixed {test_file}")
