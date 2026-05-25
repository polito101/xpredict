# linear-get-states.ps1
# Manual utility (run once) to discover a team's Linear workflow state IDs:
#   powershell -File .claude/hooks/linear-get-states.ps1
# Loads shared IDs then personal .env.local. Needs LINEAR_API_KEY (+ a team id).

param([string]$TeamId)

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

if (-not $TeamId) { $TeamId = $env:LINEAR_TEAM_ID }

if (-not $env:LINEAR_API_KEY) {
    Write-Error "Set LINEAR_API_KEY in .env.local first."
    exit 1
}
if (-not $TeamId) {
    Write-Error "Set LINEAR_TEAM_ID (in .claude/linear.shared.env or .env.local) or pass -TeamId."
    exit 1
}

$query = "{`"query`": `"query { team(id: \`"$TeamId\`") { states { nodes { id name } } } }`"}"

$response = Invoke-RestMethod `
    -Uri     "https://api.linear.app/graphql" `
    -Method  Post `
    -Headers @{ "Authorization" = $env:LINEAR_API_KEY; "Content-Type" = "application/json" } `
    -Body    $query

Write-Host "`nWorkflow states for team ${TeamId}:"
$response.data.team.states.nodes | ForEach-Object {
    Write-Host "  $($_.name): $($_.id)"
}
Write-Host "`nCopy the relevant IDs to .claude/linear.shared.env"
