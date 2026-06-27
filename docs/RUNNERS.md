# Runners

> Status: Current

Mission Control uses runners to execute background work. Runner availability depends on the local machine, installed tools, authentication state, and explicit configuration.

## Support Matrix

`working` means the runner path is implemented, selected by the runtime, and covered by tests when its prerequisites exist.

| Runner | Status | What proves it |
| --- | --- | --- |
| `codex_cli` | working | CLI runner, startup probes, runner selection tests |
| `claude_cli` | working | Claude CLI runner, handshake tests, runner selection tests |
| `ollama` | working | built-in adapter recipe, adapter tests, runner execution tests |
| `openai_api` | working | built-in API adapter recipe, adapter tests, runner selection tests |
| `dry_run` | working | deterministic dry-run lane used by the validated happy path |

## Detection model

- `dry_run` is always the safe fallback
- `codex_cli` is preferred when installed and signed in
- `ollama` uses the built-in `scripts/ollama_adapter.py` recipe and still requires a reachable local endpoint
- `claude_cli` depends on a working local CLI environment and local auth state
- API-backed runners use the built-in `scripts/api_provider_adapter.py` recipe, still require secure external API keys, and may incur billing
- `nvidia_dynamo` uses the built-in OpenAI-compatible adapter recipe and expects a reachable NVIDIA Dynamo frontend; API keys are optional unless the deployment enforces bearer auth
- `nvidia_nim` uses the built-in OpenAI-compatible adapter recipe and expects a reachable NVIDIA NIM endpoint; hosted or private deployments may require bearer auth
- Webwright is not a runner type; it is an optional browser-agent companion that Mission Control can detect and route browser tasks toward when the local runtime is ready

## NVIDIA Dynamo polish

- Mission Control now reports Dynamo runtime truth in two layers:
  - frontend reachability and model listing from the Dynamo endpoint
  - worker-runtime readiness from the local adapter command and any required API key
- if Dynamo is reachable but the adapter command is missing, Mission Control reports that as a runtime blocker instead of pretending the stack is ready
- if the deployment requires bearer auth, Mission Control reports the missing key directly instead of flattening it into generic degraded status

## NVIDIA validation surfaces

- `nvidia-gpu-diagnostics` covers remote-ish cluster truth: Prometheus, DCGM, pending GPU pods, and memory pressure
- `nvidia-local-runtime` covers local machine truth: `nvidia-smi`, `nvcc`, Compute Sanitizer, Nsight, CUDA-GDB, NGC CLI, and NVIDIA container runtime posture
- `nvidia-validation-plan` combines both with CUDA repo detection so Mission Control can generate a sane build/test/profile/sanitizer/container loop instead of making one up on the fly
- the smoke harness at `scripts/run_nvidia_stack_smoke.py` can run against:
  - a fake local NVIDIA stack with `--mock-stack`
  - or real endpoints when you provide explicit Dynamo, NIM, AI-Q, and Prometheus URLs

## Built-in adapter recipes

- Mission Control now ships first-class default adapter recipes for `ollama`, `openai_api`, `anthropic_api`, `xai_api`, `nvidia_dynamo`, and `nvidia_nim`
- those recipes use the current Python interpreter plus the repo-local adapter script
- users can still override the adapter command or args explicitly when they need a custom path
- `custom` providers stay opt-in and do not get a fake default recipe

## Test proof

- [Runner registry tests](../apps/server/tests/test_runners.py)
- [Headless bootstrap tests](../apps/server/tests/test_headless_bootstrap.py)
- [Ollama adapter tests](../apps/server/tests/test_ollama_adapter.py)
- [API provider adapter tests](../apps/server/tests/test_api_provider_adapter.py)

## Operational rules

- Mission Control should not silently switch a project onto a billed API path
- local-first options are preferred when they satisfy the task
- missing auth is surfaced as a clear blocker, not hidden as degraded success
- runner selection stays behind Mission Control policy, not ad hoc chat decisions

## Read next

- [Autowire Providers](AUTOWIRE_PROVIDERS.md)
- [Feature Status](FEATURE_STATUS.md)
- [Background Health](HEADLESS_HEALTH.md)
- [NVIDIA Stack Testing](NVIDIA_STACK_TESTING.md)
- [Webwright](WEBWRIGHT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
