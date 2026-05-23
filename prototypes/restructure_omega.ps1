# OMEGA Restructure Script
# Move OMEGA project into omega/ subdirectory

Write-Host "Creating omega/ directory structure..."
New-Item -ItemType Directory -Force -Path "omega" | Out-Null
New-Item -ItemType Directory -Force -Path "omega/prototypes" | Out-Null

Write-Host "Moving core OMEGA directories..."
$coreDirs = @('packages', 'tests', 'scripts', 'data', 'docs', '.ly_state', 'apps', 'config', 'models')
foreach ($dir in $coreDirs) {
    if (Test-Path $dir) {
        Write-Host "  Moving $dir -> omega/$dir"
        Move-Item -Path $dir -Destination "omega/" -Force
    }
}

Write-Host "Moving prototypes..."
if (Test-Path "prototypes") {
    Get-ChildItem -Path "prototypes" | Move-Item -Destination "omega/prototypes/" -Force
    Remove-Item "prototypes" -Force
}

Write-Host "Cleaning up root junk scripts..."
$preserveRootFiles = @('SOUL.md', 'AGENTS.md', 'TOOLS.md', 'USER.md', 'MEMORY.md', 'HEARTBEAT.md', 'IDENTITY.md', '.gitignore', 'pyproject.toml')

Get-ChildItem -File -Path . | Where-Object {
    $preserveRootFiles -notcontains $_.Name
} | ForEach-Object {
    Write-Host "  Moving $($_.Name) -> omega/prototypes/"
    Move-Item -Path $_.FullName -Destination "omega/prototypes/" -Force
}

Write-Host "Restructure complete!"
Write-Host "OMEGA project now in: omega/"
Write-Host "Workspace root preserved files: $($preserveRootFiles -join ', ')"
