from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import REPO_ROOT, get_codex_home


REGISTRY_VERSION = 1
INTEGRATION_REGISTRY_KEY = "integration_registry_json"
LEGACY_CONNECTION_SOURCES = {"legacy_connected_accounts", "manual", "codex_host", "claude_code_host", "mission_control"}
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "artifacts",
}


@dataclass(frozen=True)
class IntegrationActionDefinition:
    action_id: str
    title: str
    summary: str
    command_template: str | None = None
    risk_level: str = "medium"
    permission_policy: str = "ask_every_time"
    preview_supported: bool = True
    mutates_remote_state: bool = False
    requires_confirmation: bool = False
    required_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntegrationFamilyDefinition:
    family_id: str
    name: str
    summary: str
    category: str
    providers: tuple[str, ...]
    host_tokens: tuple[str, ...]
    config_files: tuple[str, ...]
    workspace_tokens: tuple[str, ...]
    cli_candidates: tuple[str, ...]
    legacy_account_keys: tuple[str, ...]
    actions: tuple[IntegrationActionDefinition, ...]


COMMON_ACTIONS = (
    IntegrationActionDefinition(
        action_id="import_host_state",
        title="Import host state",
        summary="Import any Codex or Claude-discovered integration metadata into the Mission Control registry.",
        risk_level="low",
        permission_policy="ask_once_per_project",
        preview_supported=True,
        mutates_remote_state=False,
        requires_confirmation=False,
    ),
    IntegrationActionDefinition(
        action_id="inspect_status",
        title="Inspect status",
        summary="Inspect local runtime, host import state, or workspace signals for this integration family.",
        risk_level="low",
        permission_policy="ask_once_per_project",
        preview_supported=True,
        mutates_remote_state=False,
        requires_confirmation=False,
    ),
    IntegrationActionDefinition(
        action_id="connect",
        title="Connect",
        summary="Record or refresh connection guidance for this family under Mission Control.",
        risk_level="medium",
        permission_policy="ask_every_time",
        preview_supported=True,
        mutates_remote_state=False,
        requires_confirmation=False,
    ),
)


def _action(
    action_id: str,
    title: str,
    summary: str,
    *,
    command_template: str | None = None,
    risk_level: str = "medium",
    permission_policy: str = "ask_every_time",
    preview_supported: bool = True,
    mutates_remote_state: bool = False,
    requires_confirmation: bool = False,
    required_params: tuple[str, ...] = (),
) -> IntegrationActionDefinition:
    return IntegrationActionDefinition(
        action_id=action_id,
        title=title,
        summary=summary,
        command_template=command_template,
        risk_level=risk_level,
        permission_policy=permission_policy,
        preview_supported=preview_supported,
        mutates_remote_state=mutates_remote_state,
        requires_confirmation=requires_confirmation,
        required_params=required_params,
    )


