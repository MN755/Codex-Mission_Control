param(
  [ValidateSet("desktop", "web")]
  [string]$Mode = "desktop",
  [int]$BackendPort,
  [int]$FrontendPort,
  [string]$BindHost,
  [switch]$NoBrowser
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
    frontendPort = 5173
    autoOpenBrowser = $true
    launcherLogDir = ".runtime/launcher"
  }
}

$effectiveHost = if ($BindHost) { $BindHost } else { [string]$config.host }
$effectiveBackendPort = if ($PSBoundParameters.ContainsKey("BackendPort")) { $BackendPort } else { [int]$config.backendPort }
$effectiveFrontendPort = if ($PSBoundParameters.ContainsKey("FrontendPort")) { $FrontendPort } else { [int]$config.frontendPort }
$autoOpenBrowser = -not $NoBrowser -and [bool]$config.autoOpenBrowser

$launcherDir = Join-Path $repoRoot ([string]$config.launcherLogDir)
$null = New-Item -ItemType Directory -Path $launcherDir -Force
$pidFile = Join-Path $launcherDir "pids.json"

function Write-Status {
  param([string]$Message)
  Write-Host "[Mission Control] $Message"
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

function Get-PythonWindowlessPath {
  param([string]$PythonPath)
  $candidate = Join-Path (Split-Path $PythonPath) "pythonw.exe"
  if (Test-Path $candidate) {
    return $candidate
  }
  return $PythonPath
}

function Test-PortOpen {
  param(
    [string]$TargetHost,
    [int]$Port
  )

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
    $connected = $async.AsyncWaitHandle.WaitOne(700)
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

function Test-FrontendHealthy {
  $frontendUrl = "http://${effectiveHost}:${effectiveFrontendPort}"
  try {
    $response = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 2
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  } catch {
    return $false
  }
}

function Wait-ForHealthy {
  param(
    [scriptblock]$Probe,
    [string]$Name,
    [int]$Attempts = 90
  )

  for ($index = 0; $index -lt $Attempts; $index += 1) {
    if (& $Probe) {
      return
    }
    Start-Sleep -Milliseconds 1000
  }

  throw "$Name did not become healthy in time."
}

function Start-TrackedShellProcess {
  param(
    [string]$Name,
    [string]$WorkingDirectory,
    [string]$Command,
    [switch]$Hidden
  )

  $stdoutPath = Join-Path $launcherDir "$Name.stdout.log"
  $stderrPath = Join-Path $launcherDir "$Name.stderr.log"
  $cmdPath = Join-Path $env:WINDIR "System32\cmd.exe"
  $scriptPath = Join-Path $launcherDir "$Name.launch.cmd"
  $scriptContent = @"
@echo off
cd /d "$WorkingDirectory"
$Command 1>>"$stdoutPath" 2>>"$stderrPath"
"@
  Set-Content -Path $scriptPath -Value $scriptContent -Encoding UTF8
  $commandLine = "`"$cmdPath`" /d /c `"$scriptPath`""
  $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $commandLine
    CurrentDirectory = $WorkingDirectory
  }
  if ([int]$result.ReturnValue -ne 0) {
    throw "Failed to start $Name. Win32_Process.Create returned $($result.ReturnValue)."
  }
  Write-Status "Started $Name on PID $($result.ProcessId)"
  return [pscustomobject]@{
    pid = [int]$result.ProcessId
    stdout = $stdoutPath
    stderr = $stderrPath
    cwd = $WorkingDirectory
    command = $commandLine
  }
}

function Test-TrackedProcessAlive {
  param([object]$Entry)
  if (-not $Entry -or -not $Entry.pid) {
    return $false
  }
  return [bool](Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue)
}

function Save-Metadata {
  param([hashtable]$Metadata)
  $Metadata | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $pidFile
}

function Start-DesktopMode {
  $pythonPath = Get-RequiredCommand -Names @("python", "py")
  $npmPath = Get-RequiredCommand -Names @("npm.cmd", "npm")
  $desktopSrc = Join-Path $repoRoot "apps\desktop\src"
  $serverSrc = Join-Path $repoRoot "apps\server\src"
  $frontendDist = Join-Path $repoRoot "apps\dashboard\dist"
  $desktopLog = Join-Path $launcherDir "desktop.stdout.log"

  if (Test-Path $pidFile) {
    try {
      $existing = Get-Content -Raw $pidFile | ConvertFrom-Json
      if (Test-TrackedProcessAlive -Entry $existing.desktop) {
        Write-Status "Desktop app is already running."
        return
      }
    } catch {
      Write-Status "Existing launcher metadata could not be parsed. Starting fresh."
    }
  }

  if (-not (Test-Path $frontendDist)) {
    Write-Status "Desktop frontend bundle is missing. Building it now..."
    Push-Location (Join-Path $repoRoot "apps\dashboard")
    try {
      & $env:ComSpec /c "`"$npmPath`" run build" | Out-Host
    } finally {
      Pop-Location
    }
  } else {
    Write-Status "Using existing desktop frontend bundle at $frontendDist"
  }

  if (-not (Test-Path $frontendDist)) {
    throw "Desktop frontend build output was not created at $frontendDist"
  }

  $previousPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH", "Process")
  $newPythonPath = if ($previousPythonPath) {
    "$desktopSrc;$serverSrc;$previousPythonPath"
  } else {
    "$desktopSrc;$serverSrc"
  }
  [Environment]::SetEnvironmentVariable("PYTHONPATH", $newPythonPath, "Process")
  [Environment]::SetEnvironmentVariable("MISSION_CONTROL_FRONTEND_DIST", $frontendDist, "Process")
  [Environment]::SetEnvironmentVariable("MISSION_CONTROL_LAUNCHER_DIR", $launcherDir, "Process")
  $powershellPath = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
  $workerScript = Join-Path $launcherDir "desktop.worker.ps1"
  $workerContent = @"
`$ErrorActionPreference = 'Stop'
`$env:PYTHONPATH = '$newPythonPath'
`$env:MISSION_CONTROL_FRONTEND_DIST = '$frontendDist'
`$env:MISSION_CONTROL_LAUNCHER_DIR = '$launcherDir'
Set-Location '$repoRoot'
& '$pythonPath' -m mission_control_desktop *>> '$desktopLog'
"@
  Set-Content -Path $workerScript -Value $workerContent -Encoding UTF8
  & $env:ComSpec /c "start `"`" `"$powershellPath`" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$workerScript`"" | Out-Null

  for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
    Start-Sleep -Milliseconds 250
    if (Test-Path $pidFile) {
      try {
        $desktopMetadata = Get-Content -Raw $pidFile | ConvertFrom-Json
        if (Test-TrackedProcessAlive -Entry $desktopMetadata.desktop) {
          Write-Status "Desktop app started on PID $($desktopMetadata.desktop.pid)"
          return
        }
      } catch {
        continue
      }
    }
  }

  $logTail = if (Test-Path $desktopLog) { Get-Content -Tail 20 $desktopLog | Out-String } else { "" }
  throw "Desktop app did not report a healthy startup. $logTail"
}

function Start-WebMode {
  $pythonPath = Get-RequiredCommand -Names @("python", "py")
  $npmPath = Get-RequiredCommand -Names @("npm.cmd", "npm")
  $backendHealthUrl = "http://${effectiveHost}:${effectiveBackendPort}/api/health"
  $frontendUrl = "http://${effectiveHost}:${effectiveFrontendPort}"
  $startupUrl = "${frontendUrl}/startup"

  $backendHealthy = Test-BackendHealthy
  $frontendHealthy = Test-FrontendHealthy

  if ($backendHealthy -and $frontendHealthy) {
    Write-Status "Backend and frontend are already healthy. Opening the startup route."
    if ($autoOpenBrowser) {
      Start-Process $startupUrl | Out-Null
    }
    return
  }

  if (-not $backendHealthy -and (Test-PortOpen -TargetHost $effectiveHost -Port $effectiveBackendPort)) {
    throw "Port $effectiveBackendPort is already in use, but $backendHealthUrl did not report healthy."
  }

  if (-not $frontendHealthy -and (Test-PortOpen -TargetHost $effectiveHost -Port $effectiveFrontendPort)) {
    throw "Port $effectiveFrontendPort is already in use, but $frontendUrl did not report healthy."
  }

  $metadata = @{
    repoRoot = $repoRoot
    generatedAt = (Get-Date).ToString("o")
    mode = "web"
    backend = $null
    frontend = $null
  }

  if (-not $backendHealthy) {
    $backendCommand = "`"$pythonPath`" -m uvicorn main:app --app-dir src --host $effectiveHost --port $effectiveBackendPort"
    $metadata.backend = Start-TrackedShellProcess `
      -Name "backend" `
      -WorkingDirectory (Join-Path $repoRoot "apps\server") `
      -Command $backendCommand `
      -Hidden
    Write-Status "Waiting for backend health check on $backendHealthUrl"
    Wait-ForHealthy -Probe ${function:Test-BackendHealthy} -Name "Backend"
  } else {
    Write-Status "Backend already healthy on $backendHealthUrl"
  }

  if (-not $frontendHealthy) {
    $frontendCommand = "`"$npmPath`" run dev -- --host $effectiveHost --port $effectiveFrontendPort"
    $metadata.frontend = Start-TrackedShellProcess `
      -Name "frontend" `
      -WorkingDirectory (Join-Path $repoRoot "apps\dashboard") `
      -Command $frontendCommand `
      -Hidden
    Write-Status "Waiting for frontend on $frontendUrl"
    Wait-ForHealthy -Probe ${function:Test-FrontendHealthy} -Name "Frontend"
  } else {
    Write-Status "Frontend already healthy on $frontendUrl"
  }

  Save-Metadata $metadata
  Write-Status "Launcher metadata written to $pidFile"

  if ($autoOpenBrowser) {
    Write-Status "Opening $startupUrl"
    Start-Process $startupUrl | Out-Null
  } else {
    Write-Status "Browser auto-open is disabled. Open $startupUrl manually."
  }
}

if ($Mode -eq "desktop") {
  Start-DesktopMode
} else {
  Start-WebMode
}
