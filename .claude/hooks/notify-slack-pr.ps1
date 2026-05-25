# notify-slack-pr.ps1
# Reads PLAN.md, calls Anthropic API for AI summary, posts to Slack #prs.

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
    Write-Warning "No active phase found. Skipping Slack notification."
    exit 0
}

$planContent = Get-Content (Join-Path $activePhase.FullName "PLAN.md") -Raw
$phaseName   = $activePhase.Name

# Get PR info via gh CLI
$prNumber = (gh pr list --state open --json number --jq ".[0].number" 2>&1).Trim()
$prUrl    = (gh pr list --state open --json url    --jq ".[0].url"    2>&1).Trim()

if (-not $prNumber) {
    Write-Warning "No open PR found. Skipping Slack notification."
    exit 0
}

$rawDiff = (gh pr diff $prNumber 2>&1) -join "`n"
$diff = if ($rawDiff.Length -gt 3000) { $rawDiff.Substring(0, 3000) + "`n...(truncated)" } else { $rawDiff }

# Call Anthropic API for AI summary
$prompt = @"
You are reviewing a pull request against a PLAN.md.

PLAN.MD:
$planContent

PR DIFF (may be truncated):
$diff

Reply in this EXACT format, nothing else:
MEETS_OBJECTIVE: YES or NO
SUMMARY: One sentence (max 120 chars) — what was implemented and whether it meets the plan objectives.
"@

$apiBody = @{
    model      = "claude-haiku-4-5-20251001"
    max_tokens = 200
    messages   = @(@{ role = "user"; content = $prompt })
} | ConvertTo-Json -Depth 5

$apiResponse = Invoke-RestMethod `
    -Uri     "https://api.anthropic.com/v1/messages" `
    -Method  Post `
    -Headers @{
        "x-api-key"         = $env:ANTHROPIC_API_KEY
        "anthropic-version" = "2023-06-01"
        "content-type"      = "application/json"
    } `
    -Body $apiBody

$aiText         = $apiResponse.content[0].text
$meetsObjective = if ($aiText -match "MEETS_OBJECTIVE:\s*(YES|NO)") { $Matches[1] } else { "?" }
$summary        = if ($aiText -match "SUMMARY:\s*(.+)")             { $Matches[1].Trim() } else { "See PR for details." }
$emoji          = if ($meetsObjective -eq "YES") { ":white_check_mark:" } else { ":warning:" }

# Get Linear issue URL if available
$linearUrl = ""
$issueFile = Join-Path $activePhase.FullName ".linear-issue-id"
if (Test-Path $issueFile) {
    $issueId   = (Get-Content $issueFile -Raw).Trim()
    $linearUrl = " | <https://linear.app/issue/$issueId|Linear issue>"
}

# Post to Slack
$slackText = ":twisted_rightwards_arrows: *PR ready for review — $phaseName*`n`nMeets objective? $emoji $meetsObjective`nSummary: $summary`n`n<$prUrl|View PR>$linearUrl"
$slackBody = @{ text = $slackText } | ConvertTo-Json

Invoke-RestMethod `
    -Uri         $env:SLACK_WEBHOOK_URL `
    -Method      Post `
    -Body        $slackBody `
    -ContentType "application/json"

Write-Host "Slack notification sent for PR #$prNumber ($phaseName)"
