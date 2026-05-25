# linear-create-issue.ps1
# Triggered on PostToolUse Write. Creates a Linear issue when PLAN.md is first written.

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

# Read Write tool input from stdin (Claude Code sends JSON)
$rawInput = $null
try { $rawInput = [Console]::In.ReadToEnd() } catch {}

if (-not $rawInput) { exit 0 }

$toolInput = $rawInput | ConvertFrom-Json
$filePath  = $toolInput.file_path

# Only act on PLAN.md writes
if ($filePath -notmatch '\.planning[/\\]phases[/\\]([^/\\]+)[/\\]PLAN\.md$') {
    exit 0
}

$phaseName = $Matches[1]
$phaseDir  = ".planning\phases\$phaseName"
$issueFile = Join-Path $phaseDir ".linear-issue-id"

# Skip if issue already exists for this phase
if (Test-Path $issueFile) { exit 0 }

# Read first 500 chars of PLAN.md as description
$planContent = Get-Content (Join-Path $phaseDir "PLAN.md") -Raw
$description = if ($planContent.Length -gt 500) { $planContent.Substring(0, 500) + "..." } else { $planContent }
$descEscaped = $description -replace '\\', '\\\\' -replace '"', '\"' -replace "`n", '\n'

# Create issue via Linear GraphQL API
$mutation = "{`"query`": `"mutation { issueCreate(input: { title: \`"[$phaseName]\`", description: \`"$descEscaped\`", teamId: \`"$($env:LINEAR_TEAM_ID)\`", stateId: \`"$($env:LINEAR_IN_PROGRESS_STATE_ID)\`" }) { success issue { id identifier } } }`"}"

$response = Invoke-RestMethod `
    -Uri     "https://api.linear.app/graphql" `
    -Method  Post `
    -Headers @{
        "Authorization" = $env:LINEAR_API_KEY
        "Content-Type"  = "application/json"
    } `
    -Body $mutation

if ($response.data.issueCreate.success) {
    $identifier = $response.data.issueCreate.issue.identifier
    Set-Content -Path $issueFile -Value $identifier
    Write-Host "Linear issue created: $identifier for phase $phaseName"
} else {
    Write-Warning "Linear issue creation failed for phase $phaseName"
}
