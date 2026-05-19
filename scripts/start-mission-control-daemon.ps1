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
    backendPort = 8010
    launcherLogDir = ".runtime/launcher"
  }
}

$effectiveHost = if ($BindHost) { $BindHost } else { [string]$config.host }
$effectiveBackendPort = if ($PSBoundParameters.ContainsKey("BackendPort")) { $BackendPort } else { [int]$config.backendPort }
$launcherDir = Join-Path $repoRoot ([string]$config.launcherLogDir)
$metadataPath = Join-Path $launcherDir "daemon.json"
$stdoutPath = Join-Path $launcherDir "daemon.stdout.log"
$stderrPath = Join-Path $launcherDir "daemon.stderr.log"
$launchLogPath = Join-Path $launcherDir "daemon.launch.log"
$null = New-Item -ItemType Directory -Path $launcherDir -Force

function Assert-LocalHost {
  param([string]$HostValue)
  if ($HostValue -notin @("127.0.0.1", "localhost", "::1")) {
    throw "Mission Control headless daemon must stay localhost-only. Refusing host '$HostValue'."
  }
}

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

function Get-ProcessPathEntries {
  $entries = @()
  foreach ($scope in @("Process", "User", "Machine")) {
    $value = [System.Environment]::GetEnvironmentVariable("Path", $scope)
    if (-not $value) {
      $value = [System.Environment]::GetEnvironmentVariable("PATH", $scope)
    }
    if ($value) {
      $entries += ($value -split ';' | Where-Object { $_ })
    }
  }
  return $entries
}

function Add-UniquePathEntries {
  param([string[]]$Entries)
  $current = [System.Environment]::GetEnvironmentVariable("Path", "Process")
  if (-not $current) {
    $current = [System.Environment]::GetEnvironmentVariable("PATH", "Process")
  }
  $combined = @()
  if ($current) {
    $combined += ($current -split ';' | Where-Object { $_ })
  }
  $combined += $Entries

  $unique = New-Object System.Collections.Generic.List[string]
  $seen = @{}
  foreach ($entry in $combined) {
    if (-not $entry) {
      continue
    }
    $trimmed = $entry.Trim()
    if (-not $trimmed) {
      continue
    }
    $key = $trimmed.ToLowerInvariant()
    if ($seen.ContainsKey($key)) { continue }
    $seen[$key] = $true
    $unique.Add($trimmed)
  }
  $normalized = ($unique -join ';')
  [System.Environment]::SetEnvironmentVariable("PATH", $null, "Process")
  [System.Environment]::SetEnvironmentVariable("Path", $normalized, "Process")
}

function Resolve-CodexCliPath {
  foreach ($name in @("codex", "codex.cmd", "codex.exe", "codex.ps1", "codex.bat")) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }

  $userHome = [Environment]::GetFolderPath("UserProfile")
  $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
  $tempRoot = [System.IO.Path]::GetTempPath()
  $candidates = @(
    $env:MISSION_CONTROL_CODEX_PATH,
    $env:CODEX_CLI_PATH,
    (Join-Path $localAppData "Microsoft\WindowsApps\codex.exe"),
    (Join-Path $localAppData "Programs\Codex\codex.exe"),
    (Join-Path $localAppData "Programs\OpenAI Codex\codex.exe"),
    (Join-Path $userHome ".local\bin\codex.exe"),
    (Join-Path $userHome ".local\bin\codex"),
    (Join-Path $tempRoot "codex.exe"),
    (Join-Path $tempRoot "codex.cmd")
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return (Resolve-Path $candidate).Path
    }
  }
  return $null
}

function Add-CodexCliPaths {
  $userHome = [Environment]::GetFolderPath("UserProfile")
  $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
  $candidateDirs = @()

  foreach ($entry in (Get-ProcessPathEntries)) {
    if (Test-Path $entry) {
      $candidateDirs += $entry
    }
  }

  foreach ($explicit in @($env:MISSION_CONTROL_CODEX_PATH, $env:CODEX_CLI_PATH)) {
    if (-not $explicit) {
      continue
    }
    if (Test-Path $explicit -PathType Leaf) {
      $candidateDirs += (Split-Path $explicit -Parent)
    } elseif (Test-Path $explicit -PathType Container) {
      $candidateDirs += $explicit
    }
  }

  $candidateDirs += @(
    (Join-Path $localAppData "Microsoft\WindowsApps"),
    (Join-Path $userHome "AppData\Local\Microsoft\WindowsApps"),
    (Join-Path $localAppData "Programs\Codex"),
    (Join-Path $localAppData "Programs\OpenAI Codex"),
    (Join-Path $userHome ".local\bin")
  )

  Add-UniquePathEntries -Entries ($candidateDirs | Where-Object { $_ -and (Test-Path $_) })
  return Resolve-CodexCliPath
}

