# Generate AGENTS Md Proposal

Purpose: produce a chat-friendly AGENTS.md proposal from Mission Control's codebase understanding.
Arguments: `PROJECT_ID`
Tool sequence: `mission_control_get_codebase_map` -> `mission_control_get_agents_md_status` -> `mission_control_generate_agents_md`
Expected output: AGENTS.md status, recommended path, and proposal summary.
Safety: ask before writing or replacing `AGENTS.md`.
