
function opencode {
    & "C:\Users\GHC\.openclaw\workspace\free-code\cli.exe" -p --permission-mode bypassPermissions $args
}

function codex {
    # Giả sử codex dùng chung engine hoặc có engine riêng tại path này
    & "C:\Users\GHC\AppData\Roaming\npm\codex.ps1" $args
}

# Thông báo để Ly biết đã load thành công
Write-Host "V21_QUANT_ELITE: opencode & codex aliases loaded successfully."
