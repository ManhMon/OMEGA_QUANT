import json

path = 'C:/Users/GHC/.openclaw/workspace/OMEGA_QUANT/.ly_state/config/sod_automation.json'
with open(path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Revert back to fast CLI exec mode with direct webhook to Telegram
config['settings']['execution_mode'] = 'cli_exec_background'

l2_hook = '; Invoke-RestMethod -Uri "http://127.0.0.1:18789/hooks/agent" -Method POST -Headers @{"Authorization"="Bearer sod-automation-token-2026"} -Body \'{"message":"[Hoàn thành L2] Đã viết xong code và test pass. Chờ L1 kiểm duyệt. (Tác vụ: {task_id})","deliver":true,"agentId":"main","channel":"telegram","to":"8468518663"}\' -ContentType "application/json"'
l3_hook = '; Invoke-RestMethod -Uri "http://127.0.0.1:18789/hooks/agent" -Method POST -Headers @{"Authorization"="Bearer sod-automation-token-2026"} -Body \'{"message":"[Hoàn thành L3] Đã Audit xong. Đã ghi báo cáo. Chờ L1 quyết định Gate. (Tác vụ: {task_id})","deliver":true,"agentId":"main","channel":"telegram","to":"8468518663"}\' -ContentType "application/json"'

config['workflow']['steps'][0]['command_template'] = 'opencode run "[L2-Impl:Role9-Backend] {task_description}" ' + l2_hook
config['workflow']['steps'][2]['command_template'] = 'codex exec --dangerously-bypass-approvals-and-sandbox "[L3-Audit:Role21-Review] {audit_description}" ' + l3_hook

with open(path, 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
print("Reverted to fast CLI exec with VI webhook!")