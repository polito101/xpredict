# linear-to-review.ps1
# Moves Linear issue to In Review when PR is opened.

$ErrorActionPreference = "Stop"

# Load .env.local if present
$envFile = Join-Path (Get-Location) ".env.local"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match "^\s*[^#]" } | ForEach-Object {
        $parts = $_ -split "=", 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
        }
    }
}

# Find active phase
$phasesDir = ".planning\phases"
$activePhase = Get-ChildItem $phasesDir -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "PLAN.md") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $activePhase) {
    Write-Warning "No active phase found. Skipping Linear update."
    exit 0
}

$issueFile = Join-Path $activePhase.FullName ".linear-issue-id"
if (-not (Test-Path $issueFile)) {
    Write-Warning "No Linear issue ID for phase '$($activePhase.Name)'. Skipping."
    exit 0
}

$identifier = (Get-Content $issueFile -Raw).Trim()

# Fetch issue UUID from identifier (Linear requires UUID for mutations)
$queryBody = "{`"query`": `"query { issues(filter: { identifier: { eq: \`"$identifier\`" } }) { nodes { id } } }`"}"

$queryResp = Invoke-RestMethod `
    -Uri     "https://api.linear.app/graphql" `
    -Method  Post `
    -Headers @{ "Authorization" = $env:LINEAR_API_KEY; "Content-Type" = "application/json" } `
    -Body    $queryBody

$uuid = $queryResp.data.issues.nodes[0].id

if (-not $uuid) {
    Write-Warning "Could not find Linear issue UUID for $identifier. Skipping."
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
    Write-Warning "Failed to move $identifier to In Review"
}
