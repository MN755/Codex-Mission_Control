param(
  [string]$CodexHome = "",
  [switch]$DryRun,
  [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PythonCommand {
  foreach ($name in @("python", "py")) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }
  throw "Python was not found on PATH."
}

$pythonPath = Get-PythonCommand
$scriptPath = Join-Path $PSScriptRoot "uninstall-mission-control-plugin.py"
if (-not (Test-Path $scriptPath)) {
  throw "Uninstall script not found: $scriptPath"
}

$arguments = @($scriptPath)
if ($CodexHome) { $arguments += @("--codex-home", $CodexHome) }
if ($DryRun) { $arguments += "--dry-run" }
if ($Json) { $arguments += "--json" }

& $pythonPath @arguments
