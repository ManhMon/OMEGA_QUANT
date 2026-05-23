$pathsToAdd = @(
  "C:\Users\GHC\AppData\Roaming\npm",
  "C:\Users\GHC\.multica\bin"
)

$current = [Environment]::GetEnvironmentVariable("Path", "User")
foreach ($p in $pathsToAdd) {
  if ($current -notlike "*$p*") {
    $current = "$current;$p"
  }
}

[Environment]::SetEnvironmentVariable("Path", $current, "User")
Write-Host "Updated User PATH. Close/reopen terminals to apply."
