param(
    [int]$ProjectId,
    [int]$OrchestrationId,
    [string]$WorkspacePath,
    [ValidateSet("reuse_existing", "create_new")]
    [string]$AttachPolicy = "reuse_existing",
    [ValidateSet("last_5_minutes", "last_15_minutes", "since_last_user_interaction", "since_orchestration_start")]
    [string]$EventWindow = "since_orchestration_start",
    [double]$RefreshSeconds = 1.0,
    [switch]$Once,
    [switch]$NoAnsi
)

if (-not $WorkspacePath -and (-not $ProjectId -or -not $OrchestrationId)) {
    throw "Provide -WorkspacePath, or both -ProjectId and -OrchestrationId."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot "mission-control-manage.py"
$pythonCommand = if ($env:MISSION_CONTROL_PYTHON) {
    $env:MISSION_CONTROL_PYTHON
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
}
else {
    throw "python was not found on PATH. Set MISSION_CONTROL_PYTHON or install Python."
}

$refreshText = [System.Globalization.CultureInfo]::InvariantCulture.TextInfo.ToLower($RefreshSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture))
$arguments = @(
    $scriptPath,
    "orchestration-display",
    "--install-dir", $repoRoot,
    "--refresh-seconds", $refreshText,
    "--attach-policy", $AttachPolicy,
    "--event-window", $EventWindow
)

if ($ProjectId) {
    $arguments += @("--project-id", $ProjectId.ToString())
}
if ($OrchestrationId) {
    $arguments += @("--orchestration-id", $OrchestrationId.ToString())
}
if ($WorkspacePath) {
    $arguments += @("--workspace-path", $WorkspacePath)
}
if ($Once) {
    $arguments += "--once"
}
if ($NoAnsi) {
    $arguments += "--no-ansi"
}

& $pythonCommand @arguments
exit $LASTEXITCODE
