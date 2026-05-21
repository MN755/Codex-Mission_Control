param(
  [string]$RepoUrl = "https://github.com/MN755/Codex-Mission_Control",
  [string]$InstallDir = "",
  [string]$CodexHome = "",
  [switch]$DryRun,
  [switch]$SkipCodexSync,
  [switch]$SkipPythonSetup,
  [string]$PythonCommand = "",
  [string]$DaemonHost = "",
  [int]$DaemonPort
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
$manageScript = Join-Path $PSScriptRoot "mission-control-manage.py"
if (-not (Test-Path $manageScript)) {
  throw "Manage script not found: $manageScript"
}

$arguments = @($manageScript, "update", "--repo-url", $RepoUrl)
if ($InstallDir) { $arguments += @("--install-dir", $InstallDir) }
if ($CodexHome) { $arguments += @("--codex-home", $CodexHome) }
if ($DryRun) { $arguments += "--dry-run" }
if ($SkipCodexSync) { $arguments += "--skip-codex-sync" }
if ($SkipPythonSetup) { $arguments += "--skip-python-setup" }
if ($PythonCommand) { $arguments += @("--python-command", $PythonCommand) }
if ($DaemonHost) { $arguments += @("--daemon-host", $DaemonHost) }
if ($PSBoundParameters.ContainsKey("DaemonPort")) { $arguments += @("--daemon-port", $DaemonPort) }

Write-Host "[Mission Control] Running unified update workflow"
& $pythonPath @arguments
