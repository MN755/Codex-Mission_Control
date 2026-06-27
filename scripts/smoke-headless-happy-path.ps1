param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [switch]$TryStartDaemon = $true,
  [string]$WorkspaceRoot = "",
  [string]$TranscriptPath = "",
  [ValidateSet("dry_run", "auto", "codex_cli")]
  [string]$TaskMode = "dry_run"
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
$workspaceRoot = if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
  Join-Path ([System.IO.Path]::GetTempPath()) "mission-control-smoke-headless-happy-path"
} else {
  $WorkspaceRoot
}
$workspacePath = Join-Path $workspaceRoot ("repo-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$transcriptSections = New-Object System.Collections.Generic.List[string]

function Add-TranscriptSection {
  param(
    [string]$Title,
    [string]$Content
  )
  $section = @(
    "## $Title",
    "",
    '```text',
    $Content,
    '```'
  ) -join "`n"
  $null = $transcriptSections.Add($section)
}

function Write-Section {
  param(
    [string]$Title,
    [string]$Content
  )
  Write-Host ""
  Write-Host "===== $Title ====="
  Write-Host $Content
  Add-TranscriptSection -Title $Title -Content $Content
}

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

function Get-ApiUrl {
  param(
    [string]$Path,
    [hashtable]$Query = @{}
  )
  if (-not $Query -or $Query.Count -eq 0) {
    return "$BaseUrl$Path"
  }
  $pairs = foreach ($key in $Query.Keys) {
    $encodedKey = [Uri]::EscapeDataString([string]$key)
    $encodedValue = [Uri]::EscapeDataString([string]$Query[$key])
    "$encodedKey=$encodedValue"
  }
  return "${BaseUrl}${Path}?$(($pairs -join '&'))"
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

$attach = Invoke-Json -Method POST -Url (Get-ApiUrl -Path "/api/headless/attach-workspace") -Headers $bridgeHeaders -Body @{
  workspace_path   = $workspacePath.Replace("\", "/")
  project_name     = (Split-Path -Leaf $workspacePath)
  mode             = "existing_codebase"
  read_only_first  = $true
  attach_policy    = "reuse_existing"
}
$projectId = [int]$attach.project.id

$start = Invoke-Json -Method POST -Url (Get-ApiUrl -Path "/api/headless/start-task") -Headers $bridgeHeaders -Body @{
  project_id       = $projectId
  user_request     = "Use Mission Control for this repo and fix the failing tests."
  strategy         = "balanced"
  mode             = $TaskMode
  interview_mode   = "skip"
  attach_policy    = "reuse_existing"
}

$orchestration = $start.orchestration
$orchestrationId = [int]$orchestration.id
$pending = @($start.pending_decisions)

Write-Section -Title "ATTACH WORKSPACE" -Content ($attach | ConvertTo-Json -Depth 6)
Write-Section -Title "START TASK" -Content ($orchestration | ConvertTo-Json -Depth 6)
Write-Section -Title "STATUS SUMMARY" -Content $start.status_summary.fallback_markdown

for ($attempt = 0; $attempt -lt 3; $attempt += 1) {
  if (-not $pending -or $pending.Count -eq 0) {
    break
  }
  $decision = $pending | Where-Object { $_.decision_type -eq "command_approval" } | Select-Object -First 1
  if (-not $decision) {
    $decision = $pending | Select-Object -First 1
  }
  $bridgeMessage = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/decisions/$($decision.id)/bridge-message" -Query @{ project_id = $projectId }) -Headers $bridgeHeaders
  Write-Section -Title "PENDING DECISION" -Content $bridgeMessage.fallback_markdown
  $recommended = if ($decision.recommended_option) {
    $decision.options | Where-Object { $_.id -eq $decision.recommended_option } | Select-Object -First 1
  } else {
    $null
  }
  $selected = if ($recommended) { $recommended } else { $decision.options | Select-Object -First 1 }
  if (-not $selected) {
    break
  }
  $answered = Invoke-Json -Method POST -Url (Get-ApiUrl -Path "/api/decisions/$($decision.id)/answer" -Query @{ project_id = $projectId }) -Headers $bridgeHeaders -Body @{
    option_id     = $selected.id
    selected_text = $selected.label
  }
  Write-Section -Title "NEXT STATUS" -Content $answered.next_status_summary.fallback_markdown
  if (-not $answered.next_status_summary.user_action_required) {
    break
  }
  $pending = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/orchestrations/$orchestrationId/pending-decisions" -Query @{ project_id = $projectId }) -Headers $bridgeHeaders
}

if ($TaskMode -ne "dry_run") {
  for ($attempt = 0; $attempt -lt 90; $attempt += 1) {
    $orchestrationState = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/orchestrations/$orchestrationId" -Query @{ project_id = $projectId }) -Headers $bridgeHeaders
    $pending = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/orchestrations/$orchestrationId/pending-decisions" -Query @{ project_id = $projectId }) -Headers $bridgeHeaders
    if ($pending -and $pending.Count -gt 0) {
      break
    }
    if ($orchestrationState.status -eq "completed") {
      break
    }
    Start-Sleep -Seconds 1
  }
  $finalStatus = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/orchestrations/$orchestrationId/status-summary" -Query @{ project_id = $projectId }) -Headers $bridgeHeaders
  Write-Section -Title "FINAL STATUS" -Content $finalStatus.fallback_markdown
}

$digest = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/orchestrations/$orchestrationId/event-digest" -Query @{ window = "since_orchestration_start"; project_id = $projectId }) -Headers $bridgeHeaders
Write-Section -Title "EVENT DIGEST" -Content $digest.fallback_markdown

$handoff = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/orchestrations/$orchestrationId/handoff-summary" -Query @{ project_id = $projectId }) -Headers $bridgeHeaders
$approvalLog = Invoke-Json -Method GET -Url (Get-ApiUrl -Path "/api/projects/$projectId/security/audit-log") -Headers $bridgeHeaders
$approvalSummary = if ($approvalLog -and $approvalLog.Count -gt 0) {
  ($approvalLog | Select-Object -First 5 | ForEach-Object {
    "{0} | {1} | {2} | {3}" -f $_.created_at, $_.decision, $_.action_type, $_.action_summary
  }) -join [Environment]::NewLine
} else {
  "No approval audit entries were recorded."
}
Write-Section -Title "HANDOFF SUMMARY" -Content $handoff.fallback_markdown
Write-Section -Title "APPROVAL AUDIT LOG" -Content $approvalSummary

if (-not [string]::IsNullOrWhiteSpace($TranscriptPath)) {
  $transcriptTarget = [System.IO.Path]::GetFullPath($TranscriptPath)
  $transcriptDir = Split-Path -Parent $transcriptTarget
  if ($transcriptDir) {
    $null = New-Item -ItemType Directory -Path $transcriptDir -Force
  }
  $generatedAt = (Get-Date).ToString("u")
  $commandLine = ".\scripts\smoke-headless-happy-path.ps1 -TranscriptPath $TranscriptPath"
  $content = @(
    "# Headless Terminal Transcript",
    "",
    "Generated at: $generatedAt",
    "Command: $commandLine",
    "Workspace root: $workspacePath",
    "",
    ($transcriptSections -join "`n`n")
  ) -join "`n"
  Set-Content -Path $transcriptTarget -Value $content -Encoding UTF8
  Write-Host ""
  Write-Host "Saved transcript to $transcriptTarget"
}
