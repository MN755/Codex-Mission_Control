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

if ($Serve) {
  $env:MISSION_CONTROL_REPO_ROOT = $repoRoot
  if (-not $env:MISSION_CONTROL_BACKEND_HOST) {
    $env:MISSION_CONTROL_BACKEND_HOST = "127.0.0.1"
  }
  if (-not $env:MISSION_CONTROL_BACKEND_PORT) {
    $env:MISSION_CONTROL_BACKEND_PORT = "8000"
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
