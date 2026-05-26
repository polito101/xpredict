# linear-to-review.ps1
# PostToolUse(create_pull_request): move the active phase's Linear issue to "In Review".
# Linear is OPTIONAL — this hook never blocks work and never errors out the session.

function Import-EnvFile($path) {
    if (Test-Path $path) {
        Get-Content $path | Where-Object { $_ -match "^\s*[^#]" } | ForEach-Object {
            $parts = $_ -split "=", 2
            if ($parts.Count -eq 2) {
                [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
            }
        }
    }
}
Import-EnvFile (Join-Path (Get-Location) ".claude/linear.shared.env")
Import-EnvFile (Join-Path (Get-Location) ".env.local")

# Find active phase (most recently modified dir with any *-PLAN.md file)
$phasesDir = ".planning\phases"
if (-not (Test-Path $phasesDir)) { exit 0 }
$activePhase = Get-ChildItem $phasesDir -Directory |
    Where-Object { (Get-ChildItem $_.FullName -Filter "*PLAN.md" -ErrorAction SilentlyContinue).Count -gt 0 } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $activePhase) {
    Write-Host "No active phase found - skipping Linear update."
    exit 0
}

$issueFile = Join-Path $activePhase.FullName ".linear-issue-id"
if (-not (Test-Path $issueFile)) {
    Write-Host "No Linear issue ID for phase '$($activePhase.Name)' - skipping."
    exit 0
}

# Linear is optional: skip cleanly if not configured (never error the session)
if (-not $env:LINEAR_API_KEY -or -not $env:LINEAR_IN_REVIEW_STATE_ID) {
    Write-Host "Linear not configured - skipping move to In Review."
    exit 0
}

$identifier = (Get-Content $issueFile -Raw).Trim()

try {
    # Fetch issue UUID from identifier (Linear requires UUID for mutations)
    $queryBody = "{`"query`": `"query { issues(filter: { identifier: { eq: \`"$identifier\`" } }) { nodes { id } } }`"}"
    $queryResp = Invoke-RestMethod `
        -Uri     "https://api.linear.app/graphql" `
        -Method  Post `
        -Headers @{ "Authorization" = $env:LINEAR_API_KEY; "Content-Type" = "application/json" } `
        -Body    $queryBody
    $uuid = $queryResp.data.issues.nodes[0].id
    if (-not $uuid) {
        Write-Warning "Could not find Linear issue UUID for $identifier (continuing)."
        exit 0
    }

    # Move to In Review
    $mutBody = "{`"query`": `"mutation { issueUpdate(id: \`"$uuid\`", input: { stateId: \`"$($env:LINEAR_IN_REVIEW_STATE_ID)\`" }) { success issue { identifier state { name } } } }`"}"
    $mutResp = Invoke-RestMethod `
        -Uri     "https://api.linear.app/graphql" `
        -Method  Post `
        -Headers @{ "Authorization" = $env:LINEAR_API_KEY; "Content-Type" = "application/json" } `
        -Body    $mutBody
    if ($mutResp.data.issueUpdate.success) {
        Write-Host "Linear: $identifier moved to In Review"
    } else {
        Write-Warning "Failed to move $identifier to In Review (continuing)."
    }
} catch {
    Write-Warning "Linear update failed for $identifier (continuing): $($_.Exception.Message)"
}
exit 0
