from __future__ import annotations

from typing import Any


DELETE_TOKENS = (
    "rm ",
    "rm -",
    "remove-item",
    "rmdir",
    "del ",
    "erase ",
    "git clean",
    "shutil.rmtree",
)
NETWORK_TOKENS = (
    "curl ",
    "wget ",
    "invoke-webrequest",
    "invoke-restmethod",
    "npm install",
    "npm add",
    "pnpm add",
    "pnpm install",
    "yarn add",
    "yarn install",
    "pip install",
    "python -m pip install",
    "poetry add",
    "cargo add",
    "docker pull",
    "docker push",
    "git clone",
    "git fetch",
    "git pull",
    "git push",
)
PACKAGE_TOKENS = (
    "npm install",
    "npm add",
    "pnpm add",
    "pnpm install",
    "yarn add",
    "yarn install",
    "pip install",
    "python -m pip install",
    "poetry add",
    "cargo add",
    "composer require",
    "bundle add",
)
DEPLOY_TOKENS = (
    "vercel",
    "deploy",
    "release",
    "publish",
    "netlify",
    "docker push",
    "kubectl apply",
    "terraform apply",
    "fly deploy",
)
CREDENTIAL_TOKENS = (
    ".env",
    "authorization",
    "bearer",
    "token",
    "secret",
    "password",
    "private key",
    "id_rsa",
    "keychain",
    "credential",
)
LOW_RISK_COMMANDS = ("pytest", "python -m pytest", "npm run build", "vite build", "tsc ", "ruff ", "eslint ", "cargo test")


class RiskClassifier:
    def classify(self, payload: dict[str, Any]) -> dict[str, Any]:
        action_type = str(payload.get("action_type") or "command")
        command = str(payload.get("command") or "").strip()
        tool_name = str(payload.get("tool_name") or "").strip()
        title = str(payload.get("title") or command or tool_name or action_type).strip()
        summary = str(payload.get("summary") or title).strip()
        combined = " ".join(part for part in (action_type, command, tool_name, title, summary) if part).lower()

        external_access_requested = bool(payload.get("external_access_requested"))
        modifies_files = bool(payload.get("modifies_files"))
        modifies_package_files = bool(payload.get("modifies_package_files"))
        deletes_files = bool(payload.get("deletes_files"))
        deploys = bool(payload.get("deploys"))
        accesses_network = bool(payload.get("accesses_network"))
        accesses_credentials = bool(payload.get("accesses_credentials"))
        writes_outside_workspace = bool(payload.get("writes_outside_workspace"))
        affected_paths = [str(item) for item in payload.get("affected_paths_json") or payload.get("affected_paths") or [] if str(item).strip()]

        if any(token in combined for token in DELETE_TOKENS):
            deletes_files = True
            modifies_files = True
        if any(token in combined for token in NETWORK_TOKENS):
            accesses_network = True
        if any(token in combined for token in PACKAGE_TOKENS):
            modifies_package_files = True
            modifies_files = True
            accesses_network = True
        if any(token in combined for token in DEPLOY_TOKENS):
            deploys = True
        if any(token in combined for token in CREDENTIAL_TOKENS):
            accesses_credentials = True
        if action_type in {"plugin", "connected_account"}:
            external_access_requested = True
        if action_type in {"write_permission", "snapshot"}:
            modifies_files = True

        reasons: list[str] = []
        risk_level = "low"
        recommended_policy = "allow_low_risk"

        if writes_outside_workspace:
            reasons.append("Writes outside the project workspace are requested.")
            risk_level = "critical"
            recommended_policy = "deny"
        elif deletes_files:
            reasons.append("The action appears to delete files or folders.")
            risk_level = "critical"
            recommended_policy = "critical_approval"
        elif accesses_credentials:
            reasons.append("The action may access secrets, credentials, or private keys.")
            risk_level = "critical"
            recommended_policy = "deny"
        elif deploys:
            reasons.append("The action appears to deploy, publish, or release changes externally.")
            risk_level = "high"
            recommended_policy = "ask"
        elif external_access_requested:
            reasons.append("The action requests external accounts, plugins, or remote side effects.")
            risk_level = "high"
            recommended_policy = "ask"
        elif modifies_package_files and accesses_network:
            reasons.append("The action changes dependencies and likely reaches the network.")
            risk_level = "high"
            recommended_policy = "ask"
        elif modifies_package_files:
            reasons.append("The action changes package or dependency state.")
            risk_level = "medium"
            recommended_policy = "ask"
        elif accesses_network:
            reasons.append("The action reaches the network or remote services.")
            risk_level = "medium"
            recommended_policy = "ask"
        elif modifies_files:
            reasons.append("The action writes to the local workspace.")
            risk_level = "medium"
            recommended_policy = "ask"
        elif command:
            if any(command.lower().startswith(item) for item in LOW_RISK_COMMANDS):
                reasons.append("The command matches a common local validation or build flow.")
                risk_level = "low"
                recommended_policy = "allow_low_risk"
            else:
                reasons.append("The command is read-only but not confidently classed as a trivial validation step.")
                risk_level = "medium"
                recommended_policy = "ask"
        elif tool_name:
            if any(token in tool_name.lower() for token in ("deploy", "account", "plugin", "sandbox")):
                reasons.append("The tool name implies elevated execution or external access.")
                risk_level = "high"
                recommended_policy = "ask"
            else:
                reasons.append("The tool request looks local and non-destructive.")
                risk_level = "low"
                recommended_policy = "allow_low_risk"
        else:
            reasons.append("No command or tool details were provided, so Mission Control should ask.")
            risk_level = "medium"
            recommended_policy = "ask"

        if not reasons:
            reasons.append("No explicit risk signals were detected.")

        return {
            "project_id": payload.get("project_id"),
            "action_type": action_type,
            "title": title or action_type,
            "summary": summary or title or action_type,
            "risk_level": risk_level,
            "reasons_json": reasons,
            "affected_paths_json": affected_paths,
            "external_access_json": {
                "external_access_requested": external_access_requested,
                "accesses_network": accesses_network,
                "deploys": deploys,
                "accesses_credentials": accesses_credentials,
                "writes_outside_workspace": writes_outside_workspace,
            },
            "recommended_policy": recommended_policy,
            "derived_flags": {
                "modifies_files": modifies_files,
                "modifies_package_files": modifies_package_files,
                "deletes_files": deletes_files,
                "deploys": deploys,
                "accesses_network": accesses_network,
                "accesses_credentials": accesses_credentials,
                "writes_outside_workspace": writes_outside_workspace,
                "external_access_requested": external_access_requested,
            },
        }


risk_classifier = RiskClassifier()
