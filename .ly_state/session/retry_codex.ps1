
$maxRetries = 20
$retryCount = 0
$success = $false
while ($retryCount -lt $maxRetries) {
    Write-Host "Attempting Codex execution ($retryCount)..."
    $output = cmd /c "type .ly_state\session\prompt_l3_plan_fix_v12.txt | codex exec -m cx/gpt-5.6-sol(max) -s danger-full-access --dangerously-bypass-approvals-and-sandbox" 2>&1
    Write-Host $output
    if ($LASTEXITCODE -eq 0 -and $output -notmatch "429 Too Many Requests") {
        Write-Host "Success!"
        $success = $true
        break
    }
    Write-Host "Failed with 429. Waiting 60 seconds..."
    Start-Sleep -Seconds 60
    $retryCount++
}
if (-not $success) { exit 1 }

