param(
  [string]$RepoRoot,
  [string]$PythonCommand,
  [string]$ResultsPath,
  [string]$LogPath,
  [int]$LaunchWaitSeconds = 25
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if (-not $PythonCommand) {
  $PythonCommand = "python"
}

if (-not $ResultsPath) {
  $ResultsPath = Join-Path $RepoRoot ".runtime\codex-restart-smoke\latest.json"
}

if (-not $LogPath) {
  $LogPath = Join-Path $RepoRoot ".runtime\codex-restart-smoke\latest.log"
}

$resultsDir = Split-Path -Parent $ResultsPath
$logDir = Split-Path -Parent $LogPath
New-Item -ItemType Directory -Force -Path $resultsDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
  param([string]$Message)
  $line = "[{0}] {1}" -f (Get-Date).ToString("o"), $Message
  Add-Content -LiteralPath $LogPath -Value $line
}

function Resolve-CodexCliPath {
  $candidates = @()
  foreach ($explicit in @($env:MISSION_CONTROL_CODEX_PATH, $env:CODEX_CLI_PATH)) {
    if ($explicit) {
      $candidates += $explicit
    }
  }

  $localAppData = $env:LOCALAPPDATA
  if (-not $localAppData) {
    $localAppData = Join-Path $HOME "AppData\Local"
  }

  $candidates += @(
    (Join-Path $localAppData "OpenAI\Codex\bin\codex.exe"),
    (Join-Path $localAppData "OpenAI\Codex\bin\codex.cmd"),
    (Join-Path $localAppData "Programs\OpenAI Codex\codex.exe"),
    (Join-Path $localAppData "Programs\Codex\codex.exe")
  )

  $versionedBinRoot = Join-Path $localAppData "OpenAI\Codex\bin"
  if (Test-Path $versionedBinRoot) {
    Get-ChildItem -LiteralPath $versionedBinRoot -Directory -ErrorAction SilentlyContinue |
      Sort-Object Name -Descending |
      ForEach-Object { $candidates += (Join-Path $_.FullName "codex.exe") }
  }

  $candidates += (Join-Path $localAppData "Microsoft\WindowsApps\codex.exe")

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) {
      return (Resolve-Path $candidate).Path
    }
  }

  $command = Get-Command codex -ErrorAction SilentlyContinue
  if ($command -and $command.Path) {
    return $command.Path
  }

  return $null
}

function Stop-CodexProcesses {
  $targets = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -in @("Codex", "codex", "codex-command-runner-0.133.0-alpha.1")
  }
  foreach ($target in $targets) {
    try {
      Stop-Process -Id $target.Id -Force -ErrorAction Stop
      Write-Log "Stopped process $($target.ProcessName) PID=$($target.Id)"
    } catch {
      Write-Log "Failed to stop process PID=$($target.Id): $($_.Exception.Message)"
    }
  }
}

function Wait-ForCodexProcess {
  param([int]$TimeoutSeconds = 60)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @("Codex", "codex") }
    if ($running) {
      return $running | Select-Object Id, ProcessName, Path
    }
    Start-Sleep -Seconds 1
  }
  return @()
}

$result = [ordered]@{
  status = "starting"
  repo_root = $RepoRoot
  python_command = $PythonCommand
  results_path = $ResultsPath
  log_path = $LogPath
  launch_wait_seconds = $LaunchWaitSeconds
  started_at = (Get-Date).ToString("o")
}

try {
  Clear-Content -LiteralPath $LogPath -ErrorAction SilentlyContinue
  Write-Log "Starting Codex restart smoke workflow."
  $codexCliPath = Resolve-CodexCliPath
  if (-not $codexCliPath) {
    throw "Codex CLI path could not be resolved."
  }
  $result.codex_cli_path = $codexCliPath
  Write-Log "Resolved Codex CLI path: $codexCliPath"

  Stop-CodexProcesses
  Start-Sleep -Seconds 2

  $launchProcess = Start-Process -FilePath $codexCliPath -ArgumentList "app" -PassThru -WindowStyle Hidden
  $result.launcher_pid = $launchProcess.Id
  Write-Log "Launched Codex app via PID=$($launchProcess.Id)"

  $detected = Wait-ForCodexProcess -TimeoutSeconds 60
  $result.detected_processes = @($detected)
  if (-not $detected -or $detected.Count -eq 0) {
    throw "Timed out waiting for Codex processes to reappear after restart."
  }

  Write-Log "Detected Codex processes after relaunch. Waiting $LaunchWaitSeconds seconds before smoke checks."
  Start-Sleep -Seconds $LaunchWaitSeconds

  $manageScript = Join-Path $RepoRoot "scripts\mission-control-manage.py"
  $stdout = & $PythonCommand $manageScript codex-smoke --json 2>&1 | Out-String
  $result.smoke_stdout = $stdout.Trim()
  Write-Log "Smoke command finished."

  try {
    $smokeJson = $result.smoke_stdout | ConvertFrom-Json -Depth 20 -ErrorAction Stop
    $result.smoke = $smokeJson
    $result.status = if ($smokeJson.status -eq "ready") { "ready" } else { "degraded" }
  } catch {
    $result.status = "failed"
    $result.parse_error = $_.Exception.Message
    Write-Log "Failed to parse smoke JSON: $($_.Exception.Message)"
  }
} catch {
  $result.status = "failed"
  $result.error = $_.Exception.Message
  $result.error_record = ($_ | Out-String).Trim()
  Write-Log "Workflow failed: $($_.Exception.Message)"
} finally {
  $result.completed_at = (Get-Date).ToString("o")
  $result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ResultsPath -Encoding UTF8
  Write-Log "Wrote result artifact to $ResultsPath"
}
