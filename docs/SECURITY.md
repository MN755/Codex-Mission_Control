# Security

Codex Mission Control is local-only by default.

## Default Safety Model

- Backend is intended to run on localhost.
- Frontend talks only to the local backend.
- The desktop shell embeds that same local surface instead of exposing it publicly.
- Packaged desktop builds keep the same localhost-only backend behavior inside the native shell.
- ChatGPT sign-in is the recommended default path.
- API-key login is optional. Mission Control does not store the raw key in its own database or settings.
- Claude Code and external adapters keep their own local auth flows; Mission Control does not try to proxy or persist their credentials.
- The launcher defaults to `127.0.0.1:8000` for the backend and `127.0.0.1:5173` for the frontend.
- Runner defaults avoid dangerous sandbox bypass flags.
- CLI tasks default to `workspace-write` sandboxing and `on-request` approvals.
- Empty manager or worker model values mean `use provider default`; Mission Control does not write those choices back into global Codex config.

## Workspace Safety

- The system prefers isolated worktrees for git-backed workspaces.
- Non-git workspaces use explicit path reservations to reduce concurrent write collisions.
- Generated planning docs are kept inside `<workspace>/mission-control/`.
- Worker tasks stay in `workspace-write` sandbox mode by default and do not use dangerous bypass flags.
- Role-based model overrides affect only Mission Control runs for that project. They are not global machine settings.
- External adapter commands receive Mission Control context over stdin and environment variables, so review any adapter wrapper before using it on sensitive code.

## Network Exposure

- Do not expose the backend publicly for normal use.
- Do not bind the Codex app-server to non-loopback addresses unless you understand the security implications.
- If the app-server is bound beyond localhost, add real transport authentication and treat the surface as sensitive.

## Operational Limits

- The MVP surfaces environment-dependent risks instead of pretending they are solved.
- If a runner needs additional access or approvals, the intended behavior is to stop and report it.
- Validation results should only reflect commands that actually ran.
- App-server integration should still be treated as experimental even when the handshake succeeds.
- Model availability still depends on the selected local provider session and plan; a configured override may fail if the local account cannot use that model.
- API-key login can shift usage onto API-billed credentials. Use ChatGPT sign-in if you want to stay on the local Codex or ChatGPT session path instead.
- Packaged artifacts are unsigned unless you add platform-specific signing and notarization later.
- Linux AppImage generation depends on `appimagetool`; otherwise the build falls back to a portable bundle archive.
