param(
  [switch]$Json,
  [switch]$Serve
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) {
  $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
  throw "Python is required to verify the Mission Control MCP bridge."
}

$bootstrapScript = Join-Path $repoRoot "scripts\mission-control-bootstrap.py"
$configPath = Join-Path $repoRoot "scripts\mission-control.config.json"

function Get-LauncherConfig {
  if ($env:MISSION_CONTROL_LAUNCHER_CONFIG -and (Test-Path $env:MISSION_CONTROL_LAUNCHER_CONFIG)) {
    return Get-Content -Raw $env:MISSION_CONTROL_LAUNCHER_CONFIG | ConvertFrom-Json
  }
  if (Test-Path $configPath) {
    return Get-Content -Raw $configPath | ConvertFrom-Json
  }
  return [pscustomobject]@{
    host = "127.0.0.1"
    backendPort = 8010
  }
}

if ($Serve) {
  $launcherConfig = Get-LauncherConfig
  $env:MISSION_CONTROL_REPO_ROOT = $repoRoot
  if (-not $env:MISSION_CONTROL_BACKEND_HOST) {
    $env:MISSION_CONTROL_BACKEND_HOST = [string]$launcherConfig.host
  }
  if (-not $env:MISSION_CONTROL_BACKEND_PORT) {
    $env:MISSION_CONTROL_BACKEND_PORT = [string]$launcherConfig.backendPort
  }
  $mcpRoot = Join-Path $repoRoot "apps\mcp-server"
  $env:PYTHONPATH = Join-Path $mcpRoot "src"
  Push-Location $mcpRoot
  try {
    & $python.Source -m mission_control_mcp_server
  } finally {
    Pop-Location
  }
} else {
  $arguments = @($bootstrapScript, "--install-path", $repoRoot, "--mcp-check-only")
  if ($Json) {
    $arguments += "--json"
  }

  & $python.Source @arguments
}
