param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = Join-Path $PSScriptRoot "mission-control.config.json"
$config = if (Test-Path $configPath) {
  Get-Content -Raw $configPath | ConvertFrom-Json
} else {
  [pscustomobject]@{
    host = "127.0.0.1"
    backendPort = 8010
    launcherLogDir = ".runtime/launcher"
  }
}

$effectiveHost = [string]$config.host
$effectiveBackendPort = [int]$config.backendPort
$launcherDir = Join-Path $repoRoot ([string]$config.launcherLogDir)
$metadataPath = Join-Path $launcherDir "daemon.json"

function Get-DaemonIdentity {
  $identityUrl = "http://${effectiveHost}:${effectiveBackendPort}/api/diagnostics/identity"
  try {
    $response = Invoke-WebRequest -Uri $identityUrl -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -ne 200) {
      return $null
    }
    return ($response.Content | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Get-ListeningPortPid {
  $lines = netstat -ano | Select-String ":$effectiveBackendPort"
  foreach ($line in $lines) {
    $text = [string]$line
    if ($text -notmatch "\s+LISTENING\s+(\d+)\s*$") {
      continue
    }
    $pidText = $Matches[1]
    if ($text -notmatch "^\s*TCP\s+$([regex]::Escape($effectiveHost)):$effectiveBackendPort\s+") {
      continue
    }
    return [int]$pidText
  }
  return 0
}

$identity = Get-DaemonIdentity
$trackedPid = 0
if ($identity -and [string]$identity.repo_root -eq $repoRoot -and [string]$identity.mode -eq "daemon") {
  $trackedPid = [int]$identity.pid
}

if ($trackedPid -le 0 -and -not (Test-Path $metadataPath)) {
  $portPid = Get-ListeningPortPid
  if ($portPid -le 0) {
    Write-Host "[Mission Control] No daemon metadata found at $metadataPath"
    exit 0
  }
  if (-not ($identity -and [string]$identity.repo_root -eq $repoRoot -and [string]$identity.mode -eq "daemon")) {
    throw "Refusing to stop PID $portPid on port $effectiveBackendPort because daemon identity could not be confirmed for this repository."
  }
  $trackedPid = $portPid
}

if ($trackedPid -le 0) {
  $metadata = Get-Content -Raw $metadataPath | ConvertFrom-Json
  if (-not $metadata.pid) {
    Write-Host "[Mission Control] Daemon metadata did not include a PID."
  } else {
    $trackedPid = [int]$metadata.pid
  }
}

$process = Get-Process -Id $trackedPid -ErrorAction SilentlyContinue
if (-not $process) {
  $portPid = Get-ListeningPortPid
  if ($portPid -le 0) {
    Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
    Write-Host "[Mission Control] Daemon PID $trackedPid was not running."
    exit 0
  }
  if (-not ($identity -and [string]$identity.repo_root -eq $repoRoot -and [string]$identity.mode -eq "daemon")) {
    throw "Refusing to stop PID $portPid on port $effectiveBackendPort because daemon identity could not be confirmed for this repository."
  }
  $trackedPid = $portPid
  $process = Get-Process -Id $trackedPid -ErrorAction SilentlyContinue
  if (-not $process) {
    Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
    Write-Host "[Mission Control] Port owner PID $trackedPid was not running."
    exit 0
  }
}

$commandLine = ""
try {
  $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $trackedPid"
  $commandLine = [string]$cim.CommandLine
} catch {
  $commandLine = ""
}
if (-not $commandLine -or $commandLine -notlike "*$repoRoot*") {
  if (-not ($identity -and [string]$identity.repo_root -eq $repoRoot -and [string]$identity.mode -eq "daemon" -and (Get-ListeningPortPid) -eq $trackedPid)) {
    throw "Refusing to stop PID $trackedPid because the command line does not match this repository."
  }
}

Stop-Process -Id $trackedPid -Force
Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
Write-Host "[Mission Control] Daemon stopped (PID $trackedPid)."
