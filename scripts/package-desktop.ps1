param(
  [switch]$ForceFrontend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $pythonPath) {
  $pythonPath = (Get-Command py -ErrorAction SilentlyContinue)?.Source
}
if (-not $pythonPath) {
  throw "Python was not found on PATH."
}

$arguments = @("scripts/package-desktop.py")
if ($ForceFrontend) {
  $arguments += "--force-frontend"
}

Push-Location $repoRoot
try {
  & $pythonPath @arguments
} finally {
  Pop-Location
}
