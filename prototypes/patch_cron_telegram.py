import json
from pathlib import Path

sessions_file = Path(r"C:\Users\GHC\.openclaw\agents\main\sessions\sessions.json")
if sessions_file.exists():
    data = json.loads(sessions_file.read_text(encoding="utf-8"))
    cron_key = "agent:main:cron:72e8ac1d-5067-4096-a93d-f38bc07dec16"
    
    if cron_key in data:
        print("Original key keys:", list(data[cron_key].keys()))
        # Patch delivery context to target telegram:8468518663
        data[cron_key]["deliveryContext"] = {
            "channel": "telegram",
            "to": "8468518663",
            "chatId": "telegram:8468518663"
        }
        data[cron_key]["lastChannel"] = "telegram"
        data[cron_key]["channel"] = "telegram"
        data[cron_key]["chatId"] = "telegram:8468518663"
        
        # Also write the updated sessions.json back safely
        backup_file = sessions_file.with_suffix(".json.patch.bak")
        backup_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        sessions_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("Successfully patched sessions.json with Telegram delivery context!")
    else:
        print("Cron key not found!")
else:
    print("sessions.json does not exist!")
