from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from config import REPO_ROOT, get_codex_home


REGISTRY_VERSION = 1
INTEGRATION_REGISTRY_KEY = "integration_registry_json"
LEGACY_CONNECTION_SOURCES = {"legacy_connected_accounts", "manual", "codex_host", "claude_code_host", "mission_control"}
AUTHORITATIVE_CONNECTION_SOURCES = {"mission_control", "manual", "legacy_connected_accounts"}
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

PROVIDER_PRIORITY_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "source_control": ("github", "gitlab", "bitbucket"),
    "work_tracking": ("github_issues", "jira", "linear"),
    "containers": ("devcontainer", "docker"),
    "ci_cd": ("github_actions", "gitlab_ci", "bitbucket_pipelines", "circleci", "buildkite"),
    "hosting_deploy": ("vercel", "netlify", "cloudflare_pages", "railway", "render"),
}

PROVIDER_CLIS: dict[str, tuple[str, ...]] = {
    "github": ("gh",),
    "gitlab": ("glab",),
    "bitbucket": (),
    "github_issues": ("gh",),
    "jira": ("acli",),
    "linear": (),
    "docker": ("docker",),
    "devcontainer": ("devcontainer",),
    "opentofu": ("tofu",),
    "github_actions": ("gh",),
    "gitlab_ci": ("glab",),
    "bitbucket_pipelines": (),
    "circleci": ("circleci",),
    "buildkite": ("buildkite-agent",),
    "vercel": ("vercel",),
    "netlify": ("netlify",),
    "cloudflare_pages": ("wrangler",),
    "railway": ("railway",),
    "render": ("render",),
    "storybook": ("npm",),
    "mintlify": ("mintlify",),
    "docusaurus": ("npm",),
    "terraform": ("terraform",),
    "aws": ("aws",),
    "azure": ("az",),
    "gcp": ("gcloud",),
    "npm": ("npm",),
    "pypi": ("twine",),
    "maven": ("mvn",),
    "crates": ("cargo",),
    "nuget": ("dotnet",),
    "rubygems": ("gem",),
    "docker_hub": ("docker",),
    "sentry": ("sentry-cli",),
    "datadog": ("datadog-ci",),
    "new_relic": ("newrelic",),
    "supabase": ("supabase",),
    "firebase": ("firebase",),
    "neon": ("neon",),
    "planetscale": ("pscale",),
    "kubernetes": ("kubectl",),
    "changesets": ("changeset",),
    "github_releases": ("gh",),
    "release_please": ("release-please",),
    "semantic_release": ("semantic-release",),
    "bruno": ("bru",),
    "snyk": ("snyk",),
    "semgrep": ("semgrep",),
    "trivy": ("trivy",),
    "codeql": ("codeql",),
    "doppler": ("doppler",),
    "vault": ("vault",),
    "stripe": ("stripe",),
    "onepassword": ("op",),
    "aws_secrets_manager": ("aws",),
    "gcp_secret_manager": ("gcloud",),
    "chrome_devtools": ("chrome",),
    "cdp": ("chrome",),
    "postman": ("newman",),
    "insomnia": ("inso",),
    "openapi": ("swagger-cli",),
    "swagger": ("swagger-cli",),
    "sourcegraph": ("src",),
    "zoekt": ("zoekt-query",),
    "auth0": ("auth0",),
    "firebase_auth": ("firebase",),
    "supabase_auth": ("supabase",),
    "playwright": ("playwright",),
    "cypress": ("cypress",),
    "gitleaks": ("gitleaks",),
    "ollama": ("ollama",),
    "vllm": ("vllm",),
}

PROVIDER_WORKSPACE_MARKERS: dict[str, tuple[str, ...]] = {
    "github": (".github/workflows",),
    "gitlab": (".gitlab-ci.yml",),
    "bitbucket": ("bitbucket-pipelines.yml",),
    "github_issues": (".github/workflows",),
    "jira": (".jira",),
    "linear": (".linear",),
    "docker": ("Dockerfile", "docker-compose.yml", "docker-compose.yaml"),
    "devcontainer": (".devcontainer/devcontainer.json",),
    "github_actions": (".github/workflows",),
    "gitlab_ci": (".gitlab-ci.yml",),
    "bitbucket_pipelines": ("bitbucket-pipelines.yml",),
    "circleci": (".circleci/config.yml",),
    "buildkite": (".buildkite/pipeline.yml", ".buildkite/pipeline.yaml"),
    "vercel": ("vercel.json",),
    "netlify": ("netlify.toml",),
    "cloudflare_pages": ("wrangler.toml",),
    "railway": ("railway.json",),
    "render": ("render.yaml",),
    "sentry": ("sentry.properties",),
    "datadog": ("datadog.yaml", "datadog.yml"),
    "new_relic": ("newrelic.js", "newrelic.ts", "newrelic.cjs", "newrelic.mjs"),
    "supabase": ("supabase/config.toml",),
    "firebase": ("firebase.json",),
    "neon": ("neon.json",),
    "planetscale": ("pscale.yml",),
    "storybook": (".storybook/main.js", ".storybook/main.ts"),
    "npm": ("package.json", ".npmrc"),
    "pypi": ("pyproject.toml", "setup.py", "requirements.txt"),
    "maven": ("pom.xml",),
    "crates": ("Cargo.toml",),
    "nuget": (".nuspec", ".csproj"),
    "rubygems": ("Gemfile", ".gemspec"),
    "docker_hub": ("Dockerfile",),
    "postman": ("postman.json", ".postman.json", "postman_collection.json", ".postman_collection.json"),
    "insomnia": (".insomnia", "insomnia.json", ".insomnia.json"),
    "bruno": ("bruno.json",),
    "auth0": (".auth0", "auth0.json", ".auth0.json"),
    "terraform": ("main.tf", "versions.tf", "terraform.tfvars"),
    "opentofu": ("tofu.hcl",),
    "mintlify": ("mint.json",),
    "docusaurus": ("docusaurus.config.js", "docusaurus.config.ts", "docusaurus.config.mjs"),
    "playwright": ("playwright.config.ts", "playwright.config.js"),
    "cypress": ("cypress.config.ts", "cypress.config.js"),
    "gitleaks": (".gitleaks.toml",),
    "snyk": (".snyk",),
    "semgrep": (".semgrep",),
    "trivy": ("trivy.yaml", "trivy.yml"),
    "codeql": (".github/codeql",),
    "openapi": ("openapi.yaml", "openapi.yml", "openapi.json"),
    "swagger": ("swagger.yaml", "swagger.yml"),
    "firebase_auth": ("firebase.json",),
    "supabase_auth": ("supabase/config.toml",),
    "changesets": (".changeset",),
    "release_please": (".release-please-manifest.json", "release-please-config.json"),
    "semantic_release": (".releaserc", ".releaserc.json", ".releaserc.yml", ".releaserc.yaml", "release.config.js", "release.config.cjs"),
    "kubernetes": ("k8s", "kubernetes", "helm"),
}

PROVIDER_TOKEN_MARKERS: dict[str, tuple[str, ...]] = {
    "github": ("github",),
    "gitlab": ("gitlab",),
    "bitbucket": ("bitbucket",),
    "github_issues": ("github issue", "gh issue", "github"),
    "jira": ("jira",),
    "linear": ("linear",),
    "docker": ("docker",),
    "devcontainer": ("devcontainer",),
    "github_actions": ("github workflow", "github actions",),
    "gitlab_ci": ("gitlab ci", "gitlab pipeline",),
    "bitbucket_pipelines": ("bitbucket pipelines",),
    "circleci": ("circleci",),
    "buildkite": ("buildkite",),
    "vercel": ("vercel",),
    "netlify": ("netlify",),
    "cloudflare_pages": ("cloudflare pages", "wrangler",),
    "railway": ("railway",),
    "render": ("render",),
    "figma": ("figma",),
    "slack": ("slack",),
    "discord": ("discord",),
    "teams": ("teams", "microsoft teams"),
    "notion": ("notion",),
    "confluence": ("confluence",),
    "sentry": ("sentry", "sentry-cli"),
    "logrocket": ("logrocket",),
    "datadog": ("datadog", "datadog-ci"),
    "new_relic": ("new relic", "newrelic", "newrelic-cli"),
    "launchdarkly": ("launchdarkly", "launch darkly"),
    "statsig": ("statsig",),
    "configcat": ("configcat", "config cat"),
    "unleash": ("unleash",),
    "posthog_feature_flags": ("posthog feature flags", "posthog flags", "posthog"),
    "posthog": ("posthog",),
    "amplitude": ("amplitude",),
    "mixpanel": ("mixpanel",),
    "plausible": ("plausible",),
    "intercom": ("intercom",),
    "zendesk": ("zendesk",),
    "help_scout": ("help scout", "helpscout"),
    "freshdesk": ("freshdesk",),
    "supabase": ("supabase",),
    "firebase": ("firebase",),
    "neon": ("neon",),
    "planetscale": ("planetscale", "pscale"),
    "onepassword": ("1password", "op"),
    "aws_secrets_manager": ("aws secrets manager", "aws secretsmanager"),
    "gcp_secret_manager": ("gcp secret manager", "gcloud secrets", "google secret manager"),
    "storybook": ("storybook",),
    "npm": ("npm", "package.json"),
    "pypi": ("pypi", "twine", "pyproject", "setup.py"),
    "maven": ("maven", "pom.xml", "mvn"),
    "crates": ("cargo", "crates", "cargo.toml"),
    "nuget": ("nuget", "dotnet", "nuspec"),
    "rubygems": ("rubygems", "gemfile", "gemspec", "gem"),
    "docker_hub": ("docker hub", "dockerfile", "docker"),
    "kubernetes": ("kubernetes", "kubectl", "helm", "k8s"),
    "codeql": ("codeql",),
    "chrome_devtools": ("chrome devtools", "devtools"),
    "cdp": ("chrome debug protocol", "chrome devtools protocol", "cdp"),
    "lm_studio": ("lm studio", "lmstudio"),
    "opengrok": ("opengrok",),
    "paddle": ("paddle",),
    "lemon_squeezy": ("lemon squeezy", "lemonsqueezy"),
    "paypal_sandbox": ("paypal sandbox", "paypal"),
    "github_releases": ("github releases", "github release"),
    "release_please": ("release please", "release-please"),
    "semantic_release": ("semantic-release", "semantic release"),
    "clerk": ("clerk",),
    "workos": ("workos", "work os"),
    "okta": ("okta",),
    "postman": ("postman", "newman"),
    "insomnia": ("insomnia", "inso"),
    "bruno": ("bruno", "bru"),
    "auth0": ("auth0",),
    "terraform": ("terraform",),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure",),
    "gcp": ("gcp", "google cloud", "gcloud"),
    "mintlify": ("mintlify",),
    "doppler": ("doppler",),
    "vault": ("vault",),
    "opentofu": ("opentofu", "tofu",),
    "docusaurus": ("docusaurus",),
    "playwright": ("playwright",),
    "cypress": ("cypress",),
    "gitleaks": ("gitleaks",),
    "snyk": ("snyk",),
    "semgrep": ("semgrep",),
    "trivy": ("trivy",),
    "ollama": ("ollama",),
    "vllm": ("vllm",),
    "openapi": ("openapi",),
    "swagger": ("swagger",),
    "sourcegraph": ("sourcegraph",),
    "zoekt": ("zoekt",),
    "stripe": ("stripe",),
    "firebase_auth": ("firebase auth",),
    "supabase_auth": ("supabase auth",),
    "changesets": ("changesets", ".changeset",),
    "launchnotes": ("launchnotes", "launch notes"),
    "dependabot": ("dependabot", "dependabot alerts"),
    "pinecone": ("pinecone", "pinecone index"),
    "weaviate": ("weaviate", "weaviate cluster"),
    "qdrant": ("qdrant", "qdrant cloud"),
    "chroma": ("chroma", "chroma db"),
    "milvus": ("milvus", "milvus vector db"),
    "opengrok": ("opengrok", "open grok"),
}

