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
  throw "Python is required to generate a Mission Control support bundle."
}

$scriptPath = Join-Path $repoRoot "scripts\mission-control-support-bundle.py"
$arguments = @($scriptPath)
if ($Json) {
  $arguments += "--json"
}

& $python.Source @arguments
