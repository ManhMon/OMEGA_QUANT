# Task: Fix PermissionError in test_record_dashboard_gate.py

We need to fix the Windows PermissionError in `tests/test_record_dashboard_gate.py` that occurs in L3 sandbox environment.

## Problem
`tempfile.mkdtemp()` creates directories with restrictive mode 0o700, which on Windows L3 environment causes PermissionError during `os.chdir` or `shutil.rmtree`.

## Solution
Change `setUp` in `tests/test_record_dashboard_gate.py` to generate a unique subdirectory path under `tempfile.gettempdir()` using `uuid.uuid4().hex` and create it using `os.makedirs()` (which inherits parent ACL permissions correctly).
Also update `tearDown` to use a permission-safe rmtree cleanup.

### Code Modification details for `tests/test_record_dashboard_gate.py`:

Modify `setUp`:
```python
    def setUp(self):
        """Set up test fixtures"""
        import uuid
        self.test_dir = os.path.join(tempfile.gettempdir(), f"tmp_gate_test_{uuid.uuid4().hex}")
        os.makedirs(self.test_dir, exist_ok=True)
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
```

Modify `tearDown`:
```python
    def tearDown(self):
        """Clean up test fixtures"""
        os.chdir(self.original_dir)
        if os.path.exists(self.test_dir):
            import shutil
            import stat
            def _onerror(func, path, exc_info):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass
            shutil.rmtree(self.test_dir, onerror=_onerror)
```

Verify the fix by running:
`python -m pytest tests/test_record_dashboard_gate.py -vv`
Write your L2 report to `.ly_state/session/l2_role14_drawdown_adaptive_re_entry_20260616.md` (overwriting it or updating it, keeping all other contents about STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616).
