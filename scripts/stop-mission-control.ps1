param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = if ($env:MISSION_CONTROL_LAUNCHER_CONFIG) {
  $env:MISSION_CONTROL_LAUNCHER_CONFIG
} else {
  Join-Path $PSScriptRoot "mission-control.config.json"
}
$config = if (Test-Path $configPath) {
  Get-Content -Raw $configPath | ConvertFrom-Json
} else {
  [pscustomobject]@{
    launcherLogDir = ".runtime/launcher"
  }
}
$launcherDir = if ($env:MISSION_CONTROL_LAUNCHER_DIR) {
  $env:MISSION_CONTROL_LAUNCHER_DIR
} else {
  Join-Path $repoRoot ([string]$config.launcherLogDir)
}
$pidFile = Join-Path $launcherDir "pids.json"

if (-not (Test-Path $pidFile)) {
  Write-Host "No launcher PID file found at $pidFile"
  exit 0
}

$metadata = Get-Content -Raw $pidFile | ConvertFrom-Json

function Get-MetadataEntry {
  param([string]$Name)
  $property = $metadata.PSObject.Properties[$Name]
  if ($property) {
    return $property.Value
  }
  return $null
}

function Stop-TrackedProcess {
  param(
    [string]$Name,
    [object]$Entry
  )

  if (-not $Entry -or -not $Entry.pid) {
    return
  }

  $trackedPid = [int]$Entry.pid
  $process = Get-Process -Id $trackedPid -ErrorAction SilentlyContinue
  if (-not $process) {
    return
  }

  $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $trackedPid"
  $commandLine = $cim.CommandLine
  if (-not $commandLine -or $commandLine -notlike "*$repoRoot*") {
    Write-Warning "Skipping PID $trackedPid for $Name because the command line does not match this repo."
    return
  }

  Stop-Process -Id $trackedPid -Force
  Write-Host "Stopped $Name (PID $trackedPid)"
}

Stop-TrackedProcess -Name "backend" -Entry (Get-MetadataEntry -Name "backend")
Stop-TrackedProcess -Name "frontend" -Entry (Get-MetadataEntry -Name "frontend")
Stop-TrackedProcess -Name "desktop" -Entry (Get-MetadataEntry -Name "desktop")

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Mission Control processes stopped."
