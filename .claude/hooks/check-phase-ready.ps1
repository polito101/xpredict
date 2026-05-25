# check-phase-ready.ps1
# Exit 1 blocks the PreToolUse tool call (create_pull_request).

$ErrorActionPreference = "Stop"

$phasesDir = ".planning\phases"

if (-not (Test-Path $phasesDir)) {
    Write-Error "ERROR: No .planning/phases directory. Are you in a GSD project root?"
    exit 1
}

# Active phase = most recently modified dir that has a PLAN.md
$activePhase = Get-ChildItem $phasesDir -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "PLAN.md") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $activePhase) {
    Write-Error "ERROR: No phase with PLAN.md found in .planning/phases/. Run /gsd-plan-phase first."
    exit 1
}

$verifyPath = Join-Path $activePhase.FullName "VERIFICATION.md"

if (-not (Test-Path $verifyPath)) {
    Write-Error "ERROR: VERIFICATION.md missing in phase '$($activePhase.Name)'. Run /gsd-verify-work first."
    exit 1
}

Write-Host "OK: Phase '$($activePhase.Name)' is ready for ship."
exit 0
