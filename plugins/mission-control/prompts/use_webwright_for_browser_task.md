# Use Webwright For Browser Task

Check the project's Webwright readiness first.
Resource sequence: `mission-control://projects/{project_id}/webwright` -> `mission-control://projects/{project_id}/status`

If Webwright is ready:

- Start the browser task through Mission Control.
- Prefer Webwright for multi-step browser automation, screenshot-backed verification, and reusable scripts.
- Summarize the current orchestration state compactly.

If Webwright is not ready:

- Say exactly what is missing.
- Show the safe install steps.
- Do not pretend browser automation ran.

Ground the answer in the Webwright readiness resource and current Mission Control status, not guesses.
