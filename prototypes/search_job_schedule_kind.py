from pathlib import Path

path = Path(r"C:\Users\GHC\AppData\Roaming\npm\node_modules\openclaw\dist\server-cron-C6BmZ1gR.js")
content = path.read_text(encoding="utf-8", errors="ignore")

lines = content.split("\n")
for i, line in enumerate(lines):
    if "job.schedule.kind" in line or "j.schedule.kind" in line:
        print(f"Line {i}: {line[:120]}")
