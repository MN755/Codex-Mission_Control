param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = Join-Path $PSScriptRoot "mission-control.config.json"
$config = if (Test-Path $configPath) {
  Get-Content -Raw $configPath | ConvertFrom-Json
} else {
  [pscustomobject]@{
    launcherLogDir = ".runtime/launcher"
  }
}

$launcherDir = Join-Path $repoRoot ([string]$config.launcherLogDir)
$metadataPath = Join-Path $launcherDir "daemon.json"

if (-not (Test-Path $metadataPath)) {
  Write-Host "[Mission Control] No daemon metadata found at $metadataPath"
  exit 0
}

$metadata = Get-Content -Raw $metadataPath | ConvertFrom-Json
if (-not $metadata.pid) {
  Write-Host "[Mission Control] Daemon metadata did not include a PID."
  exit 0
}

$trackedPid = [int]$metadata.pid
$process = Get-Process -Id $trackedPid -ErrorAction SilentlyContinue
if (-not $process) {
  Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
  Write-Host "[Mission Control] Daemon PID $trackedPid was not running."
  exit 0
}

$cim = Get-CimInstance Win32_Process -Filter "ProcessId = $trackedPid"
$commandLine = [string]$cim.CommandLine
if (-not $commandLine -or $commandLine -notlike "*$repoRoot*") {
  throw "Refusing to stop PID $trackedPid because the command line does not match this repository."
}

Stop-Process -Id $trackedPid -Force
Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
Write-Host "[Mission Control] Daemon stopped (PID $trackedPid)."
