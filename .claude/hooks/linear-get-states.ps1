# linear-get-states.ps1
# Run once to find your team's workflow state IDs for .env.local

param([string]$TeamId = $env:LINEAR_TEAM_ID)

$envFile = Join-Path (Get-Location) ".env.local"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match "^\s*[^#]" } | ForEach-Object {
        $parts = $_ -split "=", 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
        }
    }
}

if (-not $TeamId) {
    Write-Error "Set LINEAR_TEAM_ID in .env.local or pass as -TeamId"
    exit 1
}

$query = "{`"query`": `"query { team(id: \`"$TeamId\`") { states { nodes { id name } } } }`"}"

$response = Invoke-RestMethod `
    -Uri     "https://api.linear.app/graphql" `
    -Method  Post `
    -Headers @{ "Authorization" = $env:LINEAR_API_KEY; "Content-Type" = "application/json" } `
    -Body    $query

Write-Host "`nWorkflow states for team $TeamId:"
$response.data.team.states.nodes | ForEach-Object {
    Write-Host "  $($_.name): $($_.id)"
}
Write-Host "`nCopy the relevant IDs to your .env.local"
