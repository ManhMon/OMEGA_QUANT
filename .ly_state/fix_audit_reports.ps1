$section = @'


## Repo-Local Files Read

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
'@

$files = @(
  ".ly_state\session\audit_reports\role21_gp_threads_parallel_20260717.md",
  ".ly_state\session\audit_reports\role21_gp_numba_eval_vectorize_20260717.md"
)

foreach ($f in $files) {
  $c = Get-Content $f -Raw -Encoding utf8
  if ($c -inotmatch "repo-local files read") {
    $newContent = $c.TrimEnd() + $section
    [System.IO.File]::WriteAllText($f, $newContent, [System.Text.Encoding]::UTF8)
    Write-Host "Fixed: $f"
  } else {
    Write-Host "Skip (already has section): $f"
  }
}