PROVIDER_ACTION_GUIDANCE: dict[str, dict[str, str]] = {
    "github": {
        "search": "GitHub inspection uses the local CLI when available, but the result still reflects live remote repository state rather than repo-local proof.",
        "create": "GitHub issue creation uses the local CLI when available and still mutates remote issue state, so approvals remain mandatory.",
        "inspect": "GitHub inspection uses the local CLI when available, but the result still reflects live remote repository state rather than repo-local proof.",
    },
    "gitlab": {
        "search": "GitLab inspection uses the local CLI when available, but the result still reflects live remote repository state rather than repo-local proof.",
        "create": "GitLab issue creation uses the local CLI when available and still mutates remote issue state, so approvals remain mandatory.",
        "inspect": "GitLab inspection uses the local CLI when available, but the result still reflects live remote repository state rather than repo-local proof.",
    },
    "bitbucket": {
        "search": "Bitbucket is resolved from git remote or pipeline config, but Mission Control currently expects a host-integrated or REST-backed adapter instead of pretending there is a bundled official Bitbucket CLI.",
        "create": "Bitbucket mutations are not wired to a bundled CLI here. Use a host integration or an approval-gated REST adapter lane instead of fantasy tooling.",
        "inspect": "Bitbucket inspection should route through a host integration or REST-backed adapter lane. The repo remote is enough to resolve the provider, not enough to fake a live API session.",
    },
    "github_issues": {
        "search": "GitHub Issues inspection uses the local CLI when available, but the result still reflects live remote issue state rather than repo-local proof.",
        "create": "GitHub Issues creation uses the local CLI when available and still mutates remote issue state, so approvals remain mandatory.",
    },
    "jira": {
        "search": "Jira search can use Atlassian CLI when available. Without `acli`, keep this lane host-imported or wire a project-scoped adapter with explicit auth.",
        "create": "Jira creation supports Atlassian CLI when `project_key` and `issue_type` are supplied. Without `acli`, use a host-integrated or API-backed lane instead.",
        "update": "Jira updates should route through Atlassian CLI or a verified host/API lane rather than an invented local CLI.",
    },
    "linear": {
        "search": "Linear is resolved from workspace or host signals. Mission Control treats it as a host-import or GraphQL adapter lane because Linear does not ship a bundled local CLI here.",
        "create": "Linear issue creation should use a host-integrated path or the Linear GraphQL API. If a browser-first fallback helps, `linear.new` is the honest escape hatch.",
        "update": "Linear updates should route through a verified host-integrated or GraphQL adapter lane.",
    },
    "bitbucket_pipelines": {
        "inspect": "Bitbucket Pipelines is resolved from workspace signals, but deeper execution currently expects a host-integrated or API-backed adapter instead of a bundled CLI.",
        "inspect_run": "Inspect specific Bitbucket pipeline runs through a host-integrated or API-backed adapter lane.",
        "tail_logs": "Bitbucket pipeline log tails currently require a host-integrated or API-backed adapter lane.",
        "rerun": "Bitbucket reruns currently require a host-integrated or API-backed adapter lane.",
    },
    "github_actions": {
        "inspect": "GitHub Actions inspection uses the local CLI when available, but the result still reflects live remote workflow state rather than repo-local proof.",
        "inspect_run": "GitHub Actions run inspection uses the local CLI when available, but the result still reflects live remote workflow state rather than repo-local proof.",
        "tail_logs": "GitHub Actions log inspection uses the local CLI when available, but the result still reflects live remote workflow state rather than repo-local proof.",
        "rerun": "GitHub Actions reruns use the local CLI when available and still mutate remote workflow state, so approvals remain mandatory.",
    },
    "gitlab_ci": {
        "inspect": "GitLab CI inspection uses the local CLI when available, but the result still reflects live remote pipeline state rather than repo-local proof.",
        "inspect_run": "GitLab CI run inspection uses the local CLI when available, but the result still reflects live remote pipeline state rather than repo-local proof.",
        "tail_logs": "GitLab CI log inspection uses the local CLI when available, but the result still reflects live remote pipeline state rather than repo-local proof.",
    },
    "circleci": {
        "inspect": "CircleCI inspection uses the local CLI when available and validates the current pipeline config rather than pretending the repo alone proves a live CI session.",
    },
    "buildkite": {
        "inspect": "Buildkite inspection uses the local agent tooling when available and validates the current pipeline config rather than pretending the repo alone proves a live CI session.",
    },
    "render": {
        "deploy": "Render deploys support the official Render CLI, but you still need a concrete service identifier before Mission Control should attempt to trigger anything.",
    },
    "vercel": {
        "inspect": "Vercel inspection uses the local CLI when available, but the result still reflects live remote deployment state rather than repo-local proof.",
        "deploy": "Vercel deploy uses the local CLI when available and still mutates remote deployment state, so approvals remain mandatory.",
    },
    "netlify": {
        "inspect": "Netlify inspection uses the local CLI when available, but the result still reflects live remote deployment state rather than repo-local proof.",
        "deploy": "Netlify deploy uses the local CLI when available and still mutates remote deployment state, so approvals remain mandatory.",
    },
    "cloudflare_pages": {
        "inspect": "Cloudflare Pages inspection uses the local CLI when available, but the result still reflects live remote deployment state rather than repo-local proof.",
        "tail_logs": "Cloudflare Pages log inspection uses the local CLI when available, but the result still reflects live remote deployment state rather than repo-local proof.",
        "deploy": "Cloudflare Pages deploy uses the local CLI when available and still mutates remote deployment state, so approvals remain mandatory.",
    },
    "railway": {
        "inspect": "Railway inspection uses the local CLI when available, but the result still reflects live remote deployment state rather than repo-local proof.",
        "tail_logs": "Railway log inspection uses the local CLI when available, but the result still reflects live remote deployment state rather than repo-local proof.",
        "deploy": "Railway deploy uses the local CLI when available and still mutates remote deployment state, so approvals remain mandatory.",
    },
    "figma": {
        "inspect": "Figma is intentionally a guided remote lane here. Use the host-integrated Figma plugin or API-backed design lane instead of pretending there is a local CLI.",
        "sync": "Figma sync should route through the host-integrated or API-backed design lane rather than a fake local command.",
    },
    "slack": {
        "search": "Slack review should route through a host-integrated or API-backed chat lane instead of an invented local CLI.",
        "create": "Slack message creation should use a verified host or API-backed lane, not a fake local executable.",
    },
    "discord": {
        "search": "Discord review should route through a host-integrated or API-backed chat lane instead of an invented local CLI.",
        "create": "Discord message creation should use a verified host or API-backed lane, not a fake local executable.",
    },
    "teams": {
        "search": "Microsoft Teams review should route through a host-integrated or API-backed chat lane instead of an invented local CLI.",
        "create": "Microsoft Teams message creation should use a verified host or API-backed lane, not a fake local executable.",
    },
    "notion": {
        "inspect": "Notion is intentionally a guided remote lane here. Use the host-integrated or API-backed documentation lane instead of pretending a local CLI exists.",
        "sync": "Notion sync should route through a verified host or API-backed lane.",
    },
    "confluence": {
        "inspect": "Confluence is intentionally a guided remote lane here. Use the host-integrated or API-backed documentation lane instead of pretending a local CLI exists.",
        "sync": "Confluence sync should route through a verified host or API-backed lane.",
    },
    "mintlify": {
        "inspect": "Mintlify inspection uses the local CLI when available, but it still reflects the current docs workspace and CLI environment rather than a static repo promise.",
        "sync": "Mintlify sync should use the verified local docs CLI or a host-backed publishing lane instead of pretending the repo alone proves a live docs session.",
    },
    "postman": {
        "inspect": "Postman inspection uses the Newman CLI when available and reflects the current local collection/runtime environment rather than a repo hint.",
        "validate": "Postman validation uses the Newman CLI when available and runs the current collection state rather than a static registry hint.",
    },
    "insomnia": {
        "inspect": "Insomnia inspection uses the Inso CLI when available and reflects the current local collection/runtime environment rather than a repo hint.",
        "validate": "Insomnia validation uses the Inso CLI when available and runs the current collection state rather than a static registry hint.",
    },
    "bruno": {
        "inspect": "Bruno inspection uses the local CLI when available and reflects the current request collection/runtime environment rather than a repo hint.",
        "validate": "Bruno validation uses the local CLI when available and runs the current collection state rather than a static registry hint.",
    },
    "terraform": {
        "validate": "Terraform validation uses the local CLI when available, but it still reflects the current workspace and provider configuration rather than repo hints alone.",
        "deploy": "Terraform apply uses the local CLI when available and still mutates live infrastructure state, so approvals remain mandatory.",
    },
    "opentofu": {
        "validate": "OpenTofu validation uses the local CLI when available, but it still reflects the current workspace and provider configuration rather than repo hints alone.",
        "deploy": "OpenTofu apply uses the local CLI when available and still mutates live infrastructure state, so approvals remain mandatory.",
    },
    "aws": {
        "inspect": "AWS inspection uses live CLI auth and reflects the active cloud account context rather than repo-local proof.",
        "open": "AWS context refresh uses the local CLI when available and still depends on live cloud auth state.",
    },
    "azure": {
        "inspect": "Azure inspection uses live CLI auth and reflects the active subscription context rather than repo-local proof.",
        "open": "Azure context refresh uses the local CLI when available and still depends on live cloud auth state.",
    },
    "gcp": {
        "inspect": "GCP inspection uses live CLI auth and reflects the active project context rather than repo-local proof.",
        "open": "GCP context refresh uses the local CLI when available and still depends on live cloud auth state.",
    },
    "npm": {
        "inspect": "npm inspection uses the local CLI when available and reflects the current auth/session and registry configuration rather than repo hints alone.",
        "publish": "npm publish uses the local CLI when available and still mutates remote registry state, so approvals remain mandatory.",
    },
    "pypi": {
        "inspect": "PyPI inspection uses the local tooling when available and reflects the current upload environment rather than repo hints alone.",
        "publish": "PyPI uploads use the local tooling when available and still mutate remote registry state, so approvals remain mandatory.",
    },
    "maven": {
        "inspect": "Maven inspection uses the local CLI when available and reflects the current build and repository configuration rather than repo hints alone.",
        "publish": "Maven deploy uses the local CLI when available and still mutates remote repository state, so approvals remain mandatory.",
    },
    "crates": {
        "inspect": "crates.io inspection uses the local Cargo CLI when available and reflects the current toolchain and registry configuration rather than repo hints alone.",
        "publish": "crates.io publishing uses the local Cargo CLI when available and still mutates remote registry state, so approvals remain mandatory.",
    },
    "nuget": {
        "inspect": "NuGet inspection uses the local CLI when available and reflects the current source configuration rather than repo hints alone.",
        "publish": "NuGet publishing uses the local CLI when available and still mutates remote registry state, so approvals remain mandatory.",
    },
    "rubygems": {
        "inspect": "RubyGems inspection uses the local CLI when available and reflects the current gem environment rather than repo hints alone.",
        "publish": "RubyGems publishing uses the local CLI when available and still mutates remote registry state, so approvals remain mandatory.",
    },
    "docker_hub": {
        "inspect": "Docker Hub inspection uses the local Docker CLI when available and reflects the current local engine and auth context rather than repo hints alone.",
        "publish": "Docker Hub publishing uses the local Docker CLI when available and still mutates remote registry state, so approvals remain mandatory.",
    },
    "snyk": {
        "scan": "Snyk scans use the local CLI when available and reflect the current dependency graph and live policy configuration rather than repo hints alone.",
    },
    "semgrep": {
        "scan": "Semgrep scans use the local CLI when available and reflect the current ruleset and repository contents rather than repo hints alone.",
    },
    "trivy": {
        "scan": "Trivy scans use the local CLI when available and reflect the current artifact or repository contents rather than repo hints alone.",
    },
    "codeql": {
        "scan": "CodeQL inspection uses the local CLI when available and reflects the current query-pack and workspace configuration rather than repo hints alone.",
    },
    "auth0": {
        "inspect": "Auth0 inspection uses the local CLI when available, but it still represents live remote auth state, not a repo-only guarantee.",
    },
    "supabase": {
        "inspect": "Supabase inspection uses the local CLI when available, but the result still reflects live platform state rather than repo-local proof.",
        "sync": "Supabase sync uses the local CLI when available and still mutates remote platform state, so approvals remain mandatory.",
    },
    "firebase": {
        "inspect": "Firebase inspection uses the local CLI when available, but the result still reflects live platform state rather than repo-local proof.",
        "sync": "Firebase sync uses the local CLI when available and still mutates remote platform state, so approvals remain mandatory.",
    },
    "neon": {
        "inspect": "Neon inspection uses the local CLI when available, but the result still reflects live platform state rather than repo-local proof.",
    },
    "planetscale": {
        "inspect": "PlanetScale inspection uses the local CLI when available, but the result still reflects live platform state rather than repo-local proof.",
    },
    "logrocket": {
        "inspect": "LogRocket is intentionally treated as a guided remote lane here. Mission Control should not pretend a local LogRocket CLI exists when the honest path is browser/API-backed.",
        "tail": "LogRocket session and telemetry review should route through a host-integrated or API-backed lane instead of a fake local CLI.",
    },
    "launchdarkly": {
        "inspect": "LaunchDarkly should route through a verified host or API-backed feature-flag lane instead of a fake local CLI here.",
        "sync": "LaunchDarkly sync should use a verified host or API-backed lane.",
    },
    "statsig": {
        "inspect": "Statsig should route through a verified host or API-backed feature-flag lane instead of a fake local CLI here.",
        "sync": "Statsig sync should use a verified host or API-backed lane.",
    },
    "configcat": {
        "inspect": "ConfigCat should route through a verified host or API-backed feature-flag lane instead of a fake local CLI here.",
        "sync": "ConfigCat sync should use a verified host or API-backed lane.",
    },
    "unleash": {
        "inspect": "Unleash should route through a verified host or API-backed feature-flag lane instead of a fake local CLI here.",
        "sync": "Unleash sync should use a verified host or API-backed lane.",
    },
    "posthog_feature_flags": {
        "inspect": "PostHog feature flags should route through a verified host or API-backed flag lane instead of a fake local CLI here.",
        "sync": "PostHog feature flag sync should use a verified host or API-backed lane.",
    },
    "posthog": {
        "inspect": "PostHog analytics should route through a verified host or API-backed analytics lane instead of a fake local CLI here.",
    },
    "amplitude": {
        "inspect": "Amplitude analytics should route through a verified host or API-backed analytics lane instead of a fake local CLI here.",
    },
    "mixpanel": {
        "inspect": "Mixpanel analytics should route through a verified host or API-backed analytics lane instead of a fake local CLI here.",
    },
    "plausible": {
        "inspect": "Plausible analytics should route through a verified host or API-backed analytics lane instead of a fake local CLI here.",
    },
    "intercom": {
        "search": "Intercom ticket and knowledge review should route through a verified host or API-backed support lane.",
        "create": "Intercom ticket creation should use a verified host or API-backed lane instead of a fake local CLI.",
    },
    "zendesk": {
        "search": "Zendesk ticket and knowledge review should route through a verified host or API-backed support lane.",
        "create": "Zendesk ticket creation should use a verified host or API-backed lane instead of a fake local CLI.",
    },
    "help_scout": {
        "search": "Help Scout review should route through a verified host or API-backed support lane.",
        "create": "Help Scout ticket creation should use a verified host or API-backed lane instead of a fake local CLI.",
    },
    "freshdesk": {
        "search": "Freshdesk review should route through a verified host or API-backed support lane.",
        "create": "Freshdesk ticket creation should use a verified host or API-backed lane instead of a fake local CLI.",
    },
    "lm_studio": {
        "inspect": "LM Studio is intentionally treated as a guided local-runtime lane here. Use the host/runtime bridge instead of pretending a stable CLI contract exists.",
        "open": "LM Studio open/refresh flows should use the host/runtime bridge rather than a fake local CLI.",
    },
    "opengrok": {
        "search": "OpenGrok search should route through a verified host or API-backed search lane instead of a fake local CLI here.",
    },
    "sourcegraph": {
        "search": "Sourcegraph queries use the local CLI when available, but they still reflect live indexed search state rather than repo-local proof.",
    },
    "zoekt": {
        "search": "Zoekt queries use the local CLI when available, but they still reflect live index state rather than repo-local proof.",
    },
    "openapi": {
        "inspect": "OpenAPI inspection uses the local CLI when available and reflects the current spec file rather than repo hints alone.",
        "validate": "OpenAPI validation uses the local CLI when available and checks the current spec file rather than repo hints alone.",
    },
    "swagger": {
        "inspect": "Swagger inspection uses the local CLI when available and reflects the current spec file rather than repo hints alone.",
        "validate": "Swagger validation uses the local CLI when available and checks the current spec file rather than repo hints alone.",
    },
    "playwright": {
        "validate": "Playwright validation uses the local CLI when available and reflects the current browser-test workspace rather than a static repo hint.",
    },
    "cypress": {
        "validate": "Cypress validation uses the local CLI when available and reflects the current browser-test workspace rather than a static repo hint.",
    },
    "gitleaks": {
        "scan": "Gitleaks scans use the local CLI when available and reflect the current repository contents rather than a static repo hint.",
    },
    "ollama": {
        "inspect": "Ollama inspection uses the local runtime CLI when available and reflects live local model state rather than repo-local proof.",
        "open": "Ollama runtime startup uses the local CLI when available and still depends on live local runtime state.",
    },
    "vllm": {
        "inspect": "vLLM inspection uses the local runtime CLI when available and reflects live local model-server state rather than repo-local proof.",
        "open": "vLLM runtime startup uses the local CLI when available and still depends on live local runtime state.",
    },
    "paddle": {
        "inspect": "Paddle sandbox inspection should route through a verified host or API-backed payment lane instead of a fake local CLI.",
        "create": "Paddle test artifact creation should use a verified host or API-backed lane.",
    },
    "lemon_squeezy": {
        "inspect": "Lemon Squeezy sandbox inspection should route through a verified host or API-backed payment lane instead of a fake local CLI.",
        "create": "Lemon Squeezy test artifact creation should use a verified host or API-backed lane.",
    },
    "paypal_sandbox": {
        "inspect": "PayPal sandbox inspection should route through a verified host or API-backed payment lane instead of a fake local CLI.",
        "create": "PayPal sandbox test artifact creation should use a verified host or API-backed lane.",
    },
    "clerk": {
        "inspect": "Clerk auth inspection should route through a verified host or API-backed auth lane instead of a fake local CLI.",
    },
    "workos": {
        "inspect": "WorkOS auth inspection should route through a verified host or API-backed auth lane instead of a fake local CLI.",
    },
    "okta": {
        "inspect": "Okta auth inspection should route through a verified host or API-backed auth lane instead of a fake local CLI.",
    },
    "firebase_auth": {
        "inspect": "Firebase Auth inspection uses the Firebase CLI when available, but the real contract still depends on live remote auth state.",
    },
    "supabase_auth": {
        "inspect": "Supabase Auth inspection uses the Supabase CLI when available, but the real contract still depends on live remote auth state.",
    },
    "onepassword": {
        "inspect": "1Password inspection uses the local CLI when available, but the result still reflects live vault/session state rather than repo-local proof.",
    },
    "doppler": {
        "inspect": "Doppler inspection uses the local CLI when available, but the result still reflects live config/auth state rather than repo-local proof.",
    },
    "vault": {
        "inspect": "Vault inspection uses the local CLI when available, but the result still reflects live cluster/session state rather than repo-local proof.",
    },
    "aws_secrets_manager": {
        "inspect": "AWS Secrets Manager inspection uses AWS CLI auth and reflects live cloud state, not a repo-only guarantee.",
    },
    "gcp_secret_manager": {
        "inspect": "GCP Secret Manager inspection uses gcloud auth and reflects live cloud state, not a repo-only guarantee.",
    },
    "docusaurus": {
        "inspect": "Docusaurus inspection uses the local CLI when available and reflects the current docs workspace rather than repo hints alone.",
        "sync": "Docusaurus sync currently builds local docs artifacts through the local CLI; it does not claim a live remote publish by itself.",
    },
    "devcontainer": {
        "inspect": "Dev Containers inspection uses the local CLI when available and reflects the current workspace/container definition rather than repo hints alone.",
        "validate": "Dev Containers validation uses the local CLI when available and reads the current workspace/container definition rather than a static registry hint.",
        "open": "Dev Containers startup uses the local CLI when available and changes local runtime state, not remote provider state.",
    },
    "docker": {
        "inspect": "Docker inspection uses the local CLI when available and reflects the current local engine/runtime state rather than repo hints alone.",
        "validate": "Docker validation uses the local CLI when available and reflects the current local runtime availability rather than repo hints alone.",
    },
    "sentry": {
        "inspect": "Sentry inspection uses the local CLI when available, but the result still reflects live provider state rather than repo-local proof.",
        "tail": "Sentry release and telemetry inspection uses the local CLI when available, but the result still reflects live provider state rather than repo-local proof.",
    },
    "datadog": {
        "inspect": "Datadog inspection uses the local CLI when available, but the result still reflects live provider state rather than repo-local proof.",
        "tail": "Datadog telemetry inspection uses the local CLI when available, but the result still reflects live provider state rather than repo-local proof.",
    },
    "new_relic": {
        "inspect": "New Relic inspection uses the local CLI when available, but the result still reflects live provider state rather than repo-local proof.",
    },
    "kubernetes": {
        "inspect": "Kubernetes inspection uses the local CLI when available, but the result still reflects live cluster context rather than repo-local proof.",
        "deploy": "Kubernetes apply uses the local CLI when available and still mutates live cluster state, so approvals remain mandatory.",
    },
    "storybook": {
        "validate": "Storybook validation uses the local CLI when available and reflects the current component preview workspace rather than a static repo hint.",
    },
    "stripe": {
        "inspect": "Stripe inspection uses the local CLI when available, but it still reflects live sandbox/auth state rather than repo-local proof.",
        "create": "Stripe sandbox artifact creation uses the local CLI when available and still mutates remote test state, so approvals remain mandatory.",
    },
    "chrome_devtools": {
        "inspect": "Chrome DevTools inspection uses the local CLI when available and reflects the current local browser runtime rather than repo-local proof.",
        "open": "Chrome DevTools startup uses the local CLI when available and changes local browser runtime state, not remote provider state.",
    },
    "cdp": {
        "inspect": "Chrome DevTools Protocol inspection uses the local CLI when available and reflects the current local browser runtime rather than repo-local proof.",
        "open": "Chrome DevTools Protocol startup uses the local CLI when available and changes local browser runtime state, not remote provider state.",
    },
    "release_please": {
        "draft": "Release Please drafting uses the local CLI when available, but the output still depends on the repo's live release metadata and branch state.",
        "create": "Release Please publishing uses the local CLI when available and still mutates release state, so approvals remain mandatory.",
    },
    "changesets": {
        "draft": "Changesets drafting uses the local CLI when available and reflects the repo's current changeset graph rather than a static repo hint.",
        "create": "Changesets release creation uses the local CLI when available and still mutates release state, so approvals remain mandatory.",
    },
    "semantic_release": {
        "draft": "semantic-release dry runs use the local CLI when available and reflect the repo's live release configuration and commit history.",
        "create": "semantic-release publishing uses the local CLI when available and still mutates release state, so approvals remain mandatory.",
    },
    "github_releases": {
        "draft": "GitHub release inspection uses the local CLI when available, but it still reflects live remote release state rather than repo-local proof.",
        "create": "GitHub release creation uses the local CLI when available and still mutates remote release state, so approvals remain mandatory.",
    },
    "launchnotes": {
        "draft": "LaunchNotes drafting should route through a verified host or API-backed release lane instead of a fake local CLI.",
        "create": "LaunchNotes release publishing should use a verified host or API-backed lane.",
    },
    "dependabot": {
        "scan": "Dependabot is intentionally a guided remote lane here. Use GitHub's hosted Dependabot/alerts lane instead of pretending there is a bundled local CLI.",
    },
    "pinecone": {
        "inspect": "Pinecone inspection should route through a verified host or API-backed vector-store lane instead of a fake local CLI.",
        "search": "Pinecone retrieval smoke checks should use a verified host or API-backed vector-store lane.",
    },
    "weaviate": {
        "inspect": "Weaviate inspection should route through a verified host or API-backed vector-store lane instead of a fake local CLI.",
        "search": "Weaviate retrieval smoke checks should use a verified host or API-backed vector-store lane.",
    },
    "qdrant": {
        "inspect": "Qdrant inspection should route through a verified host or API-backed vector-store lane instead of a fake local CLI.",
        "search": "Qdrant retrieval smoke checks should use a verified host or API-backed vector-store lane.",
    },
    "chroma": {
        "inspect": "Chroma inspection should route through a verified host or API-backed vector-store lane instead of a fake local CLI.",
        "search": "Chroma retrieval smoke checks should use a verified host or API-backed vector-store lane.",
    },
    "milvus": {
        "inspect": "Milvus inspection should route through a verified host or API-backed vector-store lane instead of a fake local CLI.",
        "search": "Milvus retrieval smoke checks should use a verified host or API-backed vector-store lane.",
    },
    "opengrok": {
        "search": "OpenGrok search should route through a verified host or API-backed code-search lane instead of a fake local CLI.",
    },
}

