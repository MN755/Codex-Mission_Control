param(
  [int]$BackendPort,
  [string]$BindHost
)

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
    host = "127.0.0.1"
    backendPort = 8010
    launcherLogDir = ".runtime/launcher"
  }
}

$effectiveHost = if ($BindHost) { $BindHost } else { [string]$config.host }
$effectiveBackendPort = if ($PSBoundParameters.ContainsKey("BackendPort")) { $BackendPort } else { [int]$config.backendPort }
$launcherDir = if ($env:MISSION_CONTROL_LAUNCHER_DIR) {
  $env:MISSION_CONTROL_LAUNCHER_DIR
} else {
  Join-Path $repoRoot ([string]$config.launcherLogDir)
}
$frontendDir = Join-Path $repoRoot "apps\dashboard"
$frontendDist = Join-Path $frontendDir "dist"
$frontendIndexPath = Join-Path $frontendDist "index.html"
$metadataPath = Join-Path $launcherDir "daemon.json"
$stdoutPath = Join-Path $launcherDir "daemon.stdout.log"
$stderrPath = Join-Path $launcherDir "daemon.stderr.log"
$launchLogPath = Join-Path $launcherDir "daemon.launch.log"
$null = New-Item -ItemType Directory -Path $launcherDir -Force
$runtimeRoot = if ($env:MISSION_CONTROL_RUNTIME_ROOT) {
  $env:MISSION_CONTROL_RUNTIME_ROOT
} else {
  Join-Path $repoRoot ".runtime"
}
$runtimeCodexProfileRoot = if ($env:MISSION_CONTROL_CODEX_PROFILE_ROOT) {
  $env:MISSION_CONTROL_CODEX_PROFILE_ROOT
} else {
  Join-Path $runtimeRoot "codex-profile"
}
$runtimeCodexHome = if ($env:MISSION_CONTROL_CODEX_HOME) {
  $env:MISSION_CONTROL_CODEX_HOME
} else {
  Join-Path $runtimeCodexProfileRoot ".codex"
}

function Assert-LocalHost {
  param([string]$HostValue)
  if ($HostValue -notin @("127.0.0.1", "localhost", "::1")) {
    throw "Mission Control headless daemon must stay localhost-only. Refusing host '$HostValue'."
  }
}

function Get-UrlHost {
  param([string]$HostValue)
  if ($HostValue -like "*:*" -and -not $HostValue.StartsWith("[")) {
    return "[$HostValue]"
  }
  return $HostValue
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

function Resolve-SourceCodexHome {
  if ($env:CODEX_HOME) {
    return [System.IO.Path]::GetFullPath($env:CODEX_HOME)
  }
  $userHome = [Environment]::GetFolderPath("UserProfile")
  return [System.IO.Path]::GetFullPath((Join-Path $userHome ".codex"))
}

function Sync-CodexAuthAssets {
  param(
    [string]$SourceCodexHome,
    [string]$TargetCodexHome
  )

  $sourcePath = [System.IO.Path]::GetFullPath($SourceCodexHome)
  $targetPath = [System.IO.Path]::GetFullPath($TargetCodexHome)
  $null = New-Item -ItemType Directory -Path $targetPath -Force
  $copiedFiles = New-Object System.Collections.Generic.List[string]

  foreach ($name in @("auth.json", ".credentials.json", "installation_id")) {
    $sourceFile = Join-Path $sourcePath $name
    if (-not (Test-Path $sourceFile -PathType Leaf)) {
      continue
    }
    Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $targetPath $name) -Force
    $copiedFiles.Add($name) | Out-Null
  }

  return [pscustomobject]@{
    source_home = $sourcePath
    target_home = $targetPath
    copied_files = @($copiedFiles)
  }
}

