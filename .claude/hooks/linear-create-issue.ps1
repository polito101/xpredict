# linear-create-issue.ps1
# PostToolUse(Write): when a phase PLAN.md is first written, create a Linear issue.
# Linear is OPTIONAL — this hook never blocks work and never errors out the session.

# Read Write tool input from stdin (Claude Code sends JSON)
$rawInput = $null
try { $rawInput = [Console]::In.ReadToEnd() } catch {}
if (-not $rawInput) { exit 0 }

try { $toolInput = $rawInput | ConvertFrom-Json } catch { exit 0 }
$filePath = $toolInput.file_path

# Only act on PLAN.md writes
if ($filePath -notmatch '\.planning[/\\]phases[/\\]([^/\\]+)[/\\]PLAN\.md$') { exit 0 }

$phaseName = $Matches[1]
$phaseDir  = ".planning\phases\$phaseName"
$issueFile = Join-Path $phaseDir ".linear-issue-id"

# Skip if issue already exists for this phase
if (Test-Path $issueFile) { exit 0 }

# Load env: shared non-secret IDs first, then personal .env.local
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

# Linear is optional: skip cleanly if not configured (never error the session)
if (-not $env:LINEAR_API_KEY -or -not $env:LINEAR_TEAM_ID -or -not $env:LINEAR_IN_PROGRESS_STATE_ID) {
    Write-Host "Linear not configured - skipping issue creation for $phaseName."
    exit 0
}

# Read first 500 chars of PLAN.md as description
$planContent = Get-Content (Join-Path $phaseDir "PLAN.md") -Raw
$description = if ($planContent.Length -gt 500) { $planContent.Substring(0, 500) + "..." } else { $planContent }
$descEscaped = $description -replace '\\', '\\\\' -replace '"', '\"' -replace "`n", '\n'

# Create issue via Linear GraphQL API (best-effort: never break the session)
$mutation = "{`"query`": `"mutation { issueCreate(input: { title: \`"[$phaseName]\`", description: \`"$descEscaped\`", teamId: \`"$($env:LINEAR_TEAM_ID)\`", stateId: \`"$($env:LINEAR_IN_PROGRESS_STATE_ID)\`" }) { success issue { id identifier } } }`"}"

try {
    $response = Invoke-RestMethod `
        -Uri     "https://api.linear.app/graphql" `
        -Method  Post `
        -Headers @{ "Authorization" = $env:LINEAR_API_KEY; "Content-Type" = "application/json" } `
        -Body    $mutation
    if ($response.data.issueCreate.success) {
        $identifier = $response.data.issueCreate.issue.identifier
        Set-Content -Path $issueFile -Value $identifier
        Write-Host "Linear issue created: $identifier for phase $phaseName"
    } else {
        Write-Warning "Linear issueCreate returned no success for $phaseName (continuing)."
    }
} catch {
    Write-Warning "Linear issue creation failed for $phaseName (continuing): $($_.Exception.Message)"
}
exit 0
