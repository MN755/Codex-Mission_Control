param(
  [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) {
  $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
  throw "Python is required to run Mission Control headless health checks."
}

$bootstrapScript = Join-Path $repoRoot "scripts\mission-control-bootstrap.py"
$arguments = @($bootstrapScript, "--install-path", $repoRoot, "--health-check-only")
if ($Json) {
  $arguments += "--json"
}

& $python.Source @arguments