function Test-IsWindowsAppsShimPath {
  param([string]$PathValue)
  if (-not $PathValue) {
    return $false
  }
  $normalized = $PathValue.Replace('/', '\').ToLowerInvariant()
  return $normalized -like "*\microsoft\windowsapps\*" -or $normalized -like "*\program files\windowsapps\*"
}

function Resolve-CodexCliPath {
  $userHome = [Environment]::GetFolderPath("UserProfile")
  $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
  $tempRoot = [System.IO.Path]::GetTempPath()
  $candidates = New-Object System.Collections.Generic.List[string]
  foreach ($candidate in @(
    $env:MISSION_CONTROL_CODEX_PATH,
    $env:CODEX_CLI_PATH,
    (Join-Path $localAppData "OpenAI\Codex\bin\codex.exe"),
    (Join-Path $localAppData "Programs\OpenAI Codex\codex.exe"),
    (Join-Path $localAppData "Programs\Codex\codex.exe"),
    (Join-Path $userHome ".local\bin\codex.exe"),
    (Join-Path $userHome ".local\bin\codex"),
    (Join-Path $tempRoot "codex.exe"),
    (Join-Path $tempRoot "codex.cmd")
  )) {
    if ($candidate) {
      $null = $candidates.Add($candidate)
    }
  }

  $versionedBinRoot = Join-Path $localAppData "OpenAI\Codex\bin"
  if (Test-Path $versionedBinRoot -PathType Container) {
    $versionedEntries = Get-ChildItem -Path $versionedBinRoot -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
    foreach ($entry in $versionedEntries) {
      $null = $candidates.Add((Join-Path $entry.FullName "codex.exe"))
    }
  }

  foreach ($candidate in @(
    (Join-Path $localAppData "Microsoft\WindowsApps\codex.exe")
  )) {
    if ($candidate) {
      $null = $candidates.Add($candidate)
    }
  }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return (Resolve-Path $candidate).Path
    }
  }

  $windowsAppsFallback = $null
  foreach ($name in @("codex", "codex.cmd", "codex.exe", "codex.ps1", "codex.bat")) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $command) {
      continue
    }
    $resolved = $command.Source
    try {
      $resolved = (Resolve-Path $resolved).Path
    } catch {
      $resolved = $command.Source
    }
    if (-not (Test-IsWindowsAppsShimPath -PathValue $resolved)) {
      return $resolved
    }
    if (-not $windowsAppsFallback) {
      $windowsAppsFallback = $resolved
    }
  }
  return $windowsAppsFallback
}

function Resolve-ClaudeCliPath {
  foreach ($name in @("claude", "claude.cmd", "claude.exe", "claude.ps1", "claude.bat")) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }

  $userHome = [Environment]::GetFolderPath("UserProfile")
  $appData = [Environment]::GetFolderPath("ApplicationData")
  $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
  $candidates = @(
    $env:MISSION_CONTROL_CLAUDE_PATH,
    $env:CLAUDE_CLI_PATH,
    (Join-Path $appData "npm\claude.cmd"),
    (Join-Path $appData "npm\claude.ps1"),
    (Join-Path $appData "npm\claude"),
    (Join-Path $localAppData "Programs\Claude\claude.exe"),
    (Join-Path $userHome ".local\bin\claude.exe"),
    (Join-Path $userHome ".local\bin\claude")
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return (Resolve-Path $candidate).Path
    }
  }
  return $null
}