function Test-ProcessRunning {
  param([int]$ProcessId)
  return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-DaemonMetadata {
  if (-not (Test-Path $metadataPath)) {
    return $null
  }
  try {
    return Get-Content -Raw $metadataPath | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Test-TcpPortListening {
  param(
    [string]$TargetHost,
    [int]$Port
  )

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
    $connected = $async.AsyncWaitHandle.WaitOne(500)
    if (-not $connected) {
      return $false
    }
    $client.EndConnect($async)
    return $true
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
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

function Test-ExpectedDaemon {
  $metadata = Get-DaemonMetadata
  if (-not $metadata) {
    return $false
  }
  if ([string]$metadata.host -ne $effectiveHost) {
    return $false
  }
  if ([int]$metadata.port -ne $effectiveBackendPort) {
    return $false
  }
  if ([string]$metadata.mode -ne "daemon") {
    return $false
  }
  if ($metadata.repo_root -and ([string]$metadata.repo_root -ne $repoRoot)) {
    return $false
  }
  if (-not $metadata.pid) {
    return $false
  }
  return (Test-ProcessRunning -ProcessId ([int]$metadata.pid))
}

function Get-LogTail {
  param([string]$PathValue)
  if (-not (Test-Path $PathValue)) {
    return ""
  }
  try {
    return ((Get-Content -Tail 20 $PathValue) -join [Environment]::NewLine)
  } catch {
    return ""
  }
}

function Wait-ForBackend {
  param([System.Diagnostics.Process]$ProcessHandle)
  for ($index = 0; $index -lt 60; $index += 1) {
    if (Test-BackendHealthy) {
      return
    }
    if ($ProcessHandle) {
      $ProcessHandle.Refresh()
      if ($ProcessHandle.HasExited) {
        $stderrTail = Get-LogTail -PathValue $stderrPath
        $stdoutTail = Get-LogTail -PathValue $stdoutPath
        throw "Mission Control daemon exited before becoming healthy. stderr:`n$stderrTail`nstdout:`n$stdoutTail"
      }
    }
    Start-Sleep -Milliseconds 500
  }
  throw "Mission Control daemon did not become healthy in time."
}

Assert-LocalHost -HostValue $effectiveHost

$pythonPath = Get-RequiredCommand -Names @("python", "py")
$serverScript = Join-Path $repoRoot "apps\server\src\mission_control_daemon.py"
$codexCliPath = Add-CodexCliPaths

$launchInfo = [ordered]@{
  generated_at = (Get-Date).ToString("o")
  repo_root = $repoRoot
  backend_host = $effectiveHost
  backend_port = $effectiveBackendPort
  python_path = $pythonPath
  server_script = $serverScript
  codex_cli_path = $codexCliPath
  stdout_path = $stdoutPath
  stderr_path = $stderrPath
}
$launchInfo | ConvertTo-Json -Depth 4 | Set-Content -Path $launchLogPath -Encoding UTF8

if (Test-BackendHealthy) {
  if (Test-ExpectedDaemon) {
    Write-Host "[Mission Control] Daemon already healthy on http://${effectiveHost}:${effectiveBackendPort}"
    exit 0
  }
  throw "Port $effectiveBackendPort is serving a healthy HTTP process, but it is not the expected Mission Control daemon for this repository."
}

if (Test-TcpPortListening -TargetHost $effectiveHost -Port $effectiveBackendPort) {
  throw "Port $effectiveBackendPort is already occupied on ${effectiveHost}. Pick another backend port or stop the conflicting service first."
}

$env:MISSION_CONTROL_SERVER_MODE = "daemon"
$env:MISSION_CONTROL_BACKEND_HOST = $effectiveHost
$env:MISSION_CONTROL_BACKEND_PORT = [string]$effectiveBackendPort
$env:MISSION_CONTROL_REPO_ROOT = $repoRoot
if ($codexCliPath) {
  $env:MISSION_CONTROL_CODEX_PATH = $codexCliPath
}

$process = Start-Process `
  -FilePath $pythonPath `
  -ArgumentList @("-u", "`"$serverScript`"") `
  -WorkingDirectory $repoRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $stdoutPath `
  -RedirectStandardError $stderrPath `
  -PassThru

Wait-ForBackend -ProcessHandle $process
Start-Sleep -Seconds 3
$process.Refresh()
if ($process.HasExited) {
  $stderrTail = Get-LogTail -PathValue $stderrPath
  $stdoutTail = Get-LogTail -PathValue $stdoutPath
  throw "Mission Control daemon became briefly reachable and then exited. stderr:`n$stderrTail`nstdout:`n$stdoutTail"
}
if (-not (Test-BackendHealthy)) {
  $stderrTail = Get-LogTail -PathValue $stderrPath
  $stdoutTail = Get-LogTail -PathValue $stdoutPath
  throw "Mission Control daemon passed the initial health check but did not stay reachable. stderr:`n$stderrTail`nstdout:`n$stdoutTail"
}
if (-not (Test-ExpectedDaemon)) {
  throw "Mission Control daemon answered health checks, but daemon metadata did not validate the expected repo/host/port identity."
}

Write-Host "[Mission Control] Daemon started on PID $($process.Id) at http://${effectiveHost}:${effectiveBackendPort}"
