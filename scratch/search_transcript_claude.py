import json
from pathlib import Path

transcript_path = Path("C:/Users/GHC/.gemini/antigravity-ide/brain/f4b2147f-efca-4050-8632-2ddcd209f4fc/.system_generated/logs/transcript.jsonl")

if transcript_path.exists():
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            if "claude" in line.lower():
                try:
                    data = json.loads(line)
                    # print step_index, type, content, tool_calls
                    print(f"Step {data.get('step_index')}: type={data.get('type')}")
                    if "tool_calls" in data:
                        for tc in data["tool_calls"]:
                            print(f"  Tool: {tc.get('name')}")
                            print(f"  Args: {tc.get('args')}")
                except Exception as e:
                    print(f"Error parsing line: {e}")
else:
    print("Transcript not found")
