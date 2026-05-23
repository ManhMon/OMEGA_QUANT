$token = 'mul_a671b58cad9bcbafcbbc57a19c4770075e80190a'
$workspace_id = 'ea1c24d6-a3c4-4e26-bb7e-be774ceaf154'
$repo_url = 'https://github.com/ManhMon/V21_QUANT'

$headers = @{
    'Authorization' = "Bearer $token"
    'Content-Type' = 'application/json'
}

$body = @{
    'url' = $repo_url
} | ConvertTo-Json

Write-Host "Trying to add repo to workspace..."
Write-Host "URL: https://api.multica.ai/api/workspaces/$workspace_id/repos"
Write-Host "Body: $body"

try {
    $response = Invoke-RestMethod -Uri "https://api.multica.ai/api/workspaces/$workspace_id/repos" -Method POST -Headers $headers -Body $body
    Write-Host "Success!"
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $_"
    Write-Host "Response: $_.Exception.Response"
}
