$base = "c:\Users\GHC\repos\OMEGA_QUANT\src\omega\quant"

Write-Host "=== TOTAL PYTHON FILES ==="
$allFiles = Get-ChildItem -Path $base -Filter "*.py" -Recurse
Write-Host "Total .py files: $($allFiles.Count)"

Write-Host ""
Write-Host "=== ROOT .py FILES ==="
$rootFiles = Get-ChildItem -Path $base -Filter "*.py" -File
Write-Host "Root .py files: $($rootFiles.Count)"

Write-Host ""
Write-Host "=== SUBDIRECTORIES ==="
$dirs = Get-ChildItem -Path $base -Directory
foreach ($d in $dirs) {
    $count = (Get-ChildItem -Path $d.FullName -Filter "*.py" -Recurse -ErrorAction SilentlyContinue).Count
    if ($count -eq $null) { $count = 0 }
    Write-Host "  $($d.Name): $count files"
}

Write-Host ""
Write-Host "=== FILES > 20KB (sorted desc) ==="
$bigFiles = $allFiles | Where-Object { $_.Length -gt 20480 } | Sort-Object Length -Descending
foreach ($f in $bigFiles) {
    $kb = [math]::Round($f.Length / 1024, 1)
    $rel = $f.FullName.Replace($base + "\", "")
    Write-Host "  $kb KB - $rel"
}
Write-Host "Total files > 20KB: $($bigFiles.Count)"

Write-Host ""
Write-Host "=== DUPLICATE MODULE VERIFICATION ==="
$duplicates = @(
    @("ml_engine", "$base\ml_engine.py", "$base\ml\ml_engine.py"),
    @("neutralization", "$base\neutralization.py", "$base\features\neutralization.py"),
    @("alpha_factory", "$base\alpha_factory.py", "$base\alpha_factory_optimized.py"),
    @("portfolio_optimizer", "$base\portfolio_optimizer.py", "$base\portfolio\portfolio_optimizer.py"),
    @("signal_blender", "$base\signal_blender.py", "$base\walk_forward\signal_blender.py"),
    @("execution_sim", "$base\execution_sim.py", "$base\portfolio\execution_sim.py"),
    @("continuous_learning", "$base\continuous_learning.py", "$base\evolution\continuous_learning.py"),
    @("thompson_sampling", "$base\thompson_sampling.py", "$base\pipeline\overlays\thompson_sampling.py"),
    @("black_litterman", "$base\black_litterman.py", "$base\strategy\black_litterman.py"),
    @("drift_detector", "$base\drift_detector.py", "$base\evolution\drift_detector.py"),
    @("atomic_snapshot_manager", "$base\atomic_snapshot_manager.py", "$base\evolution\atomic_snapshot_manager.py")
)

foreach ($dup in $duplicates) {
    $name = $dup[0]
    $path1 = $dup[1]
    $path2 = $dup[2]
    $exists1 = Test-Path $path1
    $exists2 = Test-Path $path2
    $size1 = if ($exists1) { [math]::Round((Get-Item $path1).Length / 1024, 1) } else { "N/A" }
    $size2 = if ($exists2) { [math]::Round((Get-Item $path2).Length / 1024, 1) } else { "N/A" }
    $status = if ($exists1 -and $exists2) { "CONFIRMED" } elseif ($exists1 -or $exists2) { "PARTIAL" } else { "NOT FOUND" }
    Write-Host "  $name [$status]: $size1 KB vs $size2 KB"
}

# Check for additional duplicates
Write-Host ""
Write-Host "=== ADDITIONAL DUPLICATE CHECK (same filename in different dirs) ==="
$allNames = $allFiles | ForEach-Object { $_.Name } | Sort-Object
$grouped = $allNames | Group-Object | Where-Object { $_.Count -gt 1 }
foreach ($g in $grouped) {
    Write-Host "  $($g.Name): found $($g.Count) times"
}

Write-Host ""
Write-Host "=== ULTIMATE_ALPHA_ARSENAL VERIFICATION ==="
$uaa = Get-Item "$base\ultimate_alpha_arsenal.py"
Write-Host "  Size: $([math]::Round($uaa.Length / 1024, 1)) KB"
Write-Host "  Lines: $((Get-Content $uaa.FullName).Count)"

Write-Host ""
Write-Host "=== TESTS DIRECTORY ==="
$testsDir = "c:\Users\GHC\repos\OMEGA_QUANT\tests"
if (Test-Path $testsDir) {
    $testFiles = Get-ChildItem -Path $testsDir -Filter "*.py" -Recurse
    Write-Host "  Test files: $($testFiles.Count)"
    foreach ($t in $testFiles) {
        $rel = $t.FullName.Replace($testsDir + "\", "")
        Write-Host "    $rel ($([math]::Round($t.Length / 1024, 1)) KB)"
    }
} else {
    Write-Host "  tests/ directory NOT FOUND"
}

Write-Host ""
Write-Host "=== CONFIG FILES CHECK ==="
$configs = @(
    "c:\Users\GHC\repos\OMEGA_QUANT\setup.cfg",
    "c:\Users\GHC\repos\OMEGA_QUANT\pytest.ini",
    "c:\Users\GHC\repos\OMEGA_QUANT\conftest.py",
    "c:\Users\GHC\repos\OMEGA_QUANT\setup.py",
    "c:\Users\GHC\repos\OMEGA_QUANT\pyproject.toml"
)
foreach ($c in $configs) {
    if (Test-Path $c) {
        Write-Host "  EXISTS: $(Split-Path $c -Leaf) ($([math]::Round((Get-Item $c).Length, 0)) bytes)"
    } else {
        Write-Host "  MISSING: $(Split-Path $c -Leaf)"
    }
}

Write-Host ""
Write-Host "=== CROSS-MODULE IMPORTS (top 20 most imported) ==="
$importPattern = "from omega\.quant\.(\w+) import|from \.(\w+) import|import omega\.quant\.(\w+)"
$allImports = @{}
foreach ($f in $allFiles) {
    $content = Get-Content $f.FullName -ErrorAction SilentlyContinue
    foreach ($line in $content) {
        if ($line -match "from \.(\w+) import") {
            $mod = $Matches[1]
            if (-not $allImports.ContainsKey($mod)) { $allImports[$mod] = 0 }
            $allImports[$mod]++
        }
    }
}
$sorted = $allImports.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 20
foreach ($s in $sorted) {
    Write-Host "  $($s.Key): imported $($s.Value) times"
}

Write-Host ""
Write-Host "=== CIRCULAR DEPENDENCY CHECK ==="
Write-Host "Checking for modules that import each other..."
$circularPairs = @()
foreach ($f in $rootFiles) {
    $modName = $f.BaseName
    $content = Get-Content $f.FullName -ErrorAction SilentlyContinue
    foreach ($line in $content) {
        if ($line -match "from \.(\w+) import") {
            $importedMod = $Matches[1]
            $importedFile = "$base\$importedMod.py"
            if (Test-Path $importedFile) {
                $importedContent = Get-Content $importedFile -ErrorAction SilentlyContinue
                foreach ($iLine in $importedContent) {
                    if ($iLine -match "from \.$modName import") {
                        $pair = @($modName, $importedMod) | Sort-Object
                        $pairKey = "$($pair[0]) <-> $($pair[1])"
                        if ($circularPairs -notcontains $pairKey) {
                            $circularPairs += $pairKey
                            Write-Host "  CIRCULAR: $pairKey"
                        }
                    }
                }
            }
        }
    }
}
if ($circularPairs.Count -eq 0) {
    Write-Host "  No circular dependencies found in root files."
}
