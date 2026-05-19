param(
  [string]$RepoUrl = "https://github.com/MN755/Codex-Mission_Control",
  [string]$InstallDir = "$env:LOCALAPPDATA\MissionControl",
  [string]$CodexHome = "",
  [switch]$HeadlessOnly,
  [switch]$DryRun,
  [switch]$Repair,
  [switch]$HealthCheckOnly,
  [switch]$SkipCodexSync
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $candidate = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
  if ((Test-Path (Join-Path $candidate "apps\server\src")) -and (Test-Path (Join-Path $candidate "README.md"))) {
    return $candidate
  }
  $target = [System.IO.Path]::GetFullPath($InstallDir)
  if (-not (Test-Path $target)) {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
      throw "git is required to clone Mission Control into $target."
    }
    Write-Host "[Mission Control] Cloning repository into $target"
    & $git.Source clone $RepoUrl $target
  }
  if (-not (Test-Path (Join-Path $target "apps\server\src")) -or -not (Test-Path (Join-Path $target "README.md"))) {
    throw "Install target '$target' does not look like a Codex Mission Control checkout."
  }
  return $target
}

function Get-PythonCommand {
  foreach ($name in @("python", "py")) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }
  throw "Python was not found on PATH."
}

function Resolve-CodexHome {
  if ($CodexHome) {
    return [System.IO.Path]::GetFullPath($CodexHome)
  }
  if ($env:CODEX_HOME) {
    return [System.IO.Path]::GetFullPath($env:CODEX_HOME)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $HOME ".codex"))
}

function Copy-RepoTree {
  param(
    [string]$Source,
    [string]$Destination
  )

  if (-not (Test-Path $Source)) {
    return
  }

  $null = New-Item -ItemType Directory -Path $Destination -Force
  Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

$repoRoot = Resolve-RepoRoot
$pythonPath = Get-PythonCommand
$bootstrapScript = Join-Path $repoRoot "scripts\mission-control-bootstrap.py"
if (-not (Test-Path $bootstrapScript)) {
  throw "Bootstrap script not found: $bootstrapScript"
}

if (-not $SkipCodexSync) {
  $resolvedCodexHome = Resolve-CodexHome
  $pluginSource = Join-Path $repoRoot ".codex\plugins\mission-control"
  if (-not (Test-Path $pluginSource)) {
    $pluginSource = Join-Path $repoRoot "plugins\mission-control"
  }
  $pluginDestination = Join-Path $resolvedCodexHome "plugins\mission-control"
  $skillsSourceRoot = Join-Path $repoRoot ".codex\skills"
  $skillsDestinationRoot = Join-Path $resolvedCodexHome "skills"

  Write-Host "[Mission Control] Syncing Codex plugin bundle to $pluginDestination"
  Copy-RepoTree -Source $pluginSource -Destination $pluginDestination

  if (Test-Path $skillsSourceRoot) {
    $skillDirectories = Get-ChildItem $skillsSourceRoot -Directory | Where-Object { $_.Name -like "mission-control*" }
    foreach ($skillDirectory in $skillDirectories) {
      $target = Join-Path $skillsDestinationRoot $skillDirectory.Name
      Write-Host "[Mission Control] Syncing skill $($skillDirectory.Name) to $target"
      Copy-RepoTree -Source $skillDirectory.FullName -Destination $target
    }
  }
}

$arguments = @($bootstrapScript, "--install-path", $repoRoot)
if ($HeadlessOnly) { $arguments += "--headless-only" }
if ($DryRun) { $arguments += "--dry-run" }
if ($Repair) { $arguments += "--repair" }
if ($HealthCheckOnly) { $arguments += "--health-check-only" }

Write-Host "[Mission Control] Running headless bootstrap from $repoRoot"
& $pythonPath @arguments
