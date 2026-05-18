param(
  [int]$BackendPort,
  [string]$BindHost
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = Join-Path $PSScriptRoot "mission-control.config.json"
$config = if (Test-Path $configPath) {
  Get-Content -Raw $configPath | ConvertFrom-Json
} else {
  [pscustomobject]@{
    host = "127.0.0.1"
    backendPort = 8000
    launcherLogDir = ".runtime/launcher"
  }
}

$effectiveHost = if ($BindHost) { $BindHost } else { [string]$config.host }
$effectiveBackendPort = if ($PSBoundParameters.ContainsKey("BackendPort")) { $BackendPort } else { [int]$config.backendPort }
$launcherDir = Join-Path $repoRoot ([string]$config.launcherLogDir)
$null = New-Item -ItemType Directory -Path $launcherDir -Force

function Get-RequiredCommand {
  param([string[]]$Names)
  foreach ($name in $Names) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }
  throw "Required command not found: $($Names -join ', ')"
}

function Test-BackendHealthy {
  $backendHealthUrl = "http://${effectiveHost}:${effectiveBackendPort}/api/health"
  try {
    $response = Invoke-WebRequest -Uri $backendHealthUrl -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"'
  } catch {
    return $false
  }
}

function Wait-ForBackend {
  for ($index = 0; $index -lt 60; $index += 1) {
    if (Test-BackendHealthy) {
      return
    }
    Start-Sleep -Milliseconds 500
  }
  throw "Mission Control daemon did not become healthy in time."
}

$pythonPath = Get-RequiredCommand -Names @("python", "py")
$serverScript = Join-Path $repoRoot "apps\server\src\mission_control_daemon.py"
$stdoutPath = Join-Path $launcherDir "daemon.stdout.log"
$stderrPath = Join-Path $launcherDir "daemon.stderr.log"

if (Test-BackendHealthy) {
  Write-Host "[Mission Control] Daemon already healthy on http://${effectiveHost}:${effectiveBackendPort}"
  exit 0
}

$env:MISSION_CONTROL_SERVER_MODE = "daemon"
$env:MISSION_CONTROL_BACKEND_HOST = $effectiveHost
$env:MISSION_CONTROL_BACKEND_PORT = [string]$effectiveBackendPort
$env:MISSION_CONTROL_REPO_ROOT = $repoRoot

$process = Start-Process `
  -FilePath $pythonPath `
  -ArgumentList @($serverScript) `
  -WorkingDirectory $repoRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutPath `
  -RedirectStandardError $stderrPath `
  -PassThru

Wait-ForBackend
Write-Host "[Mission Control] Daemon started on PID $($process.Id) at http://${effectiveHost}:${effectiveBackendPort}"
