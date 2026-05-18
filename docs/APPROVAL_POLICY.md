# Approval Policy

Mission Control approvals exist to slow down dangerous actions on purpose. That friction is the feature.

## Policy scopes

- `global`: default posture for the app
- `project`: project-specific override when a workspace needs stricter or looser handling

## SecurityPolicy fields

- `default_command_policy`: `ask`, `allow_low_risk`, `deny`
- `default_tool_policy`: `ask`, `allow_low_risk`, `deny`
- `network_access_policy`: `ask`, `allow`, `deny`
- `write_access_policy`: `read_only`, `workspace_write`, `limited_paths`
- `external_account_policy`: `ask`, `deny`
- `deployment_policy`: `ask`, `deny`
- `destructive_action_policy`: `deny`, `critical_approval`
- `auto_approve_low_risk`: whether low-risk actions may auto-approve
- `auto_approve_medium_risk`: whether medium-risk actions may auto-approve when policy permits
- `high_risk_requires_user`: whether high-risk actions always need explicit user approval

## Default posture

The intended defaults are conservative:

- commands: `ask`
- tools: `ask`
- network: `ask`
- writes: `workspace_write`
- external accounts: `ask`
- deployments: `deny`
- destructive actions: `critical_approval`
- low-risk auto-approval: off
- medium-risk auto-approval: off
- high-risk explicit user approval: on

## Risk levels

### Low

Expected local validation or inspection with no destructive behavior.

Examples:

- `python -m pytest`
- local build or lint commands
- read-only local tooling with no credential access

### Medium

Local writes or network behavior that are not clearly destructive but still deserve review in many projects.

Examples:

- non-package workspace edits
- networked read operations
- unfamiliar read-only commands that are not obviously trivial

### High

External side effects, dependency changes, deployments, or actions that meaningfully widen the blast radius.

Examples:

- `npm install`
- plugin actions with remote side effects
- connected-account actions
- deployments

### Critical

Actions that can destroy data, escape workspace boundaries, or expose credentials.

Examples:

- `rm -rf`
- writes outside the workspace
- reading `.env` or private keys
- direct secret access

## Audit decisions

Mission Control records:

- `approved`
- `denied`
- `allowed_for_project`
- `expired`
- `auto_approved`
- `blocked`

Each entry stores:

- action type
- risk level
- decision actor
- reason
- redacted metadata

## Rules that matter

- High-risk and critical actions do not become project-wide blanket approvals.
- Risk classification is deterministic and does not execute the action.
- Redaction happens before audit data is stored or displayed.
- Plugin or connected-account requests are treated as side-effectful, not as harmless UI clicks.
