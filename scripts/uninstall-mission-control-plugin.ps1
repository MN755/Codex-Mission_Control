param(
  [string]$CodexHome = "",
  [switch]$DryRun,
  [switch]$Json,
  [switch]$NoStopDaemon
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
$scriptPath = Join-Path $PSScriptRoot "mission-control-manage.py"
if (-not (Test-Path $scriptPath)) {
  throw "Manage script not found: $scriptPath"
}

$arguments = @($scriptPath, "uninstall")
if ($CodexHome) { $arguments += @("--codex-home", $CodexHome) }
if ($DryRun) { $arguments += "--dry-run" }
if ($Json) { $arguments += "--json" }
if ($NoStopDaemon) { $arguments += "--no-stop-daemon" }

& $pythonPath @arguments