function Ensure-FrontendBundle {
  if (Test-Path $frontendIndexPath -PathType Leaf) {
    return
  }
  $npmPath = Get-RequiredCommand -Names @("npm.cmd", "npm")
  Write-Host "[Mission Control] Dashboard bundle missing. Building frontend..."
  Push-Location $frontendDir
  try {
    & $env:ComSpec /c "`"$npmPath`" run build" | Out-Host
  } finally {
    Pop-Location
  }
  if (-not (Test-Path $frontendIndexPath -PathType Leaf)) {
    throw "Dashboard frontend build output was not created at $frontendIndexPath"
  }
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

  $versionedBinRoot = Join-Path $localAppData "OpenAI\Codex\bin"
  if (Test-Path $versionedBinRoot -PathType Container) {
    $candidateDirs += $versionedBinRoot
    $candidateDirs += (Get-ChildItem -Path $versionedBinRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
  }

  $candidateDirs += @(
    (Join-Path $localAppData "OpenAI\Codex\bin"),
    (Join-Path $localAppData "Programs\OpenAI Codex"),
    (Join-Path $localAppData "Programs\Codex"),
    (Join-Path $localAppData "Microsoft\WindowsApps"),
    (Join-Path $userHome "AppData\Local\Microsoft\WindowsApps"),
    (Join-Path $userHome ".local\bin")
  )

  Add-UniquePathEntries -Entries ($candidateDirs | Where-Object { $_ -and (Test-Path $_) })
  return Resolve-CodexCliPath
}

function Add-ClaudeCliPaths {
  $userHome = [Environment]::GetFolderPath("UserProfile")
  $appData = [Environment]::GetFolderPath("ApplicationData")
  $localAppData = [Environment]::GetFolderPath("LocalApplicationData")
  $candidateDirs = @()

  foreach ($entry in (Get-ProcessPathEntries)) {
    if (Test-Path $entry) {
      $candidateDirs += $entry
    }
  }

  foreach ($explicit in @($env:MISSION_CONTROL_CLAUDE_PATH, $env:CLAUDE_CLI_PATH)) {
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
    (Join-Path $appData "npm"),
    (Join-Path $localAppData "Programs\Claude"),
    (Join-Path $userHome ".local\bin")
  )

  Add-UniquePathEntries -Entries ($candidateDirs | Where-Object { $_ -and (Test-Path $_) })
  return Resolve-ClaudeCliPath
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
  $urlHost = Get-UrlHost $effectiveHost
  $backendHealthUrl = "http://${urlHost}:${effectiveBackendPort}/api/health"
  try {
    $response = Invoke-WebRequest -Uri $backendHealthUrl -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"'
  } catch {
    return $false
  }
}

function Test-FrontendHealthy {
  $urlHost = Get-UrlHost $effectiveHost
  $frontendUrl = "http://${urlHost}:${effectiveBackendPort}/dashboard"
  try {
    $response = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Get-DaemonIdentity {
  $urlHost = Get-UrlHost $effectiveHost
  $identityUrl = "http://${urlHost}:${effectiveBackendPort}/api/diagnostics/identity"
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

function Test-ExpectedDaemon {
  $identity = Get-DaemonIdentity
  if ($identity) {
    if ([string]$identity.host -ne $effectiveHost) {
      return $false
    }
    if ([int]$identity.port -ne $effectiveBackendPort) {
      return $false
    }
    if ([string]$identity.mode -ne "daemon") {
      return $false
    }
    if ($identity.repo_root -and ([string]$identity.repo_root -ne $repoRoot)) {
      return $false
    }
    return $true
  }
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
    if ((Test-BackendHealthy) -and (Test-FrontendHealthy)) {
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
$codexCliPath = Resolve-CodexCliPath
$claudeCliPath = Resolve-ClaudeCliPath
$codexHomeSync = Sync-CodexAuthAssets -SourceCodexHome (Resolve-SourceCodexHome) -TargetCodexHome $runtimeCodexHome
$runtimeCodexProfileRoot = [System.IO.Path]::GetFullPath($runtimeCodexProfileRoot)
$runtimeCodexHome = [string]$codexHomeSync.target_home
$sourceUserProfile = if ($env:MISSION_CONTROL_SOURCE_USERPROFILE) {
  $env:MISSION_CONTROL_SOURCE_USERPROFILE
} elseif ($env:USERPROFILE) {
  $env:USERPROFILE
} else {
  [Environment]::GetFolderPath("UserProfile")
}
$sourceHome = if ($env:MISSION_CONTROL_SOURCE_HOME) {
  $env:MISSION_CONTROL_SOURCE_HOME
} elseif ($env:HOME) {
  $env:HOME
} else {
  $sourceUserProfile
}

$launchInfo = [ordered]@{
  generated_at = (Get-Date).ToString("o")
  repo_root = $repoRoot
  backend_host = $effectiveHost
  backend_port = $effectiveBackendPort
  python_path = $pythonPath
  server_script = $serverScript
  codex_cli_path = $codexCliPath
  codex_source_home = $codexHomeSync.source_home
  codex_profile_root = $runtimeCodexProfileRoot
  codex_home = $runtimeCodexHome
  codex_auth_files = @($codexHomeSync.copied_files)
  claude_cli_path = $claudeCliPath
  stdout_path = $stdoutPath
  stderr_path = $stderrPath
}
$launchInfo | ConvertTo-Json -Depth 4 | Set-Content -Path $launchLogPath -Encoding UTF8

if (Test-BackendHealthy) {
  if (Test-ExpectedDaemon) {
    Ensure-FrontendBundle
    if (-not (Test-FrontendHealthy)) {
      Start-Sleep -Milliseconds 500
      if (-not (Test-FrontendHealthy)) {
        $urlHost = Get-UrlHost $effectiveHost
        throw "Mission Control daemon is healthy, but the dashboard frontend is not reachable at http://${urlHost}:${effectiveBackendPort}/dashboard"
      }
    }
    $urlHost = Get-UrlHost $effectiveHost
    Write-Host "[Mission Control] Daemon already healthy on http://${urlHost}:${effectiveBackendPort}"
    exit 0
  }
  throw "Port $effectiveBackendPort is serving a healthy HTTP process, but it is not the expected Mission Control daemon for this repository."
}

if (Test-TcpPortListening -TargetHost $effectiveHost -Port $effectiveBackendPort) {
  throw "Port $effectiveBackendPort is already occupied on ${effectiveHost}. Pick another backend port or stop the conflicting service first."
}

Ensure-FrontendBundle

$env:MISSION_CONTROL_SERVER_MODE = "daemon"
$env:MISSION_CONTROL_BACKEND_HOST = $effectiveHost
$env:MISSION_CONTROL_BACKEND_PORT = [string]$effectiveBackendPort
$env:MISSION_CONTROL_FRONTEND_DIST = $frontendDist
$env:MISSION_CONTROL_LAUNCHER_DIR = $launcherDir
$env:MISSION_CONTROL_RUNTIME_ROOT = $runtimeRoot
$env:MISSION_CONTROL_CODEX_PROFILE_ROOT = $runtimeCodexProfileRoot
$env:MISSION_CONTROL_CODEX_HOME = $runtimeCodexHome
$env:MISSION_CONTROL_SOURCE_CODEX_HOME = $codexHomeSync.source_home
$env:MISSION_CONTROL_SOURCE_USERPROFILE = $sourceUserProfile
$env:MISSION_CONTROL_SOURCE_HOME = $sourceHome
$env:USERPROFILE = $runtimeCodexProfileRoot
$env:HOME = $runtimeCodexProfileRoot
if ($codexCliPath) {
  $env:MISSION_CONTROL_CODEX_PATH = $codexCliPath
}
if ($claudeCliPath) {
  $env:MISSION_CONTROL_CLAUDE_PATH = $claudeCliPath
}

# Do not let a nested Codex Desktop chat thread leak its own bridge
# instructions or thread-scoped sandbox into the background daemon.
foreach ($key in @(
  "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
  "CODEX_THREAD_ID",
  "CODEX_SHELL"
)) {
  if (Test-Path "Env:$key") {
    Remove-Item "Env:$key" -ErrorAction SilentlyContinue
  }
}

# Some Windows shells surface both Path and PATH; Start-Process treats that as
# a duplicate-key environment block and aborts before launch.
if (Test-Path Env:PATH) {
  Remove-Item Env:PATH -ErrorAction SilentlyContinue
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
if (-not (Test-FrontendHealthy)) {
  $stderrTail = Get-LogTail -PathValue $stderrPath
  $stdoutTail = Get-LogTail -PathValue $stdoutPath
  throw "Mission Control daemon is healthy, but the dashboard frontend did not become reachable. stderr:`n$stderrTail`nstdout:`n$stdoutTail"
}
if (-not (Test-ExpectedDaemon)) {
  throw "Mission Control daemon answered health checks, but daemon metadata did not validate the expected repo/host/port identity."
}

$urlHost = Get-UrlHost $effectiveHost
Write-Host "[Mission Control] Daemon started on PID $($process.Id) at http://${urlHost}:${effectiveBackendPort}"