PROVIDER_ACTION_REQUIRED_PARAMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("jira", "create"): ("project_key", "issue_type"),
    ("render", "deploy"): ("service_id",),
    ("render", "tail_logs"): ("resource_id",),
    ("docker_hub", "publish"): ("image",),
    ("pypi", "publish"): ("artifact",),
    ("nuget", "publish"): ("artifact",),
    ("rubygems", "publish"): ("artifact",),
    ("github_releases", "create"): ("tag",),
    ("stripe", "create"): ("name",),
    ("postman", "validate"): ("collection",),
    ("insomnia", "validate"): ("collection",),
    ("openapi", "inspect"): ("spec",),
    ("openapi", "validate"): ("spec",),
    ("swagger", "inspect"): ("spec",),
    ("swagger", "validate"): ("spec",),
}

PROVIDER_ACTION_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("devcontainer", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
        "mutates_remote_state": False,
        "requires_confirmation": False,
    },
    ("docusaurus", "sync"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
        "mutates_remote_state": False,
        "requires_confirmation": False,
    },
    ("postman", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("insomnia", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("bruno", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("openapi", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("swagger", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("storybook", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("sentry", "tail"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("datadog", "tail"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("aws", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("azure", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("gcp", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("playwright", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("cypress", "validate"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("snyk", "scan"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("semgrep", "scan"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("codeql", "scan"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("trivy", "scan"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("gitleaks", "scan"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("ollama", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("vllm", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("release_please", "draft"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("changesets", "draft"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("semantic_release", "draft"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("github_releases", "draft"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("chrome_devtools", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
    ("cdp", "open"): {
        "risk_level": "low",
        "permission_policy": "ask_once_per_project",
    },
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
    IntegrationActionDefinition(
        action_id="disconnect",
        title="Disconnect",
        summary="Disconnect the Mission Control-owned connection state for this family without pretending host imports disappeared.",
        risk_level="medium",
        permission_policy="ask_every_time",
        preview_supported=True,
        mutates_remote_state=False,
        requires_confirmation=True,
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
            _action("create", "Create issue", "Create a work item against the connected source host.", command_template="gh issue create --title {title_q} --body {body_q}", mutates_remote_state=True, requires_confirmation=True, required_params=("title", "body")),
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
        cli_candidates=("gh", "acli"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("search", "Search work items", "Inspect tracked work items from the current host or CLI.", command_template="gh issue list --limit 20", risk_level="low", permission_policy="ask_once_per_project"),
            _action("create", "Create work item", "Create a tracked work item.", command_template="gh issue create --title {title_q} --body {body_q}", mutates_remote_state=True, requires_confirmation=True, required_params=("title", "body")),
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
        cli_candidates=("gh", "glab", "circleci", "buildkite-agent"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect CI status", "Inspect CI workflow status.", command_template="gh run list --limit 10", risk_level="low", permission_policy="ask_once_per_project"),
            _action("inspect_run", "Inspect CI run", "Inspect a specific CI run or pipeline.", command_template="gh run view {run_id_q}", risk_level="low", permission_policy="ask_once_per_project", required_params=("run_id",)),
            _action("tail_logs", "Tail CI logs", "Inspect logs for a specific CI run or pipeline.", command_template="gh run view {run_id_q} --log", risk_level="low", permission_policy="ask_once_per_project", required_params=("run_id",)),
            _action("rerun", "Rerun pipeline", "Rerun the most recent CI pipeline.", command_template="gh run rerun {run_id_q}", mutates_remote_state=True, requires_confirmation=True, required_params=("run_id",)),
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
        cli_candidates=("vercel", "netlify", "wrangler", "railway", "render"),
        legacy_account_keys=("vercel",),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect deployment", "Inspect deployment readiness or latest deployments.", command_template="vercel whoami", risk_level="low", permission_policy="ask_once_per_project"),
            _action("tail_logs", "Tail deployment logs", "Tail the latest deployment or service logs.", risk_level="low", permission_policy="ask_once_per_project"),
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
        cli_candidates=("supabase", "firebase", "neon", "pscale"),
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
        workspace_tokens=("sentry", "logrocket", "datadog", "newrelic", "new relic"),
        cli_candidates=("sentry-cli", "datadog-ci", "newrelic"),
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
        host_tokens=("slack", "discord", "teams", "microsoft teams"),
        config_files=(),
        workspace_tokens=("slack", "discord", "teams", "microsoft teams"),
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
        cli_candidates=("mintlify", "npm"),
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
        workspace_tokens=("kubectl", "helm", "kubernetes", "k8s"),
        cli_candidates=("kubectl", "helm"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("inspect", "Inspect cluster", "Inspect current cluster context and workload state.", command_template="kubectl config current-context", risk_level="low", permission_policy="ask_once_per_project"),
            _action("deploy", "Apply manifests", "Apply Kubernetes manifests.", command_template="kubectl apply -f {path_q}", risk_level="high", mutates_remote_state=True, requires_confirmation=True, required_params=("path",)),
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
        workspace_tokens=("terraform", "opentofu", "tofu"),
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
        config_files=("postman.json", ".postman.json", "postman_collection.json", ".postman_collection.json", ".insomnia", "insomnia.json", ".insomnia.json", "bruno.json"),
        workspace_tokens=("postman", "insomnia", "bruno"),
        cli_candidates=("newman", "inso", "bru"),
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
        cli_candidates=("swagger-cli",),
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
        cli_candidates=("npm", "storybook"),
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
        cli_candidates=("npm", "twine", "mvn", "cargo", "dotnet", "gem", "docker"),
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
        config_files=(".semgrep", ".github/codeql", ".gitleaks.toml", "trivy.yaml", "trivy.yml", ".snyk"),
        workspace_tokens=("snyk", "semgrep", "codeql", "trivy", "gitleaks", "dependabot"),
        cli_candidates=("snyk", "semgrep", "codeql", "trivy", "gitleaks"),
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
        host_tokens=("ollama", "lm studio", "lmstudio", "vllm"),
        config_files=(),
        workspace_tokens=("ollama", "lm studio", "lmstudio", "vllm"),
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
        workspace_tokens=("pinecone", "pinecone index", "weaviate", "weaviate cluster", "qdrant", "qdrant cloud", "chroma", "chroma db", "milvus", "milvus vector db"),
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
        workspace_tokens=("sourcegraph", "opengrok", "open grok", "zoekt"),
        cli_candidates=("src", "zoekt-query"),
        legacy_account_keys=(),
        actions=COMMON_ACTIONS + (
            _action("search", "Search code", "Run a code-search query through the configured engine.", risk_level="low", permission_policy="ask_once_per_project", required_params=("query",)),
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
        cli_candidates=("chrome",),
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
        host_tokens=("stripe", "paddle", "lemon", "lemon squeezy", "lemonsqueezy", "paypal", "paypal sandbox"),
        config_files=(),
        workspace_tokens=("stripe", "paddle", "lemon", "lemon squeezy", "lemonsqueezy", "paypal", "paypal sandbox"),
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
        host_tokens=("auth0", "clerk", "workos", "work os", "okta", "firebase auth", "supabase auth"),
        config_files=(".auth0", "auth0.json", ".auth0.json", "firebase.json", "supabase/config.toml"),
        workspace_tokens=("auth0", "clerk", "workos", "work os", "okta", "firebase auth", "supabase auth"),
        cli_candidates=("auth0", "firebase", "supabase"),
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
        host_tokens=("1password", "doppler", "vault", "secret manager", "aws secrets manager", "gcp secret manager", "google secret manager"),
        config_files=(),
        workspace_tokens=("1password", "doppler", "vault", "secret manager", "aws secrets manager", "gcp secret manager", "google secret manager"),
        cli_candidates=("op", "doppler", "vault", "aws", "gcloud"),
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
        host_tokens=("launchdarkly", "launch darkly", "statsig", "configcat", "config cat", "unleash", "posthog"),
        config_files=(),
        workspace_tokens=("launchdarkly", "launch darkly", "statsig", "configcat", "config cat", "unleash", "posthog"),
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
        host_tokens=("intercom", "zendesk", "help scout", "helpscout", "freshdesk"),
        config_files=(),
        workspace_tokens=("intercom", "zendesk", "help scout", "helpscout", "freshdesk"),
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
        host_tokens=("release please", "changesets", "semantic-release", "github releases", "launchnotes", "launch notes"),
        config_files=(".release-please-manifest.json", ".changeset", ".releaserc", "release.config.js"),
        workspace_tokens=("release please", "changesets", "semantic-release", "github releases", "launchnotes", "launch notes"),
        cli_candidates=("gh", "changeset", "release-please", "semantic-release"),
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


def _normalized_connection_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"connected", "ready"}:
        return "connected"
    if status in {"partial", "host_imported", "degraded"}:
        return "partial"
    if status in {"needs_setup", "disconnected", "unknown"}:
        return status
    return "unknown"


def _quote(value: Any) -> str:
    text = str(value)
    return '"' + text.replace('"', '\\"') + '"'


def _format_command(template: str, params: dict[str, Any]) -> str:
    values: dict[str, Any] = {}
    for key, value in params.items():
        values[key] = value
        values[f"{key}_q"] = _quote(value)
    return template.format(**values)


def _command_to_args(command: str) -> list[str]:
    return shlex.split(command, posix=True)


def _command_executable_name(command: str) -> str | None:
    try:
        args = _command_to_args(command)
    except ValueError:
        return None
    if not args:
        return None
    return args[0]


def _command_is_available(command: str) -> bool:
    executable = _command_executable_name(command)
    if not executable:
        return False
    return shutil.which(executable) is not None


def _execution_block_reason(
    *,
    missing_params: list[str],
    provider_verification_required: bool,
    suppressed_command_reason: str | None,
    execution_mode: str,
    command: str | None,
    executable_available: bool,
) -> str | None:
    if missing_params:
        return "missing_params"
    if provider_verification_required:
        return "provider_verification_required"
    if suppressed_command_reason:
        return suppressed_command_reason
    if not command and execution_mode == "guided_remote":
        return "no_local_command"
    if command and not executable_available:
        return "missing_executable"
    return None


def _provider_extra_required_params(provider: str | None, action_id: str) -> tuple[str, ...]:
    if not provider:
        return ()
    return PROVIDER_ACTION_REQUIRED_PARAMS.get((provider, action_id), ())


def _provider_display_name(provider: str | None) -> str:
    provider_id = str(provider or "").strip().lower()
    if not provider_id:
        return "This provider"
    display_names = {
        "gitlab": "GitLab",
        "github_actions": "GitHub Actions",
        "circleci": "CircleCI",
        "gitlab_ci": "GitLab CI",
        "bitbucket_pipelines": "Bitbucket Pipelines",
        "opentofu": "OpenTofu",
        "cloudflare_pages": "Cloudflare Pages",
        "github_issues": "GitHub Issues",
        "github_releases": "GitHub Releases",
        "docker_hub": "Docker Hub",
        "devcontainer": "Dev Containers",
        "codeql": "CodeQL",
        "chrome_devtools": "Chrome DevTools",
        "cdp": "Chrome DevTools Protocol",
        "auth0": "Auth0",
        "npm": "npm",
        "pypi": "PyPI",
        "crates": "crates.io",
        "nuget": "NuGet",
        "rubygems": "RubyGems",
        "new_relic": "New Relic",
        "aws_secrets_manager": "AWS Secrets Manager",
        "gcp_secret_manager": "GCP Secret Manager",
        "posthog_feature_flags": "PostHog Feature Flags",
        "lemon_squeezy": "Lemon Squeezy",
        "lm_studio": "LM Studio",
        "sourcegraph": "Sourcegraph",
        "vllm": "vLLM",
    }
    return display_names.get(provider_id, provider_id.replace("_", " ").title())


def _provider_guidance(provider: str | None, action_id: str) -> str | None:
    if not provider:
        return None
    guidance = PROVIDER_ACTION_GUIDANCE.get(provider, {})
    return guidance.get(action_id) or guidance.get("inspect")


def _effective_action_metadata(action: IntegrationActionDefinition, provider: str | None) -> dict[str, Any]:
    metadata = {
        "risk_level": action.risk_level,
        "permission_policy": action.permission_policy,
        "mutates_remote_state": action.mutates_remote_state,
        "requires_confirmation": action.requires_confirmation,
    }
    if provider:
        metadata.update(PROVIDER_ACTION_OVERRIDES.get((provider, action.action_id), {}))
    return metadata


def _default_provider_guidance(
    *,
    provider: str | None,
    action: IntegrationActionDefinition,
    action_metadata: dict[str, Any],
    command_template: str | None,
) -> str | None:
    if not provider or not command_template:
        return None
    provider_name = _provider_display_name(provider)
    if bool(action_metadata.get("mutates_remote_state")):
        return f"{provider_name} uses the local CLI when available and still mutates remote state, so approvals remain mandatory."
    if action.action_id in {"inspect", "inspect_run", "tail_logs", "tail", "search", "draft", "open"}:
        return f"{provider_name} uses the local CLI when available, but the result still depends on live provider state rather than repo-local proof."
    if action.action_id in {"validate", "scan"}:
        return f"{provider_name} uses the local CLI when available and evaluates the current repo or runtime state rather than a static registry hint."
    return f"{provider_name} uses the local CLI when available, but the action still depends on live provider or runtime state rather than repo-local proof."


def _read_git_remote_url(root: Path | None) -> str:
    if root is None:
        return ""
    git_dir = root / ".git"
    config_path = git_dir / "config"
    if not config_path.exists():
        return ""
    text = _safe_read_text(config_path)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("url ="):
            return stripped.partition("=")[2].strip().lower()
    return ""


def _git_remote_hostname(git_remote_url: str) -> str:
    remote = str(git_remote_url or "").strip().lower()
    if not remote:
        return ""
    if "://" in remote:
        return str(urlsplit(remote).hostname or "").strip().rstrip(".")
    scp_like = remote
    if "@" in scp_like:
        scp_like = scp_like.rsplit("@", 1)[1]
    host, separator, _remainder = scp_like.partition(":")
    if separator and host and "/" not in host:
        return host.strip().rstrip(".")
    return ""


def _git_remote_host_matches_provider(hostname: str, provider: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    exact_hosts = {
        "github": ("github.com", "ssh.github.com"),
        "gitlab": ("gitlab.com",),
        "bitbucket": ("bitbucket.org",),
    }.get(provider, ())
    if any(host == exact_host or host.endswith(f".{exact_host}") for exact_host in exact_hosts):
        return True
    first_label = host.split(".", 1)[0]
    return provider in {"gitlab", "bitbucket"} and first_label == provider


PROVIDER_COMMANDS: dict[str, dict[str, str | None]] = {
        "github": {
            "search": "gh repo view --json name,defaultBranchRef,isPrivate,url",
            "create": "gh issue create --title {title_q} --body {body_q}",
            "inspect": "gh repo view --json name,defaultBranchRef,isPrivate,url",
        },
        "gitlab": {
            "search": "glab repo view",
            "create": "glab issue create --title {title_q} --description {body_q}",
            "inspect": "glab repo view",
        },
        "bitbucket": {
            "inspect": None,
            "search": None,
            "create": None,
        },
        "github_issues": {
            "search": "gh issue list --limit 20",
            "create": "gh issue create --title {title_q} --body {body_q}",
        },
        "jira": {
            "search": 'acli jira workitem search --jql "order by updated DESC" --limit 20 --json',
            "create": "acli jira workitem create --summary {title_q} --description {body_q} --project {project_key_q} --type {issue_type_q} --json",
        },
        "linear": {
            "search": None,
            "create": None,
        },
        "docker": {
            "validate": "docker --version",
            "inspect": "docker --version",
        },
        "devcontainer": {
            "validate": "devcontainer read-configuration --workspace-folder .",
            "open": "devcontainer up --workspace-folder .",
            "inspect": "devcontainer read-configuration --workspace-folder .",
        },
        "github_actions": {
            "inspect": "gh run list --limit 10 --json databaseId,status,conclusion,name,workflowName",
            "inspect_run": "gh run view {run_id_q}",
            "tail_logs": "gh run view {run_id_q} --log",
            "rerun": "gh run rerun {run_id_q}",
        },
        "gitlab_ci": {
            "inspect": "glab ci list --output json",
            "inspect_run": "glab ci get --pipeline-id {run_id_q} --with-job-details --output json",
            "tail_logs": "glab ci trace --pipeline-id {run_id_q}",
        },
        "bitbucket_pipelines": {
            "inspect": None,
            "inspect_run": None,
            "tail_logs": None,
            "rerun": None,
        },
        "circleci": {
            "inspect": "circleci config validate .circleci/config.yml",
        },
        "buildkite": {
            "inspect": "buildkite-agent pipeline upload --dry-run .buildkite/pipeline.yml",
        },
        "figma": {
            "inspect": None,
        },
        "slack": {
            "draft": None,
            "create": None,
        },
        "discord": {
            "draft": None,
            "create": None,
        },
        "teams": {
            "draft": None,
            "create": None,
        },
        "notion": {
            "inspect": None,
            "sync": None,
        },
        "confluence": {
            "inspect": None,
            "sync": None,
        },
        "vercel": {
            "inspect": "vercel whoami",
            "deploy": "vercel deploy --yes",
        },
        "netlify": {
            "inspect": "netlify status",
            "deploy": "netlify deploy --prod",
        },
        "cloudflare_pages": {
            "inspect": "wrangler pages project list --json",
            "tail_logs": "wrangler pages deployment tail",
            "deploy": "wrangler pages deploy {directory_q}",
        },
        "railway": {
            "inspect": "railway status --json",
            "tail_logs": "railway logs --deployment --latest --lines 200 --json",
            "deploy": "railway up",
        },
        "render": {
            "inspect": "render services --output json",
            "tail_logs": "render logs --resources {resource_id_q} --limit 200 --output json",
            "deploy": "render deploys create {service_id_q} --wait",
        },
        "supabase": {
            "inspect": "supabase projects list",
            "sync": "supabase db push",
        },
        "firebase": {
            "inspect": "firebase apps:list --json",
            "sync": "firebase deploy --only firestore",
        },
        "neon": {
            "inspect": "neon projects list --output json",
        },
        "planetscale": {
            "inspect": "pscale database list",
        },
        "sentry": {
            "inspect": "sentry-cli info",
            "tail": "sentry-cli releases list",
        },
        "logrocket": {
            "inspect": None,
            "tail": None,
        },
        "datadog": {
            "inspect": "datadog-ci --version",
            "tail": "datadog-ci gate evaluate",
        },
        "new_relic": {
            "inspect": "newrelic --version",
        },
        "launchdarkly": {
            "inspect": None,
            "sync": None,
        },
        "statsig": {
            "inspect": None,
            "sync": None,
        },
        "configcat": {
            "inspect": None,
            "sync": None,
        },
        "unleash": {
            "inspect": None,
            "sync": None,
        },
        "posthog_feature_flags": {
            "inspect": None,
            "sync": None,
        },
        "posthog": {
            "inspect": None,
        },
        "amplitude": {
            "inspect": None,
        },
        "mixpanel": {
            "inspect": None,
        },
        "plausible": {
            "inspect": None,
        },
        "postman": {
            "inspect": "newman --version",
            "validate": "newman run {collection_q}",
        },
        "insomnia": {
            "inspect": "inso --version",
            "validate": "inso run test {collection_q}",
        },
        "opentofu": {
            "validate": "tofu validate",
            "deploy": "tofu apply -auto-approve",
        },
        "aws": {
            "inspect": "aws sts get-caller-identity",
            "open": "aws configure list",
        },
        "azure": {
            "inspect": "az account show --output json",
            "open": "az login",
        },
        "gcp": {
            "inspect": "gcloud config list --format json",
            "open": "gcloud auth login",
        },
        "bruno": {
            "inspect": "bru --version",
            "validate": "bru run",
        },
        "cypress": {
            "validate": "cypress run",
        },
        "docusaurus": {
            "inspect": "npm exec docusaurus -- --help",
            "sync": "npm exec docusaurus -- build",
        },
        "storybook": {
            "validate": "npm exec storybook -- build",
        },
        "vllm": {
            "inspect": "vllm --help",
            "open": "vllm serve --help",
        },
        "lm_studio": {
            "inspect": None,
            "open": None,
        },
        "npm": {
            "inspect": "npm whoami",
            "publish": "npm publish",
        },
        "pypi": {
            "inspect": "twine --version",
            "publish": "twine upload {artifact_q}",
        },
        "maven": {
            "inspect": "mvn --version",
            "publish": "mvn deploy -DskipTests",
        },
        "crates": {
            "inspect": "cargo --version",
            "publish": "cargo publish --dry-run",
        },
        "nuget": {
            "inspect": "dotnet nuget list source",
            "publish": "dotnet nuget push {artifact_q}",
        },
        "rubygems": {
            "inspect": "gem env",
            "publish": "gem push {artifact_q}",
        },
        "docker_hub": {
            "inspect": "docker info --format {{json .}}",
            "publish": "docker push {image_q}",
        },
        "kubernetes": {
            "inspect": "kubectl config current-context",
            "deploy": "kubectl apply -f {path_q}",
        },
        "dependabot": {
            "scan": None,
        },
        "terraform": {
            "validate": "terraform validate",
            "deploy": "terraform apply -auto-approve",
        },
        "aws": {
            "inspect": "aws sts get-caller-identity",
            "open": "aws configure list",
        },
        "mintlify": {
            "inspect": "mintlify --help",
        },
        "playwright": {
            "validate": "playwright test",
        },
        "gitleaks": {
            "scan": "gitleaks dir . --redact",
        },
        "codeql": {
            "scan": "codeql resolve qlpacks",
        },
        "ollama": {
            "inspect": "ollama list",
            "open": "ollama serve",
        },
        "snyk": {
            "scan": "snyk test --json",
        },
        "semgrep": {
            "scan": "semgrep scan --json",
        },
        "trivy": {
            "scan": "trivy fs --format json .",
        },
        "onepassword": {
            "inspect": "op vault list --format json",
        },
        "doppler": {
            "inspect": "doppler configs",
        },
        "vault": {
            "inspect": "vault status -format=json",
        },
        "aws_secrets_manager": {
            "inspect": "aws secretsmanager list-secrets --max-results 20 --output json",
        },
        "gcp_secret_manager": {
            "inspect": "gcloud secrets list --format json",
        },
        "intercom": {
            "search": None,
            "create": None,
        },
        "zendesk": {
            "search": None,
            "create": None,
        },
        "help_scout": {
            "search": None,
            "create": None,
        },
        "freshdesk": {
            "search": None,
            "create": None,
        },
        "changesets": {
            "draft": "changeset status",
            "create": "changeset version",
        },
        "release_please": {
            "draft": "release-please manifest-pr --dry-run",
            "create": "release-please github-release",
        },
        "semantic_release": {
            "draft": "semantic-release --dry-run",
            "create": "semantic-release",
        },
        "github_releases": {
            "draft": "gh release view --json name,tagName,isDraft",
            "create": "gh release create {tag_q}",
        },
        "launchnotes": {
            "draft": None,
            "create": None,
        },
        "stripe": {
            "inspect": "stripe config --list",
            "create": "stripe customers create --name {name_q}",
        },
        "paddle": {
            "inspect": None,
            "create": None,
        },
        "lemon_squeezy": {
            "inspect": None,
            "create": None,
        },
        "paypal_sandbox": {
            "inspect": None,
            "create": None,
        },
        "openapi": {
            "inspect": "swagger-cli validate {spec_q}",
            "validate": "swagger-cli validate {spec_q}",
        },
        "swagger": {
            "inspect": "swagger-cli validate {spec_q}",
            "validate": "swagger-cli validate {spec_q}",
        },
        "sourcegraph": {
            "search": "src search -json {query_q}",
        },
        "opengrok": {
            "search": None,
        },
        "zoekt": {
            "search": "zoekt-query {query_q}",
        },
        "pinecone": {
            "inspect": None,
            "search": None,
        },
        "weaviate": {
            "inspect": None,
            "search": None,
        },
        "qdrant": {
            "inspect": None,
            "search": None,
        },
        "chroma": {
            "inspect": None,
            "search": None,
        },
        "milvus": {
            "inspect": None,
            "search": None,
        },
        "chrome_devtools": {
            "inspect": "chrome --version",
            "open": "chrome --remote-debugging-port=9222 about:blank",
        },
        "cdp": {
            "inspect": "chrome --version",
            "open": "chrome --remote-debugging-port=9222 about:blank",
        },
        "auth0": {
            "inspect": "auth0 apps list --json",
        },
        "clerk": {
            "inspect": None,
        },
        "workos": {
            "inspect": None,
        },
        "okta": {
            "inspect": None,
        },
        "firebase_auth": {
            "inspect": "firebase apps:list --json",
        },
        "supabase_auth": {
            "inspect": "supabase projects list",
        },
    }


def _provider_supports_action(provider: str, action_id: str) -> bool:
    return action_id in PROVIDER_COMMANDS.get(provider, {})


def _provider_command_template(provider: str, action_id: str) -> str | None:
    return PROVIDER_COMMANDS.get(provider, {}).get(action_id)


def _supported_providers_for_action(
    family: IntegrationFamilyDefinition,
    action: IntegrationActionDefinition,
) -> list[str]:
    return [provider for provider in family.providers if _provider_supports_action(provider, action.action_id)]


def _action_support_mode(
    family: IntegrationFamilyDefinition,
    action: IntegrationActionDefinition,
) -> str:
    if action.action_id in {"import_host_state", "connect", "disconnect", "inspect_status"}:
        return "registry_state"
    if _supported_providers_for_action(family, action):
        return "provider_specific"
    if action.command_template:
        return "family_default"
    if family.providers:
        return "guided_only"
    return "unsupported"


def _context_requirement_reason(
    *,
    family: IntegrationFamilyDefinition,
    action: IntegrationActionDefinition,
    resolved_provider: str | None,
    supported_providers: list[str],
) -> str | None:
    if resolved_provider:
        return None
    if len(family.providers) > 1 and supported_providers:
        return "provider_context_missing"
    return None


def _provider_context_verified(
    *,
    family: IntegrationFamilyDefinition,
    resolved_provider: str | None,
    connection_status: str,
    connection_providers: list[str],
) -> bool:
    if connection_status != "connected":
        return False
    if len(family.providers) == 1:
        return True
    if resolved_provider and resolved_provider in connection_providers:
        return True
    return False


def _provider_context_source(
    *,
    family: IntegrationFamilyDefinition,
    resolved_provider: str | None,
    connection_status: str,
    connection_providers: list[str],
    has_host_import: bool,
    has_workspace_signal: bool,
    has_any_cli_signal: bool,
) -> str:
    if _provider_context_verified(
        family=family,
        resolved_provider=resolved_provider,
        connection_status=connection_status,
        connection_providers=connection_providers,
    ):
        return "connection"
    if resolved_provider and has_workspace_signal:
        return "workspace"
    if resolved_provider and has_host_import:
        return "host_import"
    if connection_status == "connected":
        return "connection_family_only"
    if has_host_import:
        return "host_import_only"
    if has_workspace_signal:
        return "workspace_only"
    if has_any_cli_signal:
        return "standalone_cli_only"
    return "none"


def _provider_context_status(*, provider_lane_resolved: bool, provider_context_verified: bool, provider_context_source: str) -> str:
    if provider_context_verified:
        return "verified"
    if provider_lane_resolved and provider_context_source in {"workspace", "host_import", "connection_family_only"}:
        return "inferred"
    return "missing"


def _provider_verification_reason(
    *,
    action_metadata: dict[str, Any],
    execution_mode: str,
    provider_lane_resolved: bool,
    provider_context_verified: bool,
    provider_context_source: str,
) -> str | None:
    if not provider_lane_resolved or provider_context_verified:
        return None
    if execution_mode != "guided_remote":
        return None
    if not bool(action_metadata.get("mutates_remote_state")):
        return None
    if provider_context_source in {"workspace", "host_import", "connection_family_only"}:
        return "provider_verification_required"
    return None


def _provider_hint_tokens(provider: str) -> list[str]:
    tokens = {
        provider.lower(),
        provider.replace("_", " ").lower(),
        *[token.lower() for token in PROVIDER_CLIS.get(provider, ()) if len(token) >= 3],
        *[
            token.lower()
            for token in PROVIDER_TOKEN_MARKERS.get(provider, ())
            if len(token) >= 3 or " " in token or any(char.isdigit() for char in token)
        ],
    }
    return _dedupe_strs([token for token in tokens if token])


def _provider_hints_for_paths(family: IntegrationFamilyDefinition, matched_paths: list[str]) -> list[str]:
    lowered_paths = [item.lower() for item in matched_paths]
    hints: list[str] = []
    for provider in family.providers:
        provider_tokens = _provider_hint_tokens(provider)
        if any(_contains_token(path, token) for path in lowered_paths for token in provider_tokens):
            hints.append(provider)
    return _dedupe_strs(hints or [provider for provider in family.providers if provider])


def _family_token_candidates(family: IntegrationFamilyDefinition) -> list[str]:
    return _dedupe_strs([*family.workspace_tokens])


def _contains_token(text: str, token: str) -> bool:
    lowered_text = str(text or "").lower()
    lowered_token = str(token or "").strip().lower()
    if not lowered_text or not lowered_token:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9 ._:-]*", lowered_token):
        pattern = rf"(?<![a-z0-9]){re.escape(lowered_token)}(?![a-z0-9])"
        return re.search(pattern, lowered_text) is not None
    return lowered_token in lowered_text


def _path_matches_marker(path: str, marker: str) -> bool:
    lowered_path = str(path or "").lower()
    lowered_marker = str(marker or "").lower().rstrip("/")
    if not lowered_path or not lowered_marker:
        return False
    if (
        lowered_path == lowered_marker
        or lowered_path.endswith("/" + lowered_marker)
        or lowered_path.startswith(lowered_marker + "/")
        or Path(lowered_path).name == lowered_marker
    ):
        return True
    if "." in lowered_marker and Path(lowered_path).name.endswith(lowered_marker):
        return True
    return False


def _family_workspace_markers(family: IntegrationFamilyDefinition) -> tuple[str, ...]:
    markers = list(family.config_files)
    for provider in family.providers:
        markers.extend(PROVIDER_WORKSPACE_MARKERS.get(provider, ()))
    return tuple(_dedupe_strs([str(item) for item in markers if str(item).strip()]))


def _family_workspace_evidence_files(*, family: IntegrationFamilyDefinition, relative_files: list[str]) -> list[str]:
    markers = _family_workspace_markers(family)
    return [
        path
        for path in relative_files
        if any(_path_matches_marker(path, marker) for marker in markers)
    ]


def _host_import_entries_for_family(registry: dict[str, Any], family_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for host_name, families in dict(registry.get("host_imports") or {}).items():
        payload = dict(dict(families or {}).get(family_id) or {})
        if not payload:
            continue
        for path in list(payload.get("paths") or []):
            entries.append({"host": host_name, "path": str(path)})
    return entries


def _execution_mode(*, action_id: str, command_template: str | None, provider: str | None) -> str:
    if action_id in {"import_host_state", "connect", "disconnect", "inspect_status"}:
        return "registry_state"
    if command_template:
        return "local_cli"
    if provider:
        return "guided_remote"
    return "unavailable"


def _provider_cli_candidates(provider: str | None) -> tuple[str, ...]:
    if not provider:
        return ()
    return PROVIDER_CLIS.get(provider, ())


def _provider_signal_breakdown(
    *,
    family: IntegrationFamilyDefinition,
    connection: dict[str, Any],
    detected_files: list[str],
    token_hits: list[str],
    installed_clis: list[str],
    git_remote_url: str,
) -> dict[str, dict[str, Any]]:
    breakdown: dict[str, dict[str, Any]] = {}
    connection_providers = [str(item) for item in list(connection.get("providers") or [])]
    connection_source = str(connection.get("connection_source") or "mission_control")
    git_remote_host = _git_remote_hostname(git_remote_url)
    lowered_files = [path.lower() for path in detected_files]
    lowered_hits = {hit.lower() for hit in token_hits}
    installed_cli_set = {item.lower() for item in installed_clis}

    for provider in family.providers:
        entry = {
            "connection": 0,
            "git_remote": 0,
            "workspace_marker": 0,
            "workspace_token": 0,
            "cli": 0,
            "total": 0,
            "has_non_cli_evidence": False,
            "suppressed_cli_only": False,
        }
        if provider in connection_providers:
            entry["connection"] = 80 if connection_source in AUTHORITATIVE_CONNECTION_SOURCES else 40
        if git_remote_host:
            if _git_remote_host_matches_provider(git_remote_host, "github") and provider == "github":
                entry["git_remote"] = 70
            if _git_remote_host_matches_provider(git_remote_host, "gitlab") and provider == "gitlab":
                entry["git_remote"] = 70
            if _git_remote_host_matches_provider(git_remote_host, "bitbucket") and provider == "bitbucket":
                entry["git_remote"] = 70
        markers = PROVIDER_WORKSPACE_MARKERS.get(provider, ())
        if any(_path_matches_marker(file_path, marker) for file_path in lowered_files for marker in markers):
            entry["workspace_marker"] = 60
        tokens = PROVIDER_TOKEN_MARKERS.get(provider, ())
        if any(token.lower() in lowered_hits for token in tokens):
            entry["workspace_token"] = 30
        entry["has_non_cli_evidence"] = bool(
            entry["connection"] or entry["git_remote"] or entry["workspace_marker"] or entry["workspace_token"]
        )
        required_clis = PROVIDER_CLIS.get(provider, ())
        if required_clis and all(cli.lower() in installed_cli_set for cli in required_clis):
            if entry["has_non_cli_evidence"]:
                entry["cli"] = 10
            else:
                entry["suppressed_cli_only"] = True
        entry["total"] = int(entry["connection"]) + int(entry["git_remote"]) + int(entry["workspace_marker"]) + int(entry["workspace_token"]) + int(entry["cli"])
        breakdown[provider] = entry
    return breakdown


def _provider_candidates_for_family(
    *,
    family: IntegrationFamilyDefinition,
    connection: dict[str, Any],
    detected_files: list[str],
    token_hits: list[str],
    installed_clis: list[str],
    git_remote_url: str,
) -> list[str]:
    breakdown = _provider_signal_breakdown(
        family=family,
        connection=connection,
        detected_files=detected_files,
        token_hits=token_hits,
        installed_clis=installed_clis,
        git_remote_url=git_remote_url,
    )
    scores = {
        provider: int(entry["total"])
        for provider, entry in breakdown.items()
        if int(entry["total"]) > 0 and bool(entry["has_non_cli_evidence"])
    }
    priority = PROVIDER_PRIORITY_BY_FAMILY.get(family.family_id, family.providers)
    priority_index = {provider: index for index, provider in enumerate(priority)}
    ordered = sorted(
        scores,
        key=lambda provider: (-scores[provider], priority_index.get(provider, len(priority_index)), provider),
    )
    return _dedupe_strs(ordered)


def _provider_resolution_state(*, provider: str | None, cli_only_candidates_suppressed: list[str]) -> str:
    if provider:
        return "resolved"
    if cli_only_candidates_suppressed:
        return "suppressed_cli_only"
    return "unresolved"


def _resolve_provider_command(
    *,
    family: IntegrationFamilyDefinition,
    action: IntegrationActionDefinition,
    connection: dict[str, Any],
    detected_files: list[str],
    token_hits: list[str],
    installed_clis: list[str],
    git_remote_url: str,
) -> tuple[str | None, list[str], str | None]:
    candidates = _provider_candidates_for_family(
        family=family,
        connection=connection,
        detected_files=detected_files,
        token_hits=token_hits,
        installed_clis=installed_clis,
        git_remote_url=git_remote_url,
    )
    supported_candidates = [provider for provider in candidates if _provider_supports_action(provider, action.action_id)]
    for provider in supported_candidates:
        template = _provider_command_template(provider, action.action_id)
        if template and _command_is_available(template):
            return template, candidates, provider
    for provider in supported_candidates:
        template = _provider_command_template(provider, action.action_id)
        return template, candidates, provider
    if candidates and len(family.providers) == 1 and action.command_template:
        return action.command_template, candidates, candidates[0]
    return None, candidates, None


def _provider_status_from_legacy(account: dict[str, Any]) -> str:
    status = str(account.get("status") or "").strip().lower()
    if status == "connected":
        return "connected"
    if status in {"configure_manually", "coming_soon"}:
        return "needs_setup"
    if status in {"ready", "partial", "needs_setup", "disconnected", "unknown"}:
        return _normalized_connection_status(status)
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
    for family_id, connection in list(normalized["connections"].items()):
        connection["family"] = str(connection.get("family") or family_id)
        connection["status"] = _normalized_connection_status(connection.get("status"))
        connection["providers"] = _dedupe_strs([str(item) for item in list(connection.get("providers") or []) if str(item).strip()])
        connection["connection_source"] = str(connection.get("connection_source") or "mission_control")
        connection["host_imported"] = bool(connection.get("host_imported"))
        connection["approval_policy"] = str(connection.get("approval_policy") or "ask_every_time")
        connection["notes"] = _dedupe_strs([str(item) for item in list(connection.get("notes") or []) if str(item).strip()])

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


def _merge_connection_entry(
    existing: dict[str, Any] | None,
    *,
    family: IntegrationFamilyDefinition,
    status: str,
    providers: list[str],
    connection_source: str,
    host_imported: bool,
    notes: list[str],
) -> dict[str, Any]:
    current = dict(existing or {})
    current_source = str(current.get("connection_source") or "mission_control")
    current_status = _normalized_connection_status(current.get("status"))
    preserve_authoritative = current_source in AUTHORITATIVE_CONNECTION_SOURCES and current_status in {"connected", "partial"}
    merged = {
        "family": family.family_id,
        "status": current_status if current_source in AUTHORITATIVE_CONNECTION_SOURCES and current_status == "connected" else _normalized_connection_status(status),
        "providers": _dedupe_strs([str(item) for item in list(current.get("providers") or [])] + providers),
        "connection_source": current_source if preserve_authoritative else connection_source,
        "host_imported": bool(current.get("host_imported")) or host_imported,
        "approval_policy": str(current.get("approval_policy") or "ask_every_time"),
        "notes": _dedupe_strs([str(item) for item in list(current.get("notes") or [])] + notes),
    }
    if preserve_authoritative:
        merged["status"] = current_status
    return merged


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
    return any(_contains_token(normalized, token) for token in tokens)


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
                provider_hints = _provider_hints_for_paths(family, matched_paths)
                imported[family.family_id] = {
                    "detected": True,
                    "paths": _dedupe_strs(matched_paths),
                    "provider_hints": provider_hints,
                }
                registry["connections"][family.family_id] = _merge_connection_entry(
                    dict(registry["connections"].get(family.family_id) or {}),
                    family=family,
                    status="partial",
                    providers=provider_hints,
                    connection_source=f"{host_name}_host",
                    host_imported=True,
                    notes=[f"Imported metadata from {host_name} host assets. Host import does not override Mission Control-owned connection state."],
                )
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
        if any(
            part.startswith(".")
            and part not in {".github", ".storybook", ".devcontainer", ".linear", ".jira", ".circleci", ".buildkite", ".changeset", ".semgrep", ".insomnia", ".auth0"}
            for part in rel.parts[:-1]
        ):
            continue
        results.append(rel.as_posix())
    return results


def _workspace_haystack(root: Path, relative_files: list[str]) -> str:
    chunks: list[str] = []
    for relative in relative_files:
        name = Path(relative).name.lower()
        if name in {
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "readme.md",
            "firebase.json",
            "netlify.toml",
            "vercel.json",
            "wrangler.toml",
            "railway.json",
            "render.yaml",
            "bitbucket-pipelines.yml",
            ".gitlab-ci.yml",
        }:
            chunks.append(_safe_read_text(root / relative)[:4000])
    return "\n".join(chunks).lower()


def _infer_cloudflare_pages_directory(root: Path | None, relative_files: list[str]) -> str | None:
    if root is None or not root.exists():
        return None
    for relative in relative_files:
        path = Path(relative)
        if path.name.lower() != "wrangler.toml":
            continue
        text = _safe_read_text(root / relative)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("pages_build_output_dir"):
                continue
            _, _, raw_value = stripped.partition("=")
            value = raw_value.strip().strip('"').strip("'")
            if value:
                return value
    for candidate in ("dist", "build", "public", "out"):
        if (root / candidate).exists():
            return candidate
    return None


def _infer_openapi_spec_path(relative_files: list[str]) -> str | None:
    for candidate in ("openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.yml"):
        for relative in relative_files:
            if relative == candidate or relative.endswith("/" + candidate):
                return relative
    return None


def _infer_api_client_collection_path(*, provider: str | None, relative_files: list[str]) -> str | None:
    if provider == "postman":
        for relative in relative_files:
            name = Path(relative).name.lower()
            if name in {"postman_collection.json", ".postman_collection.json"} or name.endswith(".postman_collection.json"):
                return relative
        for relative in relative_files:
            name = Path(relative).name.lower()
            if name in {"postman.json", ".postman.json"}:
                return relative
    if provider == "insomnia":
        for relative in relative_files:
            name = Path(relative).name.lower()
            if name in {"insomnia.json", ".insomnia.json"}:
                return relative
        for relative in relative_files:
            if relative.lower().startswith(".insomnia/") and relative.lower().endswith(".json"):
                return relative
    return None


def _provider_default_params(
    *,
    provider: str | None,
    action_id: str,
    root: Path | None,
    relative_files: list[str],
) -> dict[str, Any]:
    if provider == "cloudflare_pages" and action_id == "deploy":
        directory = _infer_cloudflare_pages_directory(root, relative_files)
        if directory:
            return {"directory": directory}
    if provider in {"postman", "insomnia"} and action_id == "validate":
        collection = _infer_api_client_collection_path(provider=provider, relative_files=relative_files)
        if collection:
            return {"collection": collection}
    if provider in {"openapi", "swagger"} and action_id in {"inspect", "validate"}:
        spec = _infer_openapi_spec_path(relative_files)
        if spec:
            return {"spec": spec}
    return {}


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
    git_remote_url = _read_git_remote_url(root)
    statuses: list[dict[str, Any]] = []
    for family in FAMILIES:
        connection = _connection_status_for_family(registry, family)
        connection_status = _normalized_connection_status(connection.get("status"))
        detected_files = _family_workspace_evidence_files(family=family, relative_files=relative_files)
        token_hits = [token for token in _family_token_candidates(family) if token and _contains_token(haystack, token)]
        installed_clis = [cli for cli in family.cli_candidates if shutil.which(cli)]
        provider_candidates = _provider_candidates_for_family(
            family=family,
            connection=connection,
            detected_files=detected_files,
            token_hits=token_hits,
            installed_clis=installed_clis,
            git_remote_url=git_remote_url,
        )
        provider_signal_breakdown = _provider_signal_breakdown(
            family=family,
            connection=connection,
            detected_files=detected_files,
            token_hits=token_hits,
            installed_clis=installed_clis,
            git_remote_url=git_remote_url,
        )
        resolved_provider = provider_candidates[0] if provider_candidates else None
        displayed_providers = provider_candidates or list(connection.get("providers") or []) or list(family.providers)
        connection_providers = [str(item) for item in list(connection.get("providers") or []) if str(item).strip()]
        connection_provider_count = len(connection_providers)
        has_host_import = bool(connection.get("host_imported"))
        has_workspace_signal = bool(detected_files or token_hits)
        has_connection = connection_status == "connected"
        has_context_signal = has_connection or has_host_import or has_workspace_signal
        provider_cli_candidates = list(_provider_cli_candidates(resolved_provider))
        installed_provider_clis = [cli for cli in provider_cli_candidates if shutil.which(cli)]
        has_any_cli_signal = bool(installed_clis)
        provider_context_verified = _provider_context_verified(
            family=family,
            resolved_provider=resolved_provider,
            connection_status=connection_status,
            connection_providers=connection_providers,
        )
        provider_context_source = _provider_context_source(
            family=family,
            resolved_provider=resolved_provider,
            connection_status=connection_status,
            connection_providers=connection_providers,
            has_host_import=has_host_import,
            has_workspace_signal=has_workspace_signal,
            has_any_cli_signal=has_any_cli_signal,
        )
        connection_without_provider_identity = bool(
            has_connection and len(family.providers) > 1 and not connection_provider_count
        )
        available_actions: list[dict[str, Any]] = []
        blockers: list[str] = []
        recommended_fixes: list[str] = []
        for action in family.actions:
            action_template, _, action_provider = _resolve_provider_command(
                family=family,
                action=action,
                connection=connection,
                detected_files=detected_files,
                token_hits=token_hits,
                installed_clis=installed_clis,
                git_remote_url=git_remote_url,
            )
            supported_providers = _supported_providers_for_action(family, action)
            support_mode = _action_support_mode(family, action)
            action_metadata = _effective_action_metadata(action, action_provider)
            action_command_ready = bool(action_template and _command_is_available(action_template))
            action_required_params = _dedupe_strs(
                [
                    *[str(item) for item in action.required_params],
                    *[str(item) for item in _provider_extra_required_params(action_provider, action.action_id)],
                ]
            )
            execution_mode = _execution_mode(action_id=action.action_id, command_template=action_template, provider=action_provider)
            provider_lane_resolved = bool(action_provider and (not supported_providers or action_provider in supported_providers))
            provider_context_status = _provider_context_status(
                provider_lane_resolved=provider_lane_resolved,
                provider_context_verified=provider_context_verified,
                provider_context_source=provider_context_source,
            )
            provider_verification_reason = _provider_verification_reason(
                action_metadata=action_metadata,
                execution_mode=execution_mode,
                provider_lane_resolved=provider_lane_resolved,
                provider_context_verified=provider_context_verified,
                provider_context_source=provider_context_source,
            )
            provider_verification_required = bool(provider_verification_reason)
            context_requirement_reason = _context_requirement_reason(
                family=family,
                action=action,
                resolved_provider=action_provider,
                supported_providers=supported_providers,
            )
            context_required = bool(context_requirement_reason)
            suppressed_command_reason = context_requirement_reason if context_required and not action_template else None
            action_ready = bool(
                action.action_id in {"import_host_state", "connect", "disconnect", "inspect_status"}
                or (
                    execution_mode == "local_cli"
                    and action_command_ready
                    and has_context_signal
                )
                or (action_command_ready and has_context_signal)
                or (
                    execution_mode in {"guided_remote", "registry_state"}
                    and has_context_signal
                )
            )
            if provider_verification_required:
                action_ready = False
            available_actions.append(
                {
                    "action_id": action.action_id,
                    "title": action.title,
                    "summary": action.summary,
                    "risk_level": str(action_metadata["risk_level"]),
                    "permission_policy": str(action_metadata["permission_policy"]),
                    "preview_supported": action.preview_supported,
                    "mutates_remote_state": bool(action_metadata["mutates_remote_state"]),
                    "requires_confirmation": bool(action_metadata["requires_confirmation"]),
                    "required_params": action_required_params,
                    "status": "available" if action_ready else "needs_setup",
                    "provider": action_provider,
                    "command_template": action_template,
                    "command_ready": action_command_ready,
                    "execution_mode": execution_mode,
                    "provider_support_mode": support_mode,
                    "supported_providers": supported_providers,
                    "supported_provider_count": len(supported_providers),
                    "provider_lane_resolved": provider_lane_resolved,
                    "provider_context_verified": provider_context_verified,
                    "provider_context_source": provider_context_source,
                    "provider_context_status": provider_context_status,
                    "provider_verification_required": provider_verification_required,
                    "provider_verification_reason": provider_verification_reason,
                    "context_required": context_required,
                    "context_requirement_reason": context_requirement_reason,
                    "suppressed_command_reason": suppressed_command_reason,
                }
            )
        available_action_count = sum(1 for item in available_actions if item["status"] == "available")
        local_action_count = sum(
            1
            for item in available_actions
            if item["status"] == "available" and item["execution_mode"] == "local_cli"
        )
        guided_action_count = sum(
            1
            for item in available_actions
            if item["status"] == "available" and item["execution_mode"] == "guided_remote"
        )
        registry_action_count = sum(
            1
            for item in available_actions
            if item["status"] == "available" and item["execution_mode"] == "registry_state"
        )
        provider_specific_action_count = sum(
            1 for item in available_actions if item["provider_support_mode"] == "provider_specific"
        )
        guided_only_action_count = sum(
            1 for item in available_actions if item["provider_support_mode"] == "guided_only"
        )
        available_provider_lane_count = sum(
            1
            for item in available_actions
            if item["status"] == "available"
            and item["provider_lane_resolved"]
            and item["execution_mode"] != "registry_state"
        )
        context_blocked_action_count = sum(1 for item in available_actions if item["context_required"])
        verification_blocked_action_count = sum(1 for item in available_actions if item["provider_verification_required"])
        verification_blocked_action_ids = [
            str(item["action_id"])
            for item in available_actions
            if item["provider_verification_required"]
        ]
        has_actionable_lane = available_action_count > registry_action_count
        has_provider_cli = not provider_cli_candidates or len(installed_provider_clis) == len(provider_cli_candidates)
        if not has_context_signal:
            if has_any_cli_signal:
                blockers.append("Only standalone local CLIs were detected. Mission Control still needs workspace, host, or connection evidence before claiming this family is active.")
                recommended_fixes.append("Connect the provider or add workspace evidence before treating this lane as configured.")
            else:
                blockers.append("No host import, local CLI, or workspace signals were detected for this family.")
                recommended_fixes.append("Connect the provider in Mission Control or install the relevant local CLI before expecting a serious integration lane.")
            status = "needs_setup"
        elif provider_specific_action_count > 0 and has_connection and not provider_context_verified:
            status = "partial"
            blockers.append("Connection state exists, but Mission Control still lacks verified provider identity for provider-specific lanes in this family.")
            if connection_without_provider_identity:
                recommended_fixes.append("Reconnect this family through Mission Control with an explicit provider selection before treating it as ready.")
            else:
                recommended_fixes.append("Verify the connected provider in Mission Control before treating provider-specific lanes in this family as ready.")
            if resolved_provider and provider_context_source in {"workspace", "host_import"}:
                recommended_fixes.append(f"Workspace or host signals suggest `{resolved_provider}`, but Mission Control still needs a verified live connection for that provider.")
        elif has_connection and (
            available_provider_lane_count > 0
            or (guided_only_action_count > 0 and has_actionable_lane)
            or (available_action_count == registry_action_count and not provider_specific_action_count)
        ):
            status = "ready"
        elif local_action_count > 0 and (has_workspace_signal or has_host_import or has_connection):
            status = "ready"
        else:
            status = "partial"
            if provider_cli_candidates and not has_provider_cli and (has_connection or has_workspace_signal or has_host_import):
                blockers.append("A local CLI is still missing for the actionable lane in this family.")
                recommended_fixes.append(f"Install one of: {', '.join(provider_cli_candidates)}")
            elif family.cli_candidates and not has_any_cli_signal and (has_connection or has_workspace_signal or has_host_import):
                blockers.append("A local CLI is still missing for the actionable lane in this family.")
                recommended_fixes.append(f"Install one of: {', '.join(family.cli_candidates)}")
            if not has_connection and has_host_import:
                blockers.append("Only host-imported metadata is present. Mission Control has not verified a live provider session yet.")
                recommended_fixes.append("Refresh the connection in Mission Control or use a verified local CLI before treating this lane as live.")
            if has_workspace_signal and not has_connection:
                recommended_fixes.append("Workspace signals exist, but Mission Control has not verified the live provider context yet.")
        if verification_blocked_action_count:
            blockers.append("Some provider-specific guided actions remain blocked until Mission Control verifies the live provider identity for this family.")
            if resolved_provider:
                recommended_fixes.append(f"Verify the `{resolved_provider}` connection in Mission Control before using guided remote mutation actions in this family.")
        safe_commands = [
            template
            for action in family.actions
            for template, _, _provider in [
                _resolve_provider_command(
                    family=family,
                    action=action,
                    connection=connection,
                    detected_files=detected_files,
                    token_hits=token_hits,
                    installed_clis=installed_clis,
                    git_remote_url=git_remote_url,
                )
            ]
            if template and has_context_signal and not _effective_action_metadata(action, _provider).get("mutates_remote_state") and _command_is_available(template)
        ]
        signal_sources = _dedupe_strs(
            [
                "connection" if has_connection else "",
                "host_import" if has_host_import else "",
                "workspace" if has_workspace_signal else "",
                "standalone_cli" if has_any_cli_signal and not has_context_signal else "",
            ]
        )
        cli_only_candidates_suppressed = [
            provider
            for provider, entry in provider_signal_breakdown.items()
            if bool(entry.get("suppressed_cli_only"))
        ]
        provider_resolution_state = _provider_resolution_state(
            provider=resolved_provider,
            cli_only_candidates_suppressed=cli_only_candidates_suppressed,
        )
        artifacts = [{"type": "config_file", "path": path} for path in detected_files]
        artifacts.extend(
            {
                "type": "host_import_path",
                "host": item["host"],
                "path": item["path"],
            }
            for item in _host_import_entries_for_family(registry, family.family_id)
        )
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
                "providers": displayed_providers,
                "resolved_provider": resolved_provider,
                "provider_candidates": provider_candidates,
                "resolved_cli_candidates": provider_cli_candidates,
                "required_permissions": _dedupe_strs([str(item["permission_policy"]) for item in available_actions]),
                "available_action_count": available_action_count,
                "local_action_count": local_action_count,
                "guided_action_count": guided_action_count,
                "registry_action_count": registry_action_count,
                "provider_specific_action_count": provider_specific_action_count,
                "guided_only_action_count": guided_only_action_count,
                "available_provider_lane_count": available_provider_lane_count,
                "context_blocked_action_count": context_blocked_action_count,
                "verification_blocked_action_count": verification_blocked_action_count,
                "health": {
                    "cli_detected": installed_clis,
                    "resolved_cli_detected": installed_provider_clis,
                    "workspace_config_files": detected_files,
                    "workspace_token_hits": token_hits,
                    "workspace_signal_detected": has_workspace_signal,
                    "host_imported": has_host_import,
                    "host_import_detected": has_host_import,
                    "connection_status": connection_status,
                    "connection_detected": has_connection,
                    "connection_provider_count": connection_provider_count,
                    "connection_without_provider_identity": connection_without_provider_identity,
                    "provider_context_verified": provider_context_verified,
                    "provider_context_source": provider_context_source,
                    "provider_context_status": _provider_context_status(
                        provider_lane_resolved=bool(resolved_provider),
                        provider_context_verified=provider_context_verified,
                        provider_context_source=provider_context_source,
                    ),
                    "standalone_cli_detected": has_any_cli_signal and not has_context_signal,
                    "signal_sources": signal_sources,
                    "provider_signal_breakdown": provider_signal_breakdown,
                    "resolved_provider_evidence": dict(provider_signal_breakdown.get(resolved_provider) or {}),
                    "cli_only_candidates_suppressed": cli_only_candidates_suppressed,
                    "provider_resolution_state": provider_resolution_state,
                    "resolved_provider": resolved_provider,
                    "provider_candidates": provider_candidates,
                    "verification_blocked_action_ids": verification_blocked_action_ids,
                    "git_remote_url": git_remote_url or None,
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


def build_integration_health(registry_payload: dict[str, Any] | None) -> dict[str, Any]:
    registry = normalize_integration_registry(registry_payload, {})
    connections = list_connections(registry)
    status_counts: dict[str, int] = {}
    host_imported_count = 0
    authoritative_count = 0
    for connection in connections:
        status = _normalized_connection_status(connection.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if connection.get("host_imported"):
            host_imported_count += 1
        if str(connection.get("connection_source") or "") in AUTHORITATIVE_CONNECTION_SOURCES:
            authoritative_count += 1
    recent_actions = list(registry.get("action_history") or [])[-10:]
    failed_actions = [item for item in recent_actions if str(item.get("status") or "") == "failed"]
    return {
        "version": int(registry.get("version") or REGISTRY_VERSION),
        "family_count": len(FAMILIES),
        "connection_count": len([item for item in connections if _normalized_connection_status(item.get("status")) != "disconnected"]),
        "authoritative_connection_count": authoritative_count,
        "host_imported_count": host_imported_count,
        "status_counts": status_counts,
        "recent_action_failures": failed_actions,
        "host_import_roots": {
            host: [str(path) for path in roots]
            for host, roots in _host_scan_roots().items()
        },
    }


def build_integration_catalog_with_connections(registry_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    registry = normalize_integration_registry(registry_payload, {})
    rows: list[dict[str, Any]] = []
    for family in FAMILIES:
        connection = _connection_status_for_family(registry, family)
        rows.append(
            {
                **next(item for item in integration_catalog() if item["family"] == family.family_id),
                "status": _normalized_connection_status(connection.get("status") or "disconnected"),
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
    root = Path(workspace_path) if workspace_path else None
    relative_files = _relative_files(root) if root and root.exists() else []
    haystack = _workspace_haystack(root, relative_files) if root and root.exists() else ""
    git_remote_url = _read_git_remote_url(root)
    registry = normalize_integration_registry(registry_payload, {})
    connection = _connection_status_for_family(registry, family)
    detected_files = _family_workspace_evidence_files(family=family, relative_files=relative_files)
    token_hits = [token for token in _family_token_candidates(family) if token and _contains_token(haystack, token)]
    installed_clis = [cli for cli in family.cli_candidates if shutil.which(cli)]
    connection_status = _normalized_connection_status(connection.get("status"))
    connection_providers = [str(item) for item in list(connection.get("providers") or []) if str(item).strip()]
    has_host_import = bool(connection.get("host_imported"))
    has_workspace_signal = bool(detected_files or token_hits)
    has_any_cli_signal = bool(installed_clis)
    command_template, provider_candidates, resolved_provider = _resolve_provider_command(
        family=family,
        action=action,
        connection=connection,
        detected_files=detected_files,
        token_hits=token_hits,
        installed_clis=installed_clis,
        git_remote_url=git_remote_url,
    )
    provider_signal_breakdown = _provider_signal_breakdown(
        family=family,
        connection=connection,
        detected_files=detected_files,
        token_hits=token_hits,
        installed_clis=installed_clis,
        git_remote_url=git_remote_url,
    )
    cli_only_candidates_suppressed = [
        provider
        for provider, entry in provider_signal_breakdown.items()
        if bool(entry.get("suppressed_cli_only"))
    ]
    provider_resolution_state = _provider_resolution_state(
        provider=resolved_provider,
        cli_only_candidates_suppressed=cli_only_candidates_suppressed,
    )
    supported_providers = _supported_providers_for_action(family, action)
    support_mode = _action_support_mode(family, action)
    provider_context_verified = _provider_context_verified(
        family=family,
        resolved_provider=resolved_provider,
        connection_status=connection_status,
        connection_providers=connection_providers,
    )
    provider_context_source = _provider_context_source(
        family=family,
        resolved_provider=resolved_provider,
        connection_status=connection_status,
        connection_providers=connection_providers,
        has_host_import=has_host_import,
        has_workspace_signal=has_workspace_signal,
        has_any_cli_signal=has_any_cli_signal,
    )
    provider_lane_resolved = bool(resolved_provider and (not supported_providers or resolved_provider in supported_providers))
    provider_context_status = _provider_context_status(
        provider_lane_resolved=provider_lane_resolved,
        provider_context_verified=provider_context_verified,
        provider_context_source=provider_context_source,
    )
    action_metadata = _effective_action_metadata(action, resolved_provider)
    effective_params = {
        **_provider_default_params(
            provider=resolved_provider,
            action_id=action.action_id,
            root=root,
            relative_files=relative_files,
        ),
        **params,
    }
    missing = [
        name
        for name in (*action.required_params, *_provider_extra_required_params(resolved_provider, action.action_id))
        if name not in effective_params or effective_params[name] in {None, ""}
    ]
    command: str | None = None
    if command_template:
        if missing:
            command = command_template
        else:
            command = _format_command(command_template, effective_params)
    executable_available = bool(command and _command_is_available(command))
    executable_name = _command_executable_name(command or command_template or "")
    execution_mode = _execution_mode(action_id=action.action_id, command_template=command_template, provider=resolved_provider)
    provider_verification_reason = _provider_verification_reason(
        action_metadata=action_metadata,
        execution_mode=execution_mode,
        provider_lane_resolved=provider_lane_resolved,
        provider_context_verified=provider_context_verified,
        provider_context_source=provider_context_source,
    )
    provider_verification_required = bool(provider_verification_reason)
    context_requirement_reason = _context_requirement_reason(
        family=family,
        action=action,
        resolved_provider=resolved_provider,
        supported_providers=supported_providers,
    )
    context_required = bool(context_requirement_reason)
    suppressed_command_reason = context_requirement_reason if context_required and not command_template else None
    provider_guidance = _provider_guidance(resolved_provider, action.action_id) or _default_provider_guidance(
        provider=resolved_provider,
        action=action,
        action_metadata=action_metadata,
        command_template=command_template,
    )
    execution_block_reason = _execution_block_reason(
        missing_params=missing,
        provider_verification_required=provider_verification_required,
        suppressed_command_reason=suppressed_command_reason,
        execution_mode=execution_mode,
        command=command,
        executable_available=executable_available,
    )
    preflight_ready = execution_block_reason is None
    confirmation_eligible = bool(preflight_ready and action_metadata["requires_confirmation"])
    ready_to_execute = bool(preflight_ready and not action_metadata["requires_confirmation"])
    notes = [
        "Mission Control previews the action before execution so approvals are tied to a concrete command or host import step.",
        "Local execution stays shell-free and only runs when the previewed executable is actually present.",
        "A host import is metadata, not proof of live remote authorization.",
        f"Executable detected: {'yes' if executable_available else 'no'}.",
        f"Resolved provider: {resolved_provider or 'none'}.",
    ]
    if provider_context_status == "inferred":
        notes.append("Provider identity is inferred from workspace or host signals, but Mission Control has not verified a live provider session yet.")
    if provider_verification_required:
        notes.append("Guided remote mutation remains blocked until Mission Control verifies the live provider identity for this provider-specific lane.")
    if suppressed_command_reason == "provider_context_missing":
        notes.append("Executable preview was intentionally suppressed until Mission Control has real provider context for this family.")
    if effective_params != params:
        notes.append(f"Provider defaults were inferred for preview params: {json.dumps({key: value for key, value in effective_params.items() if key not in params}, sort_keys=True)}")
    if provider_guidance:
        notes.append(provider_guidance)
    return {
        "family": family.family_id,
        "action_id": action.action_id,
        "title": action.title,
        "summary": action.summary,
        "project_name": project_name,
        "workspace_path": workspace_path,
        "command": command,
        "risk_level": str(action_metadata["risk_level"]),
        "permission_policy": str(action_metadata["permission_policy"]),
        "preview_supported": action.preview_supported,
        "mutates_remote_state": bool(action_metadata["mutates_remote_state"]),
        "requires_confirmation": bool(action_metadata["requires_confirmation"]),
        "missing_params": missing,
        "provider": resolved_provider,
        "provider_candidates": provider_candidates,
        "provider_signal_breakdown": provider_signal_breakdown,
        "resolved_provider_evidence": dict(provider_signal_breakdown.get(resolved_provider) or {}),
        "cli_only_candidates_suppressed": cli_only_candidates_suppressed,
        "provider_resolution_state": provider_resolution_state,
        "provider_support_mode": support_mode,
        "supported_providers": supported_providers,
        "supported_provider_count": len(supported_providers),
        "provider_lane_resolved": provider_lane_resolved,
        "provider_context_verified": provider_context_verified,
        "provider_context_source": provider_context_source,
        "provider_context_status": provider_context_status,
        "provider_verification_required": provider_verification_required,
        "provider_verification_reason": provider_verification_reason,
        "executable_name": executable_name,
        "defaulted_params": {key: value for key, value in effective_params.items() if key not in params},
        "command_ready": executable_available,
        "execution_mode": execution_mode,
        "execution_block_reason": execution_block_reason,
        "preflight_ready": preflight_ready,
        "confirmation_eligible": confirmation_eligible,
        "ready_to_execute": ready_to_execute,
        "context_required": context_required,
        "context_requirement_reason": context_requirement_reason,
        "context_available": bool(has_workspace_signal or has_host_import or connection_status == "connected"),
        "suppressed_command_reason": suppressed_command_reason,
        "provider_guidance": provider_guidance,
        "notes": notes,
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
            "stderr": f"Missing required parameters for this integration action: {', '.join(preview['missing_params'])}.",
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
    if action.action_id == "connect":
        family = FAMILY_BY_ID[family_id]
        updated_registry = normalize_integration_registry(registry, {})
        updated_registry["connections"][family_id] = _merge_connection_entry(
            dict(updated_registry["connections"].get(family_id) or {}),
            family=family,
            status="partial",
            providers=list(family.providers),
            connection_source="manual",
            host_imported=bool(dict(updated_registry["connections"].get(family_id) or {}).get("host_imported")),
            notes=["Manual connection intent recorded by Mission Control. Live provider verification is still pending."],
        )
        history = list(updated_registry.get("action_history") or [])
        history.append({"family": family_id, "action_id": action_id, "status": "completed", "command": None, "returncode": 0})
        updated_registry["action_history"] = history[-50:]
        return {
            **preview,
            "status": "completed",
            "stdout": "Recorded manual connection intent. Mission Control still requires live provider verification before treating this lane as connected.",
            "stderr": "",
            "returncode": 0,
            "approval_required": False,
            "updated_registry": updated_registry,
        }
    if action.action_id == "disconnect":
        updated_registry = normalize_integration_registry(registry, {})
        existing = dict(updated_registry["connections"].get(family_id) or {})
        updated_registry["connections"][family_id] = {
            "family": family_id,
            "status": "disconnected",
            "providers": _dedupe_strs([str(item) for item in list(existing.get("providers") or [])]),
            "connection_source": "mission_control",
            "host_imported": bool(existing.get("host_imported")),
            "approval_policy": str(existing.get("approval_policy") or "ask_every_time"),
            "notes": _dedupe_strs([str(item) for item in list(existing.get("notes") or [])] + ["Disconnected through Mission Control."]),
        }
        history = list(updated_registry.get("action_history") or [])
        history.append({"family": family_id, "action_id": action_id, "status": "completed", "command": None, "returncode": 0})
        updated_registry["action_history"] = history[-50:]
        return {
            **preview,
            "status": "completed",
            "stdout": "Disconnected the Mission Control-owned connection state for this family.",
            "stderr": "",
            "returncode": 0,
            "approval_required": False,
            "updated_registry": updated_registry,
        }
    if preview.get("provider_verification_required"):
        return {
            **preview,
            "status": "blocked",
            "stdout": "",
            "stderr": "Mission Control must verify the live provider identity for this guided remote mutation before it can approve or execute the action.",
            "returncode": None,
            "approval_required": False,
        }
    if preview.get("execution_block_reason") == "missing_executable":
        return {
            **preview,
            "status": "blocked",
            "stdout": "",
            "stderr": "The previewed executable is not available on PATH for this environment.",
            "returncode": None,
            "approval_required": False,
        }
    if not preview.get("command"):
        guidance = _provider_guidance(str(preview.get("provider") or ""), action.action_id)
        stderr = guidance or "No executable local command is defined for this action."
        if preview.get("suppressed_command_reason") == "provider_context_missing":
            stderr = "Mission Control needs real provider context for this provider-specific lane before it can preview or execute a concrete command."
        return {
            **preview,
            "status": "completed" if action.action_id == "connect" else "blocked",
            "stdout": "No executable local command is defined for this action." if action.action_id == "connect" else "",
            "stderr": "" if action.action_id == "connect" else stderr,
            "returncode": 0 if action.action_id == "connect" else None,
            "approval_required": False,
        }
    if preview["requires_confirmation"] and not confirmed:
        return {
            **preview,
            "status": "approval_required",
            "stdout": "",
            "stderr": "Explicit confirmation is required for this mutating integration action.",
            "returncode": None,
            "approval_required": True,
        }
    try:
        completed = subprocess.run(
            _command_to_args(str(preview["command"])),
            shell=False,
            cwd=workspace_path if workspace_path and Path(workspace_path).exists() else str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **preview,
            "status": "failed",
            "stdout": (exc.stdout or "").strip(),
            "stderr": f"Integration action timed out after {int(exc.timeout)} seconds.",
            "returncode": None,
            "approval_required": False,
        }
    except OSError as exc:
        return {
            **preview,
            "status": "failed",
            "stdout": "",
            "stderr": str(exc),
            "returncode": None,
            "approval_required": False,
        }
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
