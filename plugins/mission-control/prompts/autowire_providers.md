# Autowire Providers

Purpose: probe safe local runners and provider config, then summarize ready and degraded runner paths.
Arguments: `WORKSPACE_PATH`
Tool sequence: `mission_control_plugin_health`
Expected output: ready runners, degraded runners, unavailable runners, and specific setup steps.
Safety: local-first. Do not silently use billed API providers or print secrets.
