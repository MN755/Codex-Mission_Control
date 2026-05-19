param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [switch]$TryStartDaemon = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeRoot = if ($env:MISSION_CONTROL_RUNTIME_ROOT) {
  $env:MISSION_CONTROL_RUNTIME_ROOT
} else {
  Join-Path $repoRoot "apps\server\.runtime"
}
$baseUri = [Uri]$BaseUrl
$daemonHost = $baseUri.Host
$daemonPort = $baseUri.Port
$tokenPath = Join-Path $runtimeRoot "daemon.token"
$workspaceRoot = Join-Path $runtimeRoot "smoke-headless-happy-path"
$workspacePath = Join-Path $workspaceRoot ("repo-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

function Test-Health {
  try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 2
    return $response.status -eq "ok"
  } catch {
    return $false
  }
}

function Invoke-Json {
  param(
    [ValidateSet("GET", "POST", "PUT")]
    [string]$Method,
    [string]$Url,
    [hashtable]$Headers = @{},
    $Body = $null
  )
  if ($null -eq $Body) {
    return Invoke-RestMethod -Uri $Url -Method $Method -Headers $Headers -TimeoutSec 15
  }
  $json = $Body | ConvertTo-Json -Depth 10
  return Invoke-RestMethod -Uri $Url -Method $Method -Headers $Headers -ContentType "application/json" -Body $json -TimeoutSec 15
}

function Wait-ForToken {
  for ($index = 0; $index -lt 40; $index += 1) {
    if (Test-Path $tokenPath) {
      return
    }
    Start-Sleep -Milliseconds 500
  }
  throw "Mission Control daemon token was not found at $tokenPath"
}

if (-not (Test-Health)) {
  if (-not $TryStartDaemon) {
    throw "Mission Control daemon is not healthy at $BaseUrl and auto-start is disabled."
  }
  & (Join-Path $PSScriptRoot "start-mission-control-daemon.ps1") -BackendPort $daemonPort -BindHost $daemonHost
}

Wait-ForToken
$bridgeHeaders = @{
  "X-Mission-Control-Token" = (Get-Content -Raw $tokenPath).Trim()
}

$null = New-Item -ItemType Directory -Path $workspacePath -Force
$null = New-Item -ItemType Directory -Path (Join-Path $workspacePath "tests") -Force
Set-Content -Path (Join-Path $workspacePath "README.md") -Value "# Smoke repo`n" -Encoding UTF8
Set-Content -Path (Join-Path $workspacePath "tests\test_smoke.py") -Value "def test_smoke():`n    assert True`n" -Encoding UTF8

$attach = Invoke-Json -Method POST -Url "$BaseUrl/api/orchestrations/attach-workspace" -Headers $bridgeHeaders -Body @{
  workspace_path   = $workspacePath.Replace("\", "/")
  project_name     = "Headless Smoke"
  mode             = "existing_codebase"
  read_only_first  = $true
  attach_policy    = "reuse_existing"
}
$projectId = [int]$attach.project.id

$settings = Invoke-Json -Method GET -Url "$BaseUrl/api/settings?project_id=$projectId"
$settings.runner_mode = "dry_run"
$null = Invoke-Json -Method PUT -Url "$BaseUrl/api/settings?project_id=$projectId" -Body $settings
$null = Invoke-Json -Method POST -Url "$BaseUrl/api/projects/$projectId/open"

$orchestration = Invoke-Json -Method POST -Url "$BaseUrl/api/orchestrations" -Headers $bridgeHeaders -Body @{
  project_id    = $projectId
  user_request  = "Use Mission Control for this repo and fix the failing tests."
  source        = "codex_plugin"
}
$orchestrationId = [int]$orchestration.id

for ($index = 0; $index -lt 20; $index += 1) {
  $pending = Invoke-Json -Method GET -Url "$BaseUrl/api/orchestrations/$orchestrationId/pending-decisions" -Headers $bridgeHeaders
  if ($pending.Count -gt 0) {
    break
  }
  Start-Sleep -Milliseconds 500
}

$statusSummary = Invoke-Json -Method GET -Url "$BaseUrl/api/orchestrations/$orchestrationId/status-summary" -Headers $bridgeHeaders
Write-Host ""
Write-Host "===== STATUS SUMMARY ====="
Write-Host $statusSummary.fallback_markdown

$pending = Invoke-Json -Method GET -Url "$BaseUrl/api/orchestrations/$orchestrationId/pending-decisions" -Headers $bridgeHeaders
for ($attempt = 0; $attempt -lt 3; $attempt += 1) {
  if (-not $pending -or $pending.Count -eq 0) {
    break
  }
  $decision = $pending | Where-Object { $_.decision_type -eq "command_approval" } | Select-Object -First 1
  if (-not $decision) {
    $decision = $pending | Select-Object -First 1
  }
  $bridgeMessage = Invoke-Json -Method GET -Url "$BaseUrl/api/decisions/$($decision.id)/bridge-message" -Headers $bridgeHeaders
  Write-Host ""
  Write-Host "===== PENDING DECISION ====="
  Write-Host $bridgeMessage.fallback_markdown
  $recommended = if ($decision.recommended_option) {
    $decision.options | Where-Object { $_.id -eq $decision.recommended_option } | Select-Object -First 1
  } else {
    $null
  }
  $selected = if ($recommended) { $recommended } else { $decision.options | Select-Object -First 1 }
  if (-not $selected) {
    break
  }
  $answered = Invoke-Json -Method POST -Url "$BaseUrl/api/decisions/$($decision.id)/answer" -Headers $bridgeHeaders -Body @{
    option_id     = $selected.id
    selected_text = $selected.label
  }
  Write-Host ""
  Write-Host "===== NEXT STATUS ====="
  Write-Host $answered.next_status_summary.fallback_markdown
  if (-not $answered.next_status_summary.user_action_required) {
    break
  }
  $pending = Invoke-Json -Method GET -Url "$BaseUrl/api/orchestrations/$orchestrationId/pending-decisions" -Headers $bridgeHeaders
}

$digest = Invoke-Json -Method GET -Url "$BaseUrl/api/orchestrations/$orchestrationId/event-digest?window=since_orchestration_start" -Headers $bridgeHeaders
Write-Host ""
Write-Host "===== EVENT DIGEST ====="
Write-Host $digest.fallback_markdown

$null = Invoke-Json -Method POST -Url "$BaseUrl/api/projects/$projectId/handoff/generate" -Headers $bridgeHeaders
$handoff = Invoke-Json -Method GET -Url "$BaseUrl/api/orchestrations/$orchestrationId/handoff-summary" -Headers $bridgeHeaders
Write-Host ""
Write-Host "===== HANDOFF SUMMARY ====="
Write-Host $handoff.fallback_markdown