FAMILIES: tuple[IntegrationFamilyDefinition, ...] = (
    IntegrationFamilyDefinition(
        family_id="source_control",
        name="GitHub / GitLab / Bitbucket",
        summary="Source-control and repository-host integration lane.",
        category="delivery",
        providers=("github", "gitlab", "bitbucket"),
        host_tokens=("github", "gitlab", "bitbucket"),
        config_files=(".github/workflows", ".gitlab-ci.yml", "bitbucket-pipelines.yml"),
        workspace_tokens=("github", "gitlab", "bitbucket"),
        cli_candidates=("gh", "glab"),
        legacy_account_keys=("github",),
        actions=COMMON_ACTIONS + (
            _action("search", "Search repos", "Inspect repo host metadata or issue state.", command_template="gh repo view --json name,defaultBranchRef", risk_level="low", permission_policy="ask_once_per_project"),
            _action("create", "Create issue", "Create a work item against the connected source host.", command_template='gh issue create --title "{title}" --body "{body}"', mutates_remote_state=True, requires_confirmation=True, required_params=("title", "body")),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="work_tracking",
        name="Linear / Jira / GitHub Issues",
        summary="Planning and issue-tracking integration lane.",
        category="planning",
        providers=("linear", "jira", "github_issues"),
        host_tokens=("linear", "jira", "issues"),
        config_files=(".linear", ".jira",),
        workspace_tokens=("linear", "jira", "github issue"),
        cli_candidates=("gh",),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("search", "Search work items", "Inspect tracked work items from the current host or CLI.", command_template="gh issue list --limit 20", risk_level="low", permission_policy="ask_once_per_project"),
            _action("create", "Create work item", "Create a tracked work item.", command_template='gh issue create --title "{title}" --body "{body}"', mutates_remote_state=True, requires_confirmation=True, required_params=("title", "body")),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="containers",
        name="Docker / Dev Containers",
        summary="Container runtime and devcontainer integration lane.",
        category="runtime",
        providers=("docker", "devcontainer"),
        host_tokens=("docker", "devcontainer"),
        config_files=("Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".devcontainer/devcontainer.json"),
        workspace_tokens=("docker", "devcontainer"),
        cli_candidates=("docker", "devcontainer"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("validate", "Validate container lane", "Inspect Docker or devcontainer readiness.", command_template="docker --version", risk_level="low", permission_policy="ask_once_per_project"),
            _action("open", "Open dev container", "Open or rebuild the active dev container.", command_template="devcontainer up --workspace-folder .", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="ci_cd",
        name="CI/CD Platforms",
        summary="Build and CI pipeline integration lane.",
        category="delivery",
        providers=("github_actions", "gitlab_ci", "bitbucket_pipelines", "buildkite", "circleci"),
        host_tokens=("workflow", "pipeline", "ci"),
        config_files=(".github/workflows", ".gitlab-ci.yml", "bitbucket-pipelines.yml", ".circleci/config.yml"),
        workspace_tokens=("workflow", "pipeline", "ci"),
        cli_candidates=("gh",),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect CI status", "Inspect CI workflow status.", command_template="gh run list --limit 10", risk_level="low", permission_policy="ask_once_per_project"),
            _action("rerun", "Rerun pipeline", "Rerun the most recent CI pipeline.", command_template="gh run rerun {run_id}", mutates_remote_state=True, requires_confirmation=True, required_params=("run_id",)),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="hosting_deploy",
        name="Vercel / Netlify / Cloudflare Pages / Railway / Render",
        summary="Application hosting and deployment-platform integration lane.",
        category="deployment",
        providers=("vercel", "netlify", "cloudflare_pages", "railway", "render"),
        host_tokens=("vercel", "netlify", "cloudflare", "railway", "render"),
        config_files=("vercel.json", "netlify.toml", "wrangler.toml", "railway.json", "render.yaml"),
        workspace_tokens=("vercel", "netlify", "cloudflare pages", "railway", "render"),
        cli_candidates=("vercel", "netlify", "wrangler"),
        legacy_account_keys=("vercel",),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect deployment", "Inspect deployment readiness or latest deployments.", command_template="vercel whoami", risk_level="low", permission_policy="ask_once_per_project"),
            _action("deploy", "Deploy", "Trigger a deployment through the configured hosting CLI.", command_template="vercel deploy --yes", risk_level="high", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="database_platforms",
        name="Supabase / Firebase / Neon / PlanetScale",
        summary="Database and backend-platform integration lane.",
        category="data",
        providers=("supabase", "firebase", "neon", "planetscale"),
        host_tokens=("supabase", "firebase", "neon", "planetscale"),
        config_files=("supabase/config.toml", "firebase.json", "neon.json", "pscale.yml"),
        workspace_tokens=("supabase", "firebase", "neon", "planetscale"),
        cli_candidates=("supabase", "firebase"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect platform", "Inspect platform project or auth status.", command_template="supabase projects list", risk_level="low", permission_policy="ask_once_per_project"),
            _action("sync", "Sync schema", "Apply or preview backend schema changes.", command_template="supabase db push", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="observability",
        name="Sentry / LogRocket / Datadog / New Relic",
        summary="Error, trace, and session-observability integration lane.",
        category="observability",
        providers=("sentry", "logrocket", "datadog", "new_relic"),
        host_tokens=("sentry", "logrocket", "datadog", "newrelic", "new relic"),
        config_files=("sentry.properties", "datadog.yaml", "newrelic.js"),
        workspace_tokens=("sentry", "logrocket", "datadog", "newrelic"),
        cli_candidates=("sentry-cli",),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect release health", "Inspect release or issue health.", command_template="sentry-cli info", risk_level="low", permission_policy="ask_once_per_project"),
            _action("tail", "Tail telemetry", "Open a telemetry tail or release-state view.", risk_level="medium", permission_policy="ask_every_time"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="figma",
        name="Figma",
        summary="Design-file and design-system integration lane.",
        category="design",
        providers=("figma",),
        host_tokens=("figma",),
        config_files=(),
        workspace_tokens=("figma",),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect design context", "Inspect Figma connection and design-export readiness.", risk_level="low", permission_policy="ask_once_per_project"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="chatops",
        name="Slack / Discord / Microsoft Teams",
        summary="Team-chat and ChatOps integration lane.",
        category="communication",
        providers=("slack", "discord", "teams"),
        host_tokens=("slack", "discord", "teams"),
        config_files=(),
        workspace_tokens=("slack", "discord", "teams"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("draft", "Draft message", "Prepare a ChatOps message for approval or delivery.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("create", "Send message", "Send a ChatOps message through the configured integration.", mutates_remote_state=True, requires_confirmation=True, required_params=("message",)),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="docs_systems",
        name="Documentation Systems",
        summary="Notion / Confluence / Mintlify / Docusaurus integration lane.",
        category="docs",
        providers=("notion", "confluence", "mintlify", "docusaurus"),
        host_tokens=("notion", "confluence", "mintlify", "docusaurus"),
        config_files=("mint.json", "docusaurus.config.js", "docusaurus.config.ts", "docusaurus.config.mjs"),
        workspace_tokens=("notion", "confluence", "mintlify", "docusaurus"),
        cli_candidates=("mintlify",),
        legacy_account_keys=("notion",),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect docs lane", "Inspect docs build or sync readiness.", command_template="mintlify --help", risk_level="low", permission_policy="ask_once_per_project"),
            _action("sync", "Sync docs", "Publish or sync documentation changes.", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="kubernetes",
        name="Kubernetes",
        summary="Cluster and workload integration lane.",
        category="infrastructure",
        providers=("kubernetes",),
        host_tokens=("kubernetes", "k8s"),
        config_files=("k8s", "kubernetes", "helm"),
        workspace_tokens=("kubectl", "helm", "kubernetes"),
        cli_candidates=("kubectl", "helm"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect cluster", "Inspect current cluster context and workload state.", command_template="kubectl config current-context", risk_level="low", permission_policy="ask_once_per_project"),
            _action("deploy", "Apply manifests", "Apply Kubernetes manifests.", command_template="kubectl apply -f {path}", risk_level="high", mutates_remote_state=True, requires_confirmation=True, required_params=("path",)),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="terraform",
        name="Terraform / OpenTofu",
        summary="Infrastructure-as-code planning and apply lane.",
        category="infrastructure",
        providers=("terraform", "opentofu"),
        host_tokens=("terraform", "tofu", "opentofu"),
        config_files=("main.tf", "versions.tf", "terraform.tfvars", "tofu.hcl"),
        workspace_tokens=("terraform", "opentofu"),
        cli_candidates=("terraform", "tofu"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("validate", "Validate plan", "Validate Terraform/OpenTofu configuration.", command_template="terraform validate", risk_level="low", permission_policy="ask_once_per_project"),
            _action("deploy", "Apply plan", "Apply Terraform/OpenTofu changes.", command_template="terraform apply -auto-approve", risk_level="high", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="cloud_platforms",
        name="AWS / Azure / Google Cloud",
        summary="Cloud-platform integration lane.",
        category="cloud",
        providers=("aws", "azure", "gcp"),
        host_tokens=("aws", "azure", "gcp", "google cloud"),
        config_files=(".aws", ".azure", "gcloud"),
        workspace_tokens=("aws", "azure", "gcp", "google cloud"),
        cli_candidates=("aws", "az", "gcloud"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect cloud auth", "Inspect active cloud CLI auth and project context.", command_template="aws sts get-caller-identity", risk_level="low", permission_policy="ask_once_per_project"),
            _action("open", "Open cloud context", "Open or refresh cloud provider context.", risk_level="medium", permission_policy="ask_every_time"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="api_clients",
        name="Postman / Insomnia / Bruno",
        summary="API-client and request-collection integration lane.",
        category="api",
        providers=("postman", "insomnia", "bruno"),
        host_tokens=("postman", "insomnia", "bruno"),
        config_files=("postman", "insomnia", "bruno"),
        workspace_tokens=("postman", "insomnia", "bruno"),
        cli_candidates=("bruno",),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect collections", "Inspect API collection assets and runtime support.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("validate", "Run collection", "Run API collection checks.", mutates_remote_state=False, requires_confirmation=False),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="openapi",
        name="OpenAPI / Swagger",
        summary="API-schema and contract validation lane.",
        category="api",
        providers=("openapi", "swagger"),
        host_tokens=("openapi", "swagger"),
        config_files=("openapi.yaml", "openapi.yml", "swagger.yaml", "swagger.yml", "openapi.json"),
        workspace_tokens=("openapi", "swagger"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect spec", "Inspect OpenAPI/Swagger contract assets.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("validate", "Validate spec", "Validate an API schema or contract.", mutates_remote_state=False, requires_confirmation=False),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="browser_testing",
        name="Playwright / Cypress",
        summary="Browser automation and E2E testing lane.",
        category="testing",
        providers=("playwright", "cypress"),
        host_tokens=("playwright", "cypress"),
        config_files=("playwright.config.ts", "playwright.config.js", "cypress.config.ts", "cypress.config.js"),
        workspace_tokens=("playwright", "cypress"),
        cli_candidates=("playwright", "cypress"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("validate", "Run browser tests", "Run project browser tests.", command_template="playwright test", risk_level="medium", permission_policy="ask_every_time"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="storybook",
        name="Storybook",
        summary="Component preview and UI-contract integration lane.",
        category="testing",
        providers=("storybook",),
        host_tokens=("storybook",),
        config_files=(".storybook/main.js", ".storybook/main.ts"),
        workspace_tokens=("storybook",),
        cli_candidates=("storybook",),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("validate", "Run Storybook checks", "Run Storybook smoke or build validation.", mutates_remote_state=False, requires_confirmation=False),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="package_registries",
        name="Package Registries",
        summary="Package publish and registry integration lane.",
        category="supply_chain",
        providers=("npm", "pypi", "maven", "crates", "nuget", "rubygems", "docker_hub"),
        host_tokens=("npm", "pypi", "maven", "crates", "nuget", "rubygems", "docker"),
        config_files=("package.json", "pyproject.toml", "Cargo.toml", "pom.xml", ".npmrc"),
        workspace_tokens=("npm", "pypi", "maven", "crates", "nuget", "rubygems"),
        cli_candidates=("npm", "python", "cargo", "docker"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect publish lane", "Inspect package publishing readiness.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("publish", "Publish package", "Publish to the configured package registry.", risk_level="high", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="security_scanners",
        name="Security Scanners",
        summary="Security scanning and code-vulnerability integration lane.",
        category="security",
        providers=("snyk", "semgrep", "codeql", "trivy", "gitleaks", "dependabot"),
        host_tokens=("snyk", "semgrep", "codeql", "trivy", "gitleaks", "dependabot"),
        config_files=(".semgrep", ".github/codeql", ".gitleaks.toml", "trivy.yaml"),
        workspace_tokens=("snyk", "semgrep", "codeql", "trivy", "gitleaks", "dependabot"),
        cli_candidates=("snyk", "semgrep", "trivy", "gitleaks"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("scan", "Run scan", "Run the configured security scanner lane.", command_template="gitleaks dir . --redact", risk_level="medium", permission_policy="ask_every_time"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="local_model_runtimes",
        name="Local Model Runtimes",
        summary="Local AI runtime discovery and routing lane.",
        category="ai",
        providers=("ollama", "lm_studio", "vllm"),
        host_tokens=("ollama", "lm studio", "vllm"),
        config_files=(),
        workspace_tokens=("ollama", "lm studio", "vllm"),
        cli_candidates=("ollama", "vllm"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect runtime", "Inspect local model runtime availability.", command_template="ollama list", risk_level="low", permission_policy="ask_once_per_project"),
            _action("open", "Open runtime", "Open or refresh the local model runtime lane.", risk_level="medium", permission_policy="ask_every_time"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="vector_databases",
        name="Vector Databases",
        summary="Vector-index and retrieval-store integration lane.",
        category="ai",
        providers=("pinecone", "weaviate", "qdrant", "chroma", "milvus"),
        host_tokens=("pinecone", "weaviate", "qdrant", "chroma", "milvus"),
        config_files=(),
        workspace_tokens=("pinecone", "weaviate", "qdrant", "chroma", "milvus"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect vector store", "Inspect vector database config and readiness.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("search", "Test query", "Run a retrieval smoke query.", risk_level="medium", permission_policy="ask_every_time"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="code_search",
        name="Code Search Engines",
        summary="External code-search integration lane.",
        category="search",
        providers=("sourcegraph", "opengrok", "zoekt"),
        host_tokens=("sourcegraph", "opengrok", "zoekt"),
        config_files=(),
        workspace_tokens=("sourcegraph", "opengrok", "zoekt"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("search", "Search code", "Run a code-search query through the configured engine.", risk_level="low", permission_policy="ask_once_per_project"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="browser_devtools",
        name="Browser DevTools / Chrome Debug Protocol",
        summary="DevTools and CDP integration lane.",
        category="testing",
        providers=("chrome_devtools", "cdp"),
        host_tokens=("chrome", "devtools", "cdp"),
        config_files=(),
        workspace_tokens=("devtools", "cdp"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect browser runtime", "Inspect DevTools/CDP readiness.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("open", "Open browser lane", "Open a browser debugging lane.", risk_level="medium", permission_policy="ask_every_time"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="payments",
        name="Stripe / Paddle / Lemon Squeezy / PayPal Sandbox",
        summary="Payments and checkout-sandbox integration lane.",
        category="product",
        providers=("stripe", "paddle", "lemon_squeezy", "paypal_sandbox"),
        host_tokens=("stripe", "paddle", "lemon", "paypal"),
        config_files=(),
        workspace_tokens=("stripe", "paddle", "lemon", "paypal"),
        cli_candidates=("stripe",),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect payment sandbox", "Inspect sandbox auth and webhook readiness.", command_template="stripe config --list", risk_level="low", permission_policy="ask_once_per_project"),
            _action("create", "Create test artifact", "Create a sandbox payment artifact.", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="auth_providers",
        name="Auth Providers",
        summary="Identity and authentication provider integration lane.",
        category="product",
        providers=("auth0", "clerk", "workos", "okta", "firebase_auth", "supabase_auth"),
        host_tokens=("auth0", "clerk", "workos", "okta", "firebase auth", "supabase auth"),
        config_files=(),
        workspace_tokens=("auth0", "clerk", "workos", "okta", "firebase auth", "supabase auth"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect auth config", "Inspect provider auth config and runtime expectations.", risk_level="low", permission_policy="ask_once_per_project"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="secrets",
        name="Secrets Managers",
        summary="Secret-management integration lane.",
        category="security",
        providers=("onepassword", "doppler", "vault", "aws_secrets_manager", "gcp_secret_manager"),
        host_tokens=("1password", "doppler", "vault", "secret manager"),
        config_files=(),
        workspace_tokens=("doppler", "vault", "secret manager"),
        cli_candidates=("doppler", "vault"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect secret lanes", "Inspect available secret-manager configuration.", risk_level="low", permission_policy="ask_once_per_project"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="feature_flags",
        name="Feature Flag Platforms",
        summary="Feature-flag and runtime-config integration lane.",
        category="product",
        providers=("launchdarkly", "statsig", "configcat", "unleash", "posthog_feature_flags"),
        host_tokens=("launchdarkly", "statsig", "configcat", "unleash", "posthog"),
        config_files=(),
        workspace_tokens=("launchdarkly", "statsig", "configcat", "unleash", "posthog"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect flags", "Inspect feature-flag configuration and environment targeting.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("sync", "Sync flags", "Sync feature-flag metadata or environments.", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="analytics",
        name="Analytics Platforms",
        summary="Analytics integration lane.",
        category="product",
        providers=("posthog", "amplitude", "mixpanel", "plausible"),
        host_tokens=("posthog", "amplitude", "mixpanel", "plausible"),
        config_files=(),
        workspace_tokens=("posthog", "amplitude", "mixpanel", "plausible"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect analytics", "Inspect analytics configuration and event surface.", risk_level="low", permission_policy="ask_once_per_project"),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="support_desk",
        name="Knowledge Base / Support Desk",
        summary="Support-desk and knowledge-base integration lane.",
        category="support",
        providers=("intercom", "zendesk", "help_scout", "freshdesk"),
        host_tokens=("intercom", "zendesk", "help scout", "freshdesk"),
        config_files=(),
        workspace_tokens=("intercom", "zendesk", "help scout", "freshdesk"),
        cli_candidates=(),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("search", "Search tickets", "Search support or knowledge-base state.", risk_level="low", permission_policy="ask_once_per_project"),
            _action("create", "Create ticket", "Create a support artifact.", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
    IntegrationFamilyDefinition(
        family_id="release_management",
        name="Release Management / Changelog Tools",
        summary="Release and changelog automation lane.",
        category="release",
        providers=("release_please", "changesets", "semantic_release", "github_releases", "launchnotes"),
        host_tokens=("release please", "changesets", "semantic-release", "github releases", "launchnotes"),
        config_files=(".release-please-manifest.json", ".changeset", ".releaserc", "release.config.js"),
        workspace_tokens=("release please", "changesets", "semantic-release", "launchnotes"),
        cli_candidates=("gh", "changeset"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("draft", "Draft release", "Draft a release or changelog artifact.", risk_level="medium", permission_policy="ask_every_time"),
            _action("create", "Create release", "Create a release artifact through the configured release lane.", mutates_remote_state=True, requires_confirmation=True),
        ),
    ),
)


FAMILY_BY_ID = {family.family_id: family for family in FAMILIES}


def integration_catalog() -> list[dict[str, Any]]:
    return [
        {
            "family": family.family_id,
            "name": family.name,
            "summary": family.summary,
            "category": family.category,
            "providers": list(family.providers),
            "host_support": ["codex", "claude_code", "mission_control"],
            "available_action_ids": [action.action_id for action in family.actions],
        }
        for family in FAMILIES
    ]


def empty_registry() -> dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "connections": {},
        "host_imports": {"codex": {}, "claude_code": {}},
        "action_history": [],
    }


def _dedupe_strs(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _quote(value: Any) -> str:
    text = str(value)
    return '"' + text.replace('"', '\\"') + '"'


def _format_command(template: str, params: dict[str, Any]) -> str:
    values: dict[str, Any] = {}
    for key, value in params.items():
        values[key] = value
        values[f"{key}_q"] = _quote(value)
    return template.format(**values)


def _provider_status_from_legacy(account: dict[str, Any]) -> str:
    status = str(account.get("status") or "").strip().lower()
    if status == "connected":
        return "connected"
    if status in {"configure_manually", "coming_soon"}:
        return "needs_setup"
    if status:
        return status
    return "unknown"


def normalize_integration_registry(
    registry_payload: dict[str, Any] | None,
    legacy_connected_accounts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(registry_payload or {})
    normalized = empty_registry()
    if isinstance(payload.get("connections"), dict):
        normalized["connections"] = {str(key): dict(value or {}) for key, value in dict(payload["connections"]).items()}
    if isinstance(payload.get("host_imports"), dict):
        normalized["host_imports"] = {
            "codex": dict(dict(payload["host_imports"]).get("codex") or {}),
            "claude_code": dict(dict(payload["host_imports"]).get("claude_code") or {}),
        }
    if isinstance(payload.get("action_history"), list):
        normalized["action_history"] = [dict(item or {}) for item in list(payload["action_history"])[:50]]
    normalized["version"] = int(payload.get("version") or REGISTRY_VERSION)

    legacy = dict(legacy_connected_accounts or {})
    for family in FAMILIES:
        for account_key in family.legacy_account_keys:
            account = legacy.get(account_key)
            if not isinstance(account, dict):
                continue
            normalized["connections"].setdefault(
                family.family_id,
                {
                    "family": family.family_id,
                    "status": _provider_status_from_legacy(account),
                    "providers": [account_key],
                    "connection_source": "legacy_connected_accounts",
                    "host_imported": False,
                    "approval_policy": "ask_every_time",
                    "notes": [f"Migrated from legacy connected_accounts_json key `{account_key}`."],
                },
            )
    return normalized


def registry_to_legacy_connected_accounts(registry_payload: dict[str, Any] | None) -> dict[str, Any]:
    registry = normalize_integration_registry(registry_payload, {})
    legacy: dict[str, Any] = {}
    for family in FAMILIES:
        connection = dict(registry["connections"].get(family.family_id) or {})
        status = str(connection.get("status") or "")
        for key in family.legacy_account_keys:
            legacy[key] = {
                "status": "connected" if status == "connected" else "needs_setup" if status == "needs_setup" else status or "unknown",
                "source": connection.get("connection_source") or "mission_control",
                "host_imported": bool(connection.get("host_imported")),
                "providers": list(connection.get("providers") or []),
            }
    return legacy


def _host_scan_roots() -> dict[str, list[Path]]:
    home = Path.home()
    return {
        "codex": [
            get_codex_home() / "plugins",
            REPO_ROOT / ".codex" / "plugins",
            home / ".codex" / "plugins",
        ],
        "claude_code": [
            REPO_ROOT / ".claude",
            home / ".claude",
            home / ".config" / "claude",
        ],
    }


def _token_in_path(path: Path, tokens: tuple[str, ...]) -> bool:
    normalized = path.as_posix().lower()
    return any(token.lower() in normalized for token in tokens)


def import_host_state(
    registry_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    registry = normalize_integration_registry(registry_payload, {})
    host_roots = _host_scan_roots()

    for host_name, roots in host_roots.items():
        imported: dict[str, Any] = {}
        existing_tokens: list[Path] = []
        for root in roots:
            if root.exists():
                existing_tokens.append(root)
        for family in FAMILIES:
            matched_paths: list[str] = []
            for root in existing_tokens:
                try:
                    iterator = root.rglob("*")
                except OSError:
                    continue
                for path in iterator:
                    if len(matched_paths) >= 8:
                        break
                    if _token_in_path(path, family.host_tokens):
                        matched_paths.append(str(path))
            if matched_paths:
                imported[family.family_id] = {
                    "detected": True,
                    "paths": _dedupe_strs(matched_paths),
                    "provider_hints": list(family.providers),
                }
                registry["connections"][family.family_id] = {
                    "family": family.family_id,
                    "status": "connected",
                    "providers": list(family.providers),
                    "connection_source": f"{host_name}_host",
                    "host_imported": True,
                    "approval_policy": "ask_every_time",
                    "notes": [f"Imported from {host_name} host assets."],
                }
        registry["host_imports"][host_name] = imported
    return registry


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _relative_files(root: Path) -> list[str]:
    results: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.lower() in SKIP_DIRS for part in rel.parts):
            continue
        if any(part.startswith(".") and part not in {".github", ".storybook", ".devcontainer"} for part in rel.parts[:-1]):
            continue
        results.append(rel.as_posix())
    return results


def _workspace_haystack(root: Path, relative_files: list[str]) -> str:
    chunks: list[str] = []
    for relative in relative_files:
        name = Path(relative).name.lower()
        if name in {"package.json", "pyproject.toml", "requirements.txt", "readme.md", "firebase.json", "netlify.toml", "vercel.json"}:
            chunks.append(_safe_read_text(root / relative)[:4000])
    return "\n".join(chunks).lower()


def _connection_status_for_family(registry: dict[str, Any], family: IntegrationFamilyDefinition) -> dict[str, Any]:
    connection = dict(registry.get("connections", {}).get(family.family_id) or {})
    if not connection:
        return {
            "family": family.family_id,
            "status": "disconnected",
            "providers": [],
            "connection_source": "mission_control",
            "host_imported": False,
            "approval_policy": "ask_every_time",
            "notes": [],
        }
    connection.setdefault("family", family.family_id)
    connection.setdefault("approval_policy", "ask_every_time")
    connection.setdefault("providers", [])
    connection.setdefault("notes", [])
    connection.setdefault("host_imported", False)
    connection.setdefault("connection_source", "mission_control")
    return connection


def build_project_integration_status(
    *,
    workspace_path: str | None,
    project_name: str,
    registry_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    registry = normalize_integration_registry(registry_payload, {})
    root = Path(workspace_path) if workspace_path else None
    relative_files = _relative_files(root) if root and root.exists() else []
    haystack = _workspace_haystack(root, relative_files) if root and root.exists() else ""
    statuses: list[dict[str, Any]] = []
    for family in FAMILIES:
        connection = _connection_status_for_family(registry, family)
        detected_files = [path for path in relative_files if any(path == item or path.endswith("/" + item) or Path(path).name == item for item in family.config_files)]
        token_hits = [token for token in family.workspace_tokens if token and token.lower() in haystack]
        installed_clis = [cli for cli in family.cli_candidates if shutil.which(cli)]
        available_actions: list[dict[str, Any]] = []
        blockers: list[str] = []
        recommended_fixes: list[str] = []
        if not installed_clis and not connection.get("host_imported") and not detected_files and not token_hits:
            blockers.append("No host import, local CLI, or workspace signals were detected for this family.")
            recommended_fixes.append("Connect the provider in Mission Control or install the relevant local CLI before expecting a serious integration lane.")
            status = "needs_setup"
        elif connection.get("status") == "connected" or installed_clis or detected_files or token_hits:
            status = "ready"
        else:
            status = str(connection.get("status") or "unknown")
        for action in family.actions:
            action_ready = bool(installed_clis or connection.get("host_imported") or connection.get("status") == "connected" or action.action_id in {"import_host_state", "connect", "inspect_status"})
            available_actions.append(
                {
                    "action_id": action.action_id,
                    "title": action.title,
                    "summary": action.summary,
                    "risk_level": action.risk_level,
                    "permission_policy": action.permission_policy,
                    "preview_supported": action.preview_supported,
                    "mutates_remote_state": action.mutates_remote_state,
                    "requires_confirmation": action.requires_confirmation,
                    "required_params": list(action.required_params),
                    "status": "available" if action_ready else "needs_setup",
                }
            )
        safe_commands = [
            action.command_template
            for action in family.actions
            if action.command_template and not action.mutates_remote_state
        ]
        artifacts = [{"type": "config_file", "path": path} for path in detected_files]
        statuses.append(
            {
                "family": family.family_id,
                "name": family.name,
                "summary": family.summary,
                "category": family.category,
                "project_name": project_name,
                "workspace_path": workspace_path,
                "status": status,
                "connection_source": connection.get("connection_source") or "mission_control",
                "host_imported": bool(connection.get("host_imported")),
                "providers": list(connection.get("providers") or family.providers),
                "required_permissions": _dedupe_strs([action.permission_policy for action in family.actions]),
                "health": {
                    "cli_detected": installed_clis,
                    "workspace_config_files": detected_files,
                    "workspace_token_hits": token_hits,
                    "host_imported": bool(connection.get("host_imported")),
                },
                "artifacts": artifacts,
                "safe_commands": safe_commands,
                "blockers": blockers,
                "recommended_fixes": recommended_fixes,
                "available_actions": available_actions,
                "notes": list(connection.get("notes") or []),
            }
        )
    return statuses


def build_integration_catalog_with_connections(registry_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    registry = normalize_integration_registry(registry_payload, {})
    rows: list[dict[str, Any]] = []
    for family in FAMILIES:
        connection = _connection_status_for_family(registry, family)
        rows.append(
            {
                **next(item for item in integration_catalog() if item["family"] == family.family_id),
                "status": connection.get("status") or "disconnected",
                "connection_source": connection.get("connection_source") or "mission_control",
                "host_imported": bool(connection.get("host_imported")),
                "notes": list(connection.get("notes") or []),
            }
        )
    return rows


def list_connections(registry_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    registry = normalize_integration_registry(registry_payload, {})
    connections: list[dict[str, Any]] = []
    for family in FAMILIES:
        connection = _connection_status_for_family(registry, family)
        connections.append(connection)
    return connections


def preview_integration_action(
    *,
    family_id: str,
    action_id: str,
    params: dict[str, Any] | None,
    registry_payload: dict[str, Any] | None,
    workspace_path: str | None,
    project_name: str,
) -> dict[str, Any]:
    family = FAMILY_BY_ID.get(family_id)
    if family is None:
        raise ValueError("Unknown integration family")
    action = next((item for item in family.actions if item.action_id == action_id), None)
    if action is None:
        raise ValueError("Unknown integration action")
    params = dict(params or {})
    missing = [name for name in action.required_params if name not in params or params[name] in {None, ""}]
    command: str | None = None
    if action.command_template:
        if missing:
            command = action.command_template
        else:
            command = _format_command(action.command_template, params)
    return {
        "family": family.family_id,
        "action_id": action.action_id,
        "title": action.title,
        "summary": action.summary,
        "project_name": project_name,
        "workspace_path": workspace_path,
        "command": command,
        "risk_level": action.risk_level,
        "permission_policy": action.permission_policy,
        "preview_supported": action.preview_supported,
        "mutates_remote_state": action.mutates_remote_state,
        "requires_confirmation": action.requires_confirmation,
        "missing_params": missing,
        "notes": [
            "Mission Control previews the action before execution so approvals are tied to a concrete command or host import step.",
        ],
    }


def execute_integration_action(
    *,
    family_id: str,
    action_id: str,
    params: dict[str, Any] | None,
    registry_payload: dict[str, Any] | None,
    workspace_path: str | None,
    project_name: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    preview = preview_integration_action(
        family_id=family_id,
        action_id=action_id,
        params=params,
        registry_payload=registry_payload,
        workspace_path=workspace_path,
        project_name=project_name,
    )
    family = FAMILY_BY_ID[family_id]
    action = next(item for item in family.actions if item.action_id == action_id)
    registry = normalize_integration_registry(registry_payload, {})
    if preview["missing_params"]:
        return {
            **preview,
            "status": "blocked",
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "approval_required": False,
        }
    if action.action_id == "import_host_state":
        imported = import_host_state(registry)
        return {
            **preview,
            "status": "completed",
            "stdout": "Imported host integration state.",
            "stderr": "",
            "returncode": 0,
            "approval_required": False,
            "updated_registry": imported,
        }
    if action.requires_confirmation and not confirmed:
        return {
            **preview,
            "status": "approval_required",
            "stdout": "",
            "stderr": "Explicit confirmation is required for this mutating integration action.",
            "returncode": None,
            "approval_required": True,
        }
    if not preview.get("command"):
        return {
            **preview,
            "status": "completed" if action.action_id == "connect" else "blocked",
            "stdout": "No executable local command is defined for this action." if action.action_id == "connect" else "",
            "stderr": "",
            "returncode": 0 if action.action_id == "connect" else None,
            "approval_required": False,
        }
    completed = subprocess.run(
        str(preview["command"]),
        shell=True,
        cwd=workspace_path if workspace_path and Path(workspace_path).exists() else str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    history = list(registry.get("action_history") or [])
    history.append(
        {
            "family": family_id,
            "action_id": action_id,
            "status": "completed" if completed.returncode == 0 else "failed",
            "command": preview["command"],
            "returncode": completed.returncode,
        }
    )
    registry["action_history"] = history[-50:]
    return {
        **preview,
        "status": "completed" if completed.returncode == 0 else "failed",
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
        "approval_required": False,
        "updated_registry": registry,
    }

