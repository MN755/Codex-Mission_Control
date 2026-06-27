# Mission Control Token Spike Prevention And Hardening Plan

Status: draft research and design paper  
Date: 2026-06-24  
Workspace: `C:\Users\mike\OneDrive\Desktop\Codex Mission Control`  
Primary incident: project `11` / orchestration `14` token and thread explosion  
Companion artifact: [mission-control-token-spike-postmortem-project-11.md](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/docs/forensics/mission-control-token-spike-postmortem-project-11.md)

## Purpose

This document is the prevention paper for the Mission Control token-spike incident. The goal is not to restate that the failure was bad. That part is obvious. The goal is to show, in painful detail, how to keep it from happening again.

This paper is intentionally long because the failure was not one bug. It was a systems failure across economics, control flow, retry policy, model policy, state reconciliation, queue health, benchmark accounting, operator UX, and human supervision. If the fix list is short, it means the analysis was lazy.

This document is built from two evidence streams:

1. Local repo evidence and incident artifacts.
2. Current official guidance on retries, overload, circuit breaking, and rate-limit handling.

This paper is therefore both:

- a design document for Mission Control changes, and
- a runbook for how the operator and the bridge should behave when the system starts doing dumb expensive nonsense.

## Scope

This paper is about preventing a repeat of the following class of failures:

- runaway token burn
- excessive thread or session creation
- repeated retries on nonproductive work
- scheduler churn that creates more tasks than it resolves
- live benchmark loops that continue after quota or model-policy failures
- worker runs that count as “movement” without counting as progress
- weak visibility into real spend, token velocity, and context-window pressure

This paper is not primarily about:

- frontend polish
- standalone dashboard aesthetics
- generic AI safety theory
- product marketing

The relevant system surface is the headless-first Mission Control runtime:

`Codex chat -> Mission Control bridge -> daemon -> manager -> worker runners -> validation -> review -> handoff`

## Executive Summary

The incident happened because Mission Control had token observation, model normalization, retry logic, swarm agent counts, and some quota-backoff behavior, but it did not have a true cost governor.

That matters because observation without enforcement is accounting, not control.

The repo already contains multiple pieces of infrastructure that look like they should help:

- usage normalization in [usage_tracking.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/usage_tracking.py)
- Codex model clamping in [project_settings.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/project_settings.py)
- background-failure classification and retry scheduling in [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)
- provider backoff detection in [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- synthetic failure envelopes in [cli_runner.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/codex_runner/cli_runner.py)
- swarm budget records in [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)

But those pieces are not fused into a hard admission-control loop.

The practical result was:

- Mission Control could see usage after the fact.
- Mission Control could label some failures as transient.
- Mission Control could infer that quota backoff was needed.
- Mission Control could clamp worker model names in some settings flows.
- Mission Control could count active agents.

And still:

- it created huge numbers of fresh worker runs
- it retried high-cost lanes repeatedly
- it let invalid model selections burn real cycles
- it treated quota and usage-limit failures as local recoverable noise instead of benchmark-halting events
- it kept scheduling and superseding lanes even after throughput had clearly collapsed

The fix is not “use fewer agents.”

The fix is to add a full layered self-preservation architecture:

1. preflight policy gates  
2. benchmark-spend budgets  
3. retry budgets  
4. queue and task-family dedupe controls  
5. load shedding and graceful degradation  
6. circuit breakers  
7. high-signal telemetry  
8. operator kill switches  
9. post-run evidence quality gates  
10. test harnesses that intentionally simulate overload and quota events

## Incident-Derived Facts That Drive This Design

These are the specific facts from the incident that matter for prevention.

### Fact 1: Local Mission Control telemetry was already catastrophically high

The postmortem found:

- `715,075,711` locally recorded tokens
- `684,853,363` of those tied to project `11`
- `1,982` local agent runs overall
- `982` local agent runs in project `11`
- `4,288` `.events.jsonl` files in `.runtime/logs`

That means the system did not merely “look noisy.” It was objectively operating at absurd scale for one benchmark attempt.

### Fact 2: The Codex profile number was even worse than the local DB

The user profile screenshot showed:

- `1.5B` peak tokens
- `2,103` total threads

The gap between local DB totals and profile totals means at least one of these is true:

1. local persistence captured only part of the true billable work
2. some runs failed after billing but before full local reconciliation
3. thread/session churn outside the clean `agent_runs` path still consumed tokens

All three are bad.

### Fact 3: The scheduler spent too much time superseding itself

The incident task board snapshot showed `87` tasks in `superseded`.

That means the system spent real effort creating work that its own later logic invalidated or replaced.

This is not harmless metadata churn. Every superseded lane increases the chance of:

- a fresh run
- a fresh thread
- more review work
- more context-pack work
- more bookkeeping
- more opportunities for duplicate fixes

### Fact 4: The same lanes were retried absurd numbers of times

Examples from the incident:

- `Apps Mcp Server Tests Defect Batch`: `115` runs
- `Apps Desktop Tests Defect Batch`: `103` runs
- `Apps Dashboard Public Defect Batch`: `84` runs
- `Apps Desktop Src Defect Batch`: `81` runs

When a lane crosses even 4 to 6 real attempts without converging, the system should stop pretending that “just one more run” is a serious plan.

### Fact 5: Many runs had no changed files

The postmortem found:

- `64` `done` runs with zero changed files
- `326` total runs with zero changed files

This is fatal for benchmark discipline. It means the system had no sufficiently hard distinction between:

- a useful code-changing run
- a validation-only run
- a blocked run
- a no-op run that still consumed money

### Fact 6: Unsupported model selection still escaped into live execution

Stored runner-bug envelopes showed repeated invalid requests because the system tried to use `gpt-5.3-codex` in an environment where that model was not supported for the given account/runtime mode.

That means some model-policy validation happened too late, or at the wrong layer, or without strict enough fail-closed behavior.

### Fact 7: Usage-limit events did not stop the benchmark globally

The system captured multiple reports that explicitly said the provider usage limit had been hit.

The repo does contain provider-backoff recognition logic in [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py), but the incident proves that was not enough. The system still kept producing backlog churn and continued burn.

### Fact 8: SQLite lock contention was not just noise

The incident report captured `database is locked` failures in result reconciliation. This matters because:

- it can lose or delay spend/accounting updates
- it can strand or duplicate state transitions
- it can make a completed run look incomplete
- it can invite retries on work that already succeeded

In other words: storage contention can become spend amplification.

## Local Code Reality Check

This section matters because prevention should target the actual code, not the imaginary code we wish existed.

### 1. Usage tracking exists, but it is observational

[usage_tracking.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/usage_tracking.py) normalizes:

- `input_tokens`
- `output_tokens`
- `total_tokens`
- `cached_input_tokens`
- `reasoning_tokens`
- `context_tokens`
- `peak_context_tokens`
- `context_window_tokens`

This is good. It means the system already knows enough to reason about:

- spend
- context pressure
- cached-token mix
- context-window utilization

What it does not do is enforce hard stop conditions based on those values.

### 2. Swarm budget exists, but it is not a spend budget

[models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py) defines `SwarmBudget` with:

- `max_agents`
- `require_approval_above_agent_count`
- `prefer_local_models`
- `premium_models_only_for`
- `current_active_agents`
- `current_intensity`
- `dynamic_spawning_paused`

This is an agent-count budget, not an economic budget.

It can tell you how many workers are active. It cannot tell you:

- how many tokens remain for the benchmark
- whether one lane family is burning 10x its expected budget
- whether cached-input savings are hiding catastrophic absolute spend
- whether the benchmark is allowed to launch even one more worker

### 3. Model clamping exists, but is insufficiently defensive

[project_settings.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/project_settings.py) clamps Codex manager and worker models. That is better than nothing.

But the incident proves the model policy still leaked into runtime failure states. Therefore at least one of these is true:

- not all launch paths use the same clamping
- the clamp is permissive where it should be fail-closed
- account/runtime compatibility is not validated early enough
- a stale run configuration or override bypassed the clamp

### 4. Quota backoff exists, but it is reactive and too soft

[manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py) has logic that can detect provider backoff from recent run summaries and produce a degraded state.

That is useful for UI and observability.

It is not sufficient as a hard enforcement mechanism because:

- it depends on recognizing text after a run finished
- it uses a recent-run heuristic
- it activates only after several signals
- it is not obviously the top-level admission gate for all new work

### 5. Retry classification exists, but retry budgeting does not

[orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py) classifies background failures and retries some categories. `MAX_BACKGROUND_FAILURES` is currently `3`.

That looks responsible until you notice the problem domain:

- three retries per background turn is not the same as three retries per lane family
- one task can be superseded and re-created under a fresh ID
- one benchmark can generate many fresh lanes that are logically the same failure
- retry logic at different layers can multiply each other

So a local retry cap is not a true retry budget.

### 6. The runner converts provider-limit errors into blocked envelopes, but that still burns money

[cli_runner.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/codex_runner/cli_runner.py) classifies failure text and builds synthetic failure envelopes. It correctly treats:

- `usage limit`
- `rate limit`
- `quota`
- `too many requests`

as blocker-like failures.

That is good for reporting.

It does not solve the bigger issue: once those failures appear, Mission Control needs to stop launching fresh work globally unless an explicit recovery policy says otherwise.

### 7. Simulation already warns about churn, but the live system needs the same self-preservation

[simulation/service.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/simulation/service.py) includes a warning that launching more workers when blocked tasks exist may amplify churn instead of reducing it.

That warning was correct. The live benchmark proved it.

The mistake is that this wisdom lives partly in simulation and diagnostics, not as a hard live scheduling rule.

## Research Foundation

The hardening recommendations below are not based only on the incident. They are aligned with the external sources listed here.

### OpenAI

The OpenAI rate-limit documentation states that:

- rate limits exist at organization and project levels
- limits vary by model
- usage limits are also enforced
- rate-limit headers expose remaining request and token headroom
- unsuccessful requests still count against limits
- exponential backoff with jitter is recommended for retry handling

The OpenAI Help Center also notes that rate limits may be quantized over shorter windows, and that oversized contexts and bursts can trigger failures even if minute-level totals appear okay.

### AWS Builders Library

AWS’s guidance on timeouts, retries, and backoff with jitter is especially relevant here:

- retries can amplify overload
- timeouts must bound resource retention
- backoff should include jitter
- jitter should be applied to periodic work too, not just request retries
- retrying should stop when it is not improving availability

That maps directly to Mission Control’s scheduled monitor loops, background turns, queued resumes, and repeated lane launches.

### Google SRE

Google’s SRE guidance on cascading failures and load shedding maps almost one-to-one onto this incident:

- overload is the dominant cascading-failure cause
- fail early and cheaply rather than overloading the system
- rate limiting alone is not enough
- load shedding and graceful degradation must be explicit
- small queues are often better than large queues
- unhealthy-instance avoidance can worsen cascades if it concentrates traffic

Mission Control’s lane churn problem is basically an orchestration-flavored cascading-failure problem.

### Microsoft Azure Architecture

The Azure Retry and Circuit Breaker patterns reinforce several critical points:

- retry only when the failure is likely transient
- fail fast for nontransient or long-lived failures
- log retries without drowning operators in noise
- use circuit breakers to stop repeated calls to unhealthy dependencies
- consider idempotency before retrying

Mission Control violated the spirit of all of those during the incident.

## Prevention Principles

Before specific fixes, Mission Control needs a clear self-preservation philosophy.

### Principle 1: The system must optimize for accepted progress, not activity

The benchmark goal is not:

- number of tasks created
- number of runs executed
- number of threads opened
- number of summaries emitted

The benchmark goal is accepted distinct fixes with evidence.

Any metric that goes up while accepted-fix velocity goes down is suspicious.

### Principle 2: Every automated benchmark must have a burn ceiling

No benchmark should be allowed to consume open-ended:

- tokens
- run attempts
- worker sessions
- elapsed time

If those are uncapped, you have not built a benchmark. You have built a very polite denial-of-wallet machine.

### Principle 3: Retry is not recovery

Retry is useful only when:

- the failure is truly transient
- the dependency is likely healthy soon
- the system is below overload thresholds
- the work is idempotent or carefully deduped

Otherwise retry is just duplication with better branding.

### Principle 4: Quota and usage-limit events are system-level signals

If one live benchmark run hits a provider usage limit, Mission Control should assume the benchmark as a whole is economically degraded until proven otherwise.

That means:

- freeze new expensive work
- mark the benchmark degraded
- notify the operator
- wait for explicit re-arm or a controlled cooldown

### Principle 5: Thread creation must be treated as a budgeted resource

A fresh thread or session is not free. It creates:

- new context loading
- new token burn
- new coordination work
- new observability rows
- new failure surfaces

Mission Control should track and cap thread/session creation with the same seriousness it applies to worker count.

### Principle 6: No-change runs should almost never be benchmark-success runs

A run with zero changed files may still be useful as:

- validation
- diagnosis
- triage
- review

But it should not be allowed to silently masquerade as productive fix throughput.

## The Hardening Model

The prevention design should be layered. One mechanism will fail. Multiple layers are how you survive the dumb days.

### Layer A: Preflight gates

Before live benchmark work starts:

- verify account and runner compatibility
- verify allowed model set
- verify benchmark policy
- verify budget configuration exists
- verify the persistence layer is healthy enough
- verify at least one kill path exists

### Layer B: Admission control

Before any new worker run is launched:

- check token budget remaining
- check run budget remaining
- check thread budget remaining
- check task-family retry budget
- check current queue health
- check current review debt
- check provider backoff state
- check DB contention state

### Layer C: Runtime protection

While work is active:

- update spend counters continuously
- update context-window pressure continuously
- trip circuit breakers on known catastrophic classes
- shed lower-priority work when overloaded
- suppress new noncore lanes when convergence is poor

### Layer D: Post-run validation

After each run:

- enforce changed-file evidence requirements
- enforce dedupe rules
- enforce benchmark-accounting rules
- suppress fake “done” transitions

### Layer E: Operator recovery controls

When things go wrong:

- show why the system paused
- show what budget was exceeded
- show which tasks were frozen
- require explicit re-arm when appropriate

## Direct Fixes By Failure Class

This is the core of the paper. Each item below maps a failure pattern to a concrete engineering fix.

### Failure Class 1: No hard token ceiling

#### What happened

Mission Control tracked tokens after the fact but did not have a benchmark-wide hard stop that said:

“No more expensive work may launch after this threshold.”

#### Why this caused damage

Without a spend ceiling:

- retries remain “cheap enough” in logic even when they are expensive in reality
- superseded tasks can spawn fresh cost
- operator inattention becomes financially dangerous

#### Direct fix

Add a first-class `BenchmarkSpendBudget`.

Proposed schema:

- `project_id`
- `benchmark_id`
- `hard_total_tokens_limit`
- `soft_total_tokens_limit`
- `hard_prompt_tokens_limit`
- `hard_output_tokens_limit`
- `hard_context_peak_limit`
- `hard_threads_created_limit`
- `hard_run_attempts_limit`
- `current_total_tokens`
- `current_prompt_tokens`
- `current_output_tokens`
- `current_peak_context_tokens`
- `current_threads_created`
- `current_run_attempts`
- `state` = `open|soft_exceeded|hard_exceeded|paused|rearmed`
- `tripped_reason`
- `tripped_at`

#### Enforcement rule

No worker launch if any hard limit is exceeded.

#### File targets

- [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)
- [schemas.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/schemas.py)
- [db.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/db.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)

### Failure Class 2: Agent-count budget existed, spend budget did not

#### What happened

`SwarmBudget` can speak about active agents and swarm intensity, but not about spend.

#### Why this caused damage

Eight cheap workers and eight catastrophically expensive workers are very different. The current model mostly treats them as the same shape.

#### Direct fix

Extend swarm budgeting to include:

- estimated cost class per worker
- token burn rate per worker
- benchmark-wide marginal cost of launching another worker
- queue-value score of each prospective worker

Define a launch formula:

`launch_allowed = work_value_score > cost_risk_score and all hard budgets open`

#### File targets

- [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)
- [schemas.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/schemas.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)

### Failure Class 3: Unsupported model selection escaped into live runs

#### What happened

The incident showed invalid-model runner failures involving `gpt-5.3-codex`.

#### Why this caused damage

This is the worst category of avoidable burn:

- the run was doomed before it started
- the failure taught nothing useful
- it still consumed coordination and persistence work

#### Direct fix

Create a strict `ResolvedRuntimePolicy` gate checked before every live launch.

It must validate:

- provider name
- account/runtime mode
- manager model allowlist
- worker model allowlist
- model support under the currently authenticated environment
- cloud/local/fast-mode prohibition flags
- per-role overrides

The key behavior:

- fail closed
- do not substitute silently
- block launch before spawning a worker thread
- require explicit operator approval to proceed with fallback model substitution

#### File targets

- [project_settings.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/project_settings.py)
- [system_status.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/system_status.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [codex_runner/cli_runner.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/codex_runner/cli_runner.py)

### Failure Class 4: Usage-limit events did not freeze the benchmark globally

#### What happened

The system recognized provider-backoff signals but did not stop the benchmark decisively enough.

#### Why this caused damage

Usage-limit failures are not ordinary transient errors during a spend-sensitive benchmark. They are a budget alarm.

#### Direct fix

Add a benchmark-wide `ProviderBackoffCircuit`.

States:

- `closed`
- `open_quota`
- `half_open_probe`
- `manual_hold`

Rules:

- One usage-limit error from a live benchmark opens a lane-local breaker.
- Two usage-limit signals from separate recent runs open the benchmark-wide breaker.
- While open, no new expensive worker launches may occur.
- Only a small number of half-open probe runs may test recovery.
- Re-arming requires either cooldown expiry or explicit user action depending on policy.

#### File targets

- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)
- [bridge_messages.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/bridge_messages.py)

### Failure Class 5: Retry logic existed without retry budgets

#### What happened

The system had local retry logic and background retry classification, but logical work could be reissued through new task IDs, unblock lanes, or supersession flows.

#### Why this caused damage

This is how you accidentally get “three retries” at one layer but a hundred real attempts at the system level.

#### Direct fix

Create a `RetryBudget` concept at three levels:

- per-run
- per-task-family
- per-benchmark

Every lane must carry:

- `task_family_key`
- `root_cause_group`
- `attempt_index`
- `cumulative_attempt_count_for_family`
- `cumulative_tokens_for_family`

Budget rules:

- stop after `N` family attempts
- stop after family token burn exceeds threshold
- require a different remediation strategy after threshold breach
- require operator or manager justification to exceed family budget

#### File targets

- [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)
- [playbooks/service.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/playbooks/service.py)

### Failure Class 6: Scheduler supersession churn

#### What happened

The task board accumulated many `superseded` tasks and multiple `Unblock:` variants for the same basic work.

#### Why this caused damage

Scheduler churn creates:

- false throughput
- fresh context costs
- re-triage costs
- duplicate review paths

#### Direct fix

Introduce a canonical task-family registry.

Each task must have:

- `family_key`
- `supersedes_family_key`
- `root_issue_key`
- `dedupe_hash`

Rules:

- only one active open task per family unless parallel shards are explicitly declared
- unblock tasks must not create a new family
- evidence-only follow-ups must attach to the same family
- superseding should mutate family state, not mint uncontrolled fresh work

#### File targets

- [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [task_board.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/task_board.py)

### Failure Class 7: Zero-change runs were not treated as dangerous enough

#### What happened

Many runs completed with zero changed files.

#### Why this caused damage

Zero-change runs can be legitimate, but when they are common they mean:

- poor task scoping
- duplicate validation
- over-eager spawning
- weak benchmark accounting

#### Direct fix

Add a `MeaningfulOutputGate`.

A run may not count as benchmark progress unless it satisfies at least one:

1. changed files with valid diff evidence
2. explicit test or validation artifact attached to an existing accepted family
3. approved reclassification to duplicate/blocked/noncountable

And separately:

- repeated zero-change runs on the same family should freeze the family
- a high benchmark-wide zero-change ratio should reduce concurrency automatically

#### File targets

- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [bridge_messages.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/bridge_messages.py)
- [schemas.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/schemas.py)

### Failure Class 8: Queue health was not a first-class launch gate

#### What happened

The system continued launching or maintaining many lanes even while blocked, review-gated, and superseded work was piling up.

#### Why this caused damage

High queue pressure means the control plane is falling behind. More workers may make it worse.

#### Direct fix

Create a `QueueHealthScore`.

Inputs:

- open backlog count
- blocked-task count
- waiting-on-paths count
- review-debt count
- superseded-task count
- zero-change ratio
- unresolved-run count
- DB lock error rate

If the score crosses thresholds:

- stop spawning new noncore lanes
- prefer finishing existing review/validation
- switch to degraded mode
- surface a warning in the bridge and dashboard

#### File targets

- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)
- [simulation/service.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/simulation/service.py)

### Failure Class 9: SQLite lock contention amplified confusion and retries

#### What happened

The incident captured `database is locked` during state reconciliation.

#### Why this caused damage

If usage and result state are delayed or lost:

- completed work can look unfinished
- retries can be scheduled for already-completed work
- spend counters can lag reality

#### Direct fix

Reduce lock-risk impact in three ways:

1. split hot tables and writes where possible
2. write spend/accounting snapshots append-only before reconciliation
3. add reconciliation idempotency keys

Also:

- treat DB-lock frequency as a queue-health signal
- if DB lock frequency rises, reduce concurrency automatically
- preserve worker result envelopes to a durable append-only log before transactional merge

#### File targets

- [db.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/db.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)

### Failure Class 10: Thread/session creation was not explicitly budgeted

#### What happened

The profile thread count strongly suggests worker-run churn was driving large-scale thread creation.

#### Why this caused damage

Fresh thread creation:

- reloads context
- increases coordination state
- widens local-vs-billed accounting drift

#### Direct fix

Track:

- `threads_created_total`
- `threads_created_by_family`
- `threads_created_per_hour`
- `reused_threads_total`

Add policies:

- prefer thread reuse for retries of the same family when safe
- cap fresh-thread creation per benchmark window
- freeze new-thread creation if accepted-fix velocity falls below threshold

#### File targets

- runner launch and session mapping code in [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- runner persistence in [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)

### Failure Class 11: Benchmarks mixed high-value defect work with proof, docs, and ledger churn

#### What happened

The incident included many lanes that were about:

- proof
- ledger updates
- naming artifacts
- evidence reclassification

#### Why this caused damage

Documentation and evidence work is necessary, but during a degraded high-burn benchmark it should not compete equally with core fix lanes.

#### Direct fix

Introduce benchmark lane classes:

- `core_fix`
- `validation`
- `review`
- `ledger`
- `docs`
- `meta_recovery`

Scheduling rules:

- `core_fix` lanes dominate until degraded conditions appear
- `ledger` and `docs` lanes are rate-limited during high burn
- meta lanes may not exceed a small fraction of concurrent capacity

#### File targets

- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [prompts.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/prompts.py)
- [schemas.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/schemas.py)

### Failure Class 12: Operator control was too weak

#### What happened

The operator had to infer too much from symptoms and monitoring rather than from hard-stop messages tied to specific policy breaches.

#### Why this caused damage

If the operator must “notice the vibe is bad,” shutdown happens too late.

#### Direct fix

Add operator-visible guardrail states:

- `paused_by_hard_budget`
- `paused_by_quota`
- `paused_by_retry_budget`
- `paused_by_scheduler_churn`
- `paused_by_result_integrity_failure`
- `paused_by_persistence_contention`

Every pause must show:

- exact trigger
- exact threshold
- current measured value
- whether auto-recovery is allowed
- what explicit action re-arms the system

#### File targets

- [bridge_messages.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/bridge_messages.py)
- [bridge_formatter.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/bridge_formatter.py)
- [ascii_monitor.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/ascii_monitor.py)

## Proposed Target Architecture

### 1. Budget Controller

Add a dedicated `BudgetController` service.

Responsibilities:

- ingest usage snapshots
- maintain per-project and per-benchmark rollups
- expose admission checks
- emit trip events
- publish budget state to bridge and monitor surfaces

This should not live as scattered conditional logic in runner, manager, and bridge code. Those layers should call one policy surface.

### 2. Admission Controller

Add a dedicated `AdmissionController`.

Responsibilities:

- decide whether a worker may launch
- evaluate budget state, retry state, queue state, provider state, and model-policy state
- return a structured launch decision:

`allow | deny | degrade | queue | manual_review`

### 3. Family Registry

Add a family-level dedupe and retry registry.

Responsibilities:

- map fresh tasks to root work families
- limit duplicate family launches
- maintain cumulative family burn metrics
- associate related evidence and review tasks

### 4. Persistence Safety Layer

Add append-only result and usage journals that write before relational reconciliation.

Responsibilities:

- prevent loss of critical spend facts
- allow replay if reconciliation fails
- reduce false uncertainty after DB lock errors

### 5. Benchmark Governor

Add benchmark policy objects with:

- budget limits
- allowed runner modes
- allowed models
- allowed concurrency
- meta-lane caps
- re-arm rules

Mission Control should not infer benchmark behavior only from plain task state.

## Concrete Schema Additions

This section describes a practical schema proposal.

### New table: `benchmark_budgets`

Suggested fields:

- `id`
- `project_id`
- `name`
- `state`
- `hard_total_tokens_limit`
- `soft_total_tokens_limit`
- `hard_run_attempt_limit`
- `hard_thread_creation_limit`
- `hard_zero_change_run_limit`
- `hard_superseded_task_limit`
- `hard_needs_review_limit`
- `hard_waiting_on_paths_limit`
- `cooldown_seconds_after_quota`
- `manual_rearm_required_after_quota`
- `created_at`
- `updated_at`

### New table: `benchmark_budget_rollups`

Suggested fields:

- `benchmark_budget_id`
- `current_total_tokens`
- `current_input_tokens`
- `current_output_tokens`
- `current_cached_input_tokens`
- `current_peak_context_tokens`
- `current_run_attempts`
- `current_thread_creations`
- `current_zero_change_runs`
- `current_superseded_tasks`
- `current_review_backlog`
- `current_waiting_on_paths`
- `last_trip_reason`
- `last_trip_at`

### New table: `task_families`

Suggested fields:

- `id`
- `project_id`
- `family_key`
- `root_issue_key`
- `category`
- `state`
- `current_open_task_id`
- `attempt_count`
- `total_tokens`
- `zero_change_attempts`
- `thread_creations`
- `accepted_fix_count`
- `rejected_fix_count`
- `last_failure_classification`
- `last_failure_at`

### New table: `result_journal`

Suggested fields:

- `id`
- `agent_run_id`
- `journal_kind` = `usage|result|event`
- `payload_json`
- `created_at`
- `reconciled_at`

### New table: `provider_backoff_circuits`

Suggested fields:

- `project_id`
- `provider`
- `state`
- `opened_at`
- `until`
- `trigger_count`
- `last_trigger_summary`

## State-Machine Changes

Mission Control needs explicit state semantics, not just more statuses sprayed onto tasks.

### Benchmark states

Add benchmark-level states:

- `ready`
- `running`
- `degraded`
- `cooling_down`
- `paused_budget`
- `paused_quota`
- `paused_integrity`
- `paused_operator`
- `completed`
- `aborted`

### Task-family states

Add family-level states:

- `open`
- `running`
- `blocked_transient`
- `blocked_nontransient`
- `cooling_down`
- `awaiting_review`
- `accepted`
- `rejected`
- `duplicate`
- `abandoned`

### Worker-launch decisions

Add structured launch outcomes:

- `launch_now`
- `launch_after_backoff`
- `reuse_existing_session`
- `deny_model_policy`
- `deny_budget`
- `deny_queue_health`
- `deny_retry_budget`
- `deny_quota_circuit`
- `manual_review_required`

## Queue Management And Load Shedding

The incident was a queue-health failure as much as a model-cost failure.

### Why load shedding matters here

Per Google SRE, overloaded systems must fail early and cheaply. Mission Control should do the same.

When queue health degrades, Mission Control should shed or defer:

- docs lanes
- ledger lanes
- proof lanes
- low-priority validation fanout
- opportunistic re-checks

It should preserve:

- one path to close active review debt
- one path to close active core-fix lanes
- one small path for quota recovery probes if permitted

### Proposed queue thresholds

Suggested initial thresholds:

- if `needs_review > 10`, stop spawning more review-producing lanes
- if `waiting_on_paths > 5`, stop spawning overlapping path families
- if `superseded > 20`, freeze new family creation
- if `zero_change_ratio > 0.25`, cut concurrency by half
- if `database_lock_failures_last_10m > 3`, stop all noncritical lane launches

These numbers are placeholders. The final values should come from testing and replay.

## Retry Strategy

Retries are not banned. They need to be disciplined.

### Allowed retry policy

Retry only when:

- failure is classified transient
- queue health is acceptable
- circuit is closed or half-open
- family retry budget remains
- benchmark hard budget remains
- the dependency is believed to be recovering

### Disallowed retry policy

Do not retry automatically when:

- invalid model selection
- schema or envelope integrity failure
- repeated zero-change outcomes on same family
- quota breaker is open
- family attempt budget exhausted

### Backoff policy

Use exponential backoff with jitter for transient failures, consistent with OpenAI guidance and AWS guidance.

Also jitter:

- background turns
- periodic monitor wakeups
- scheduled requeues
- cooldown probes

That prevents synchronized retry storms.

### Important subtlety

AWS warns that retries can amplify overload and should stop when they are not improving availability. That is directly relevant here. Mission Control should record retry effectiveness:

- attempts since last accepted fix
- attempts since last changed-file result
- attempts since last successful validation improvement

If that goes flat, the retry system should tighten, not loosen.

## Model Policy Hardening

This is where the repo can close one of the dumbest failure modes from the incident.

### Required policy behavior

Before live launch, Mission Control must know:

- selected provider
- selected runner mode
- selected manager model
- selected worker model
- whether those models are valid in the current environment
- whether the benchmark policy forbids cloud or fast mode
- whether any override creates an illegal combination

### Fail-closed rule

If compatibility is unknown, deny launch.

Not:

- warn and continue
- guess and continue
- fall back silently

The only acceptable fallback is explicit and recorded.

### Compatibility matrix

Mission Control should maintain a resolved policy matrix per project:

- `manager_allowed_models`
- `worker_allowed_models`
- `selected_manager_model`
- `selected_worker_model`
- `runtime_supports_selected_models`
- `launch_blockers`

This should be visible in status, not buried in logs.

## Spend And Context Telemetry

The repo already tracks context-related fields. Good. Now make them operational.

### Required live metrics

Per run:

- input tokens
- output tokens
- cached input tokens
- context tokens
- peak context tokens
- context window tokens
- context utilization

Per task family:

- total tokens
- average tokens per attempt
- max context utilization
- zero-change attempts
- accepted-fix yield

Per benchmark:

- burn rate per minute
- tokens per accepted fix
- tokens per changed-file run
- tokens per zero-change run
- fresh threads per hour
- retries per accepted fix

### Required alerts

Alert when:

- total tokens exceed soft budget
- burn rate exceeds configured ceiling
- context utilization exceeds threshold repeatedly
- zero-change ratio rises
- fresh-thread creation spikes
- quota breaker opens
- DB lock error rate rises

## Benchmark Accounting Hardening

The incident showed that “done” was too generous for benchmark credibility.

### Count only accepted distinct fixes

A counted fix must require:

- family-level distinctness
- changed-file evidence
- validation evidence
- duplicate analysis
- review acceptance

### Do not count

Do not count:

- docs-only bookkeeping
- ledger-only updates
- reclassification runs
- zero-change runs
- validation-only reruns unless they close a previously accepted family

### Family acceptance record

Every counted fix needs an acceptance record with:

- family key
- root cause
- why distinct
- changed files
- validation commands
- validation result
- docs updated if relevant
- reviewer identity
- acceptance timestamp

## Operator UX And Emergency Controls

### One-click kill switch

There must be a single control that:

- pauses benchmark scheduling
- pauses worker launches
- pauses requeues
- pauses monitor-induced recovery automation
- leaves unrelated projects alone

This should be project-scoped and benchmark-scoped, not a global daemon nuke by default.

### Budget dashboard must be boringly obvious

The operator needs to see:

- total tokens spent
- burn rate
- remaining hard budget
- quota/backoff status
- current thread creation count
- top burning task families
- top retrying families
- zero-change ratio
- queue health

If these are hidden, the operator is flying blind.

### Manual re-arm workflow

After catastrophic events such as quota exhaustion or invalid-model storms:

- do not auto-resume full swarm activity
- require manual re-arm
- require a visible reason string
- record who re-armed and why

## Testing Strategy

The system will not stay safe unless the ugly paths are tested on purpose.

### Unit tests

Add targeted tests for:

- token budget trip behavior
- model-policy denial behavior
- family retry budgeting
- zero-change run gating
- queue-health launch suppression
- quota breaker open/half-open transitions

### Integration tests

Add scenario tests for:

- repeated transient failures with successful recovery
- repeated quota failures
- invalid worker model configuration
- DB lock during result reconciliation
- superseded lane churn suppression
- thread-budget exhaustion

### Chaos and replay tests

Add replay or simulation harnesses that reproduce:

- the incident’s family retry counts
- usage-limit messages
- unsupported-model messages
- missing-envelope failures
- DB-lock collisions

Success criterion:

The new system stops itself cheaply before burn becomes absurd.

### Load tests

Following Google SRE guidance, test overload and failure modes directly:

- launch many low-value tasks
- inject backoff events
- inject queue saturation
- inject slow reconciliation
- verify load shedding and graceful degradation

## Rollout Plan

Do not ship all of this in one giant chaos blob.

### Phase 1: Safety patches

Implement first:

1. hard token budget
2. hard run-attempt budget
3. model-policy fail-closed preflight
4. benchmark-wide quota breaker
5. visible operator pause reasons

These are the fastest risk reducers.

### Phase 2: Scheduling discipline

Implement next:

1. task-family registry
2. retry budgets
3. queue-health score
4. zero-change gating
5. meta-lane caps

### Phase 3: Persistence hardening

Implement next:

1. append-only result/usage journals
2. reconciliation idempotency
3. DB-lock adaptive concurrency reduction

### Phase 4: Observability and policy polish

Implement:

1. spend dashboard surfaces
2. thread-creation tracking
3. half-open probe workflows
4. re-arm audit trail

## Recommended Priorities

If engineering time is scarce, do these in this order:

1. hard token/run/thread budget enforcement
2. model-policy fail-closed launch validation
3. benchmark-wide quota breaker
4. family-level retry budgets
5. queue-health launch suppression
6. zero-change gating
7. persistence hardening
8. operator UX improvements

## File-Level Change Map

This section is the direct implementation map.

### `apps/server/src/usage_tracking.py`

Add:

- benchmark rollup helpers
- context-pressure thresholds
- spend summary helpers for bridge/UI use

Do not add:

- policy decisions directly here

This file should remain measurement-first.

### `apps/server/src/project_settings.py`

Add:

- stricter fail-closed model validation
- benchmark policy fields for allowed manager/worker models
- explicit runner-mode prohibitions for benchmark execution

### `apps/server/src/system_status.py`

Add:

- resolved runtime compatibility status
- explicit launch blockers
- account/runtime/model support surface

### `apps/server/src/models.py`

Add:

- benchmark budget tables
- family registry tables
- backoff circuit tables
- result journal tables

### `apps/server/src/schemas.py`

Add:

- budget read/write schemas
- family state schemas
- launch decision schemas
- operator pause reason schemas

### `apps/server/src/manager.py`

This is the biggest change surface.

Add:

- budget controller integration
- admission controller integration
- family-key assignment
- queue-health scoring
- meta-lane caps
- zero-change suppression
- half-open recovery probes

Remove or weaken:

- any launch paths that can bypass policy checks

### `apps/server/src/orchestration.py`

Add:

- benchmark pause reasons
- global breaker awareness
- replay-safe retry accounting
- benchmark state transitions

### `apps/server/src/codex_runner/cli_runner.py`

Add:

- stronger structured failure classification
- durable session/thread identity reporting
- explicit provider-limit event flags

Keep:

- failure-envelope generation

### `apps/server/src/task_board.py`

Add:

- family-aware dedupe rules
- prevention of redundant unblock-family creation

### `apps/server/src/simulation/service.py`

Add:

- budget-controller and queue-health simulation outputs
- overload scenario simulations

### `apps/server/src/bridge_messages.py`

Add:

- budget trip cards
- re-arm prompts
- benchmark degraded-state explanations

## Example Policy Rules

These are example rules that can be implemented almost literally.

### Rule 1: No launch after hard budget

If `benchmark_budget.current_total_tokens >= hard_total_tokens_limit`, deny all new worker launches.

### Rule 2: No launch after repeated zero-change family attempts

If `task_family.zero_change_attempts >= 3` and no accepted diff exists, freeze family and require re-plan.

### Rule 3: No launch after model-policy uncertainty

If runtime compatibility is `unknown`, deny launch and surface exact blocker.

### Rule 4: No launch after quota breaker

If benchmark quota circuit is open, only allow explicit half-open probe runs.

### Rule 5: Concurrency reduction under queue stress

If queue-health score is `degraded`, cut launch concurrency by half.

If `critical`, allow only closure-oriented lanes.

### Rule 6: No new meta lanes during degraded burn

When burn rate exceeds threshold, block new docs/ledger/proof families.

## Pseudocode Sketch

```text
launch_worker(task):
  family = family_registry.resolve(task)
  usage = budget_controller.current(task.project_id)
  queue = queue_health.compute(task.project_id)
  runtime = runtime_policy.resolve(task.project_id, task.role)
  breaker = breaker_state.for_project(task.project_id)

  if runtime.blocked:
    return deny("model_policy", runtime.blockers)

  if breaker.open:
    if not breaker.allows_probe(task):
      return deny("quota_breaker", breaker.reason)

  if usage.hard_exceeded:
    return deny("hard_budget", usage.reason)

  if family.retry_budget_exhausted:
    return deny("family_retry_budget", family.summary)

  if queue.critical:
    if task.category not in {"core_fix", "review_closure"}:
      return deny("queue_health", queue.summary)

  if task.category in {"docs", "ledger", "proof"} and usage.soft_exceeded:
    return deny("meta_lane_suppressed", usage.summary)

  return allow()
```

## Implementation Risks

This plan is necessary, but it has risks.

### Risk 1: Over-hardening causes false pauses

If thresholds are too strict, Mission Control may stall too often.

Mitigation:

- start with visible soft-limit alerts before automatic hard stops on some metrics
- tune using replay data

### Risk 2: Excessive policy complexity

A giant fragile policy engine can become its own outage source.

Mitigation:

- centralize policy
- keep rules composable
- feature-flag advanced heuristics

### Risk 3: Hidden bypass paths

If even one runner path bypasses admission control, the system will lie to itself again.

Mitigation:

- one launch gateway
- tests that assert all launch surfaces route through it

### Risk 4: Bad operator defaults

A kill switch that is hard to understand or scoped poorly can do damage.

Mitigation:

- clear project scope
- clear reason strings
- safe defaults

## Non-Negotiable Requirements

These should be treated as mandatory before another aggressive benchmark run:

1. Benchmark-wide hard token budget
2. Benchmark-wide hard run-attempt budget
3. Fail-closed model compatibility gate
4. Benchmark-wide quota circuit breaker
5. Family-level retry budgets
6. Queue-health launch suppression
7. Zero-change run gating
8. Operator-visible pause reasons

If those are not in place, another high-scale live benchmark is negligence in nicer clothes.

## Recommended Work Packages

### Package A: Economic self-preservation

- benchmark budget tables
- budget controller
- hard stop rules
- bridge and monitor surfaces

### Package B: Launch discipline

- admission controller
- model-policy fail-closed launch gate
- thread/session budget tracking

### Package C: Scheduler convergence

- family registry
- retry budgets
- supersession suppression
- meta-lane caps

### Package D: Reliability under stress

- append-only journals
- DB-lock adaptive throttling
- half-open probe logic

### Package E: Operator confidence

- visible pause reasons
- spend dashboard
- re-arm audit trail

## Research Notes And Source Translation

This section translates the external sources into Mission Control-specific guidance.

### OpenAI rate-limit guidance translated

OpenAI says:

- limits are per org and project
- remaining tokens and requests are available in headers
- unsuccessful requests still count
- exponential backoff with jitter is recommended

Mission Control translation:

- use real remaining-headroom data when available
- treat failed attempts as budget consumption, not free retries
- distinguish request-rate pressure from token-rate pressure
- keep `max_completion_tokens` tightly bounded for benchmark workers

### AWS backoff guidance translated

AWS says:

- timeouts prevent resource retention
- retries amplify overload if misused
- jitter should be added to retries and periodic work

Mission Control translation:

- background turn timeouts must be explicit
- monitor and retry loops need jitter
- if retry effectiveness is poor, stop retrying

### Google SRE overload guidance translated

Google says:

- overload causes cascades
- fail early and cheaply
- rate limiting alone is insufficient
- use load shedding and graceful degradation

Mission Control translation:

- when queue health is degraded, stop launching low-priority lanes
- reject or defer work rather than letting the control plane drown
- use family-level and benchmark-level choke points

### Azure retry/circuit-breaker guidance translated

Azure says:

- retry only transient faults
- consider idempotency
- use circuit breakers for longer-lived faults

Mission Control translation:

- invalid model config is not retryable
- usage-limit storms are breaker events
- result reconciliation and review routing must be idempotent

## Suggested Testing Matrix

| Scenario | Expected result |
| --- | --- |
| Worker model unsupported for current runtime | Launch denied before worker spawn |
| Provider returns usage-limit error twice | Benchmark quota circuit opens |
| Zero-change family attempts reach threshold | Family frozen, no auto-retry |
| DB lock errors rise above threshold | New launches throttled or paused |
| Review backlog grows while accepted fixes stall | Concurrency reduces, meta lanes suppressed |
| Hard token limit exceeded | New worker launches denied immediately |
| Half-open probe succeeds | Breaker closes and limited activity resumes |
| Half-open probe fails | Breaker reopens and cooldown extends |

## Final Recommendation

Do not restart high-scale benchmark attempts until the following are implemented and tested:

- hard spend budgets
- hard run budgets
- fail-closed model-policy gating
- quota circuit breaking
- family-level dedupe and retry budgets
- zero-change gating
- queue-health suppression

If only one sentence from this document survives, it should be this:

Mission Control must become self-preserving before it is allowed to become ambitious again.

## Detailed Control Specifications

This section expands the major controls into implementation-grade specs. The point is to leave less room for future ambiguity, loopholes, or “we thought someone else meant to wire that up.”

### Control Spec 1: Hard Total-Token Budget

#### Intent

Stop the benchmark before it spends an irrational amount of tokens.

#### Inputs

- cumulative total tokens
- soft limit
- hard limit
- recent burn rate
- benchmark mode

#### Rule

- crossing soft limit sets benchmark state to `degraded`
- crossing hard limit sets benchmark state to `paused_budget`
- new launches are denied after hard limit
- existing runs may finish, but no new work is scheduled

#### Notes

- hard-limit behavior must not depend on dashboard rendering
- hard-limit behavior must survive daemon restart
- hard-limit behavior must survive DB replay

#### Edge cases

- if a single run would obviously exceed the remaining budget based on historical lane cost, deny launch before it starts
- if total tokens are temporarily unknown, use estimated tokens and deny when confidence is low and remaining budget is tight

#### Minimum tests

- soft-limit state transition
- hard-limit state transition
- daemon restart while already tripped
- denial of fresh launches after trip
- no accidental re-arm on worker completion

### Control Spec 2: Hard Thread-Creation Budget

#### Intent

Stop hidden session churn from becoming token churn.

#### Inputs

- threads created in current benchmark
- threads created in current hour
- thread reuse ratio
- accepted-fix velocity

#### Rule

- if fresh-thread creation exceeds configured limit, deny new thread creation
- if retrying a family and reusable session exists, require reuse unless explicitly blocked
- if accepted-fix velocity is poor and thread creation is high, transition to degraded mode

#### Notes

- not every thread is a bug, but every unnecessary thread is a cost multiplier
- thread reuse rules must not compromise isolation guarantees for unrelated families

#### Minimum tests

- retry launches reuse same family session when allowed
- fresh-thread cap blocks new lane fanout
- system still allows closure of already-running tasks

### Control Spec 3: Family Retry Budget

#### Intent

Prevent one logical piece of work from being attempted dozens of times under fresh wrappers.

#### Inputs

- family key
- cumulative family attempts
- cumulative family tokens
- last changed-file timestamp
- last accepted-fix timestamp

#### Rule

- if family attempts exceed cap, freeze family
- if family token spend exceeds cap, freeze family
- if repeated attempts produce no changed files, freeze family faster

#### Notes

- family freeze should surface a recommended next action:
  - re-scope
  - merge with duplicate family
  - request operator review
  - convert to blocked nontransient

#### Minimum tests

- repeated task supersession still maps to same family budget
- unblock tasks do not reset family counters
- duplicate families share burn accounting if deduped

### Control Spec 4: Model-Policy Launch Gate

#### Intent

Make invalid model/runtime combinations impossible to launch.

#### Inputs

- provider
- account/runtime capability
- benchmark policy
- selected manager model
- selected worker model
- runner mode

#### Rule

- if any selected model is unsupported, launch denied
- if benchmark policy forbids cloud or fast mode and settings request them, launch denied
- if compatibility is unknown, launch denied until explicitly resolved

#### Notes

- launch denial must be loud and structured
- no silent substitution

#### Minimum tests

- unsupported worker model
- unsupported manager model
- forbidden fast mode
- forbidden cloud execution
- stale override conflicting with provider normalization

### Control Spec 5: Provider Quota Circuit Breaker

#### Intent

Stop quota or usage-limit events from creating retry storms.

#### Inputs

- recent run summaries
- explicit provider error flags
- breaker state
- cooldown timer

#### Rule

- one quota event opens a family-local breaker
- repeated quota events open benchmark-wide breaker
- benchmark-wide breaker blocks expensive launches
- half-open probes are few, delayed, and explicit

#### Minimum tests

- one quota event does not accidentally lock entire daemon forever
- repeated quota events open benchmark breaker
- cooldown expiry alone does not resume meta lanes if queue health is still bad

### Control Spec 6: Queue-Health Governor

#### Intent

Keep Mission Control from solving overload by adding more overload.

#### Inputs

- backlog count
- blocked count
- waiting-on-paths count
- superseded count
- review backlog
- DB lock error rate
- zero-change ratio

#### Rule

- healthy queue: launch normally
- degraded queue: reduce concurrency and suppress meta lanes
- critical queue: allow only closure-oriented work

#### Notes

- this is load shedding for orchestration, not just infrastructure

#### Minimum tests

- high superseded count suppresses new family creation
- critical queue prevents docs/ledger fanout
- closure-oriented review tasks still flow

### Control Spec 7: Meaningful-Output Gate

#### Intent

Force the benchmark to distinguish real progress from theater.

#### Inputs

- changed-file evidence
- validation evidence
- duplicate classification
- task category

#### Rule

- benchmark-credit only if evidence meets quality bar
- zero-change runs cannot count as fixed issue closures unless they are explicitly classified as validation artifacts attached to an already accepted family

#### Minimum tests

- zero-change run is denied benchmark credit
- validation-only run can attach to accepted family without inflating fix count
- docs-only lane cannot count as core fix

### Control Spec 8: Persistence-Safe Reconciliation

#### Intent

Make accounting and result state durable enough that DB contention does not cause expensive confusion.

#### Inputs

- append-only usage journal
- append-only result journal
- reconciliation idempotency key
- DB health

#### Rule

- write append-only journal first
- reconcile relational state second
- if reconciliation fails, result remains replayable and countable for diagnostics but not for benchmark acceptance until merged

#### Minimum tests

- DB lock during merge does not lose usage facts
- replay merges exactly once
- duplicate replay does not double-count spend

### Control Spec 9: Operator Pause And Re-Arm Control

#### Intent

Make emergency stops obvious, narrow, and auditable.

#### Inputs

- pause reason
- scope
- trip metrics
- re-arm actor

#### Rule

- every pause must name exact cause
- every manual re-arm must write an audit record
- every benchmark pause must avoid collateral damage to unrelated projects by default

#### Minimum tests

- project-scoped pause does not affect unrelated project
- re-arm requires structured reason
- pause reason survives daemon restart

### Control Spec 10: Meta-Lane Suppression

#### Intent

Stop the system from spending expensive cycles on proof and bookkeeping while core work is unhealthy.

#### Inputs

- lane category
- queue-health score
- budget state
- accepted-fix velocity

#### Rule

- in degraded or critical mode, suppress docs/ledger/proof lane creation unless explicitly whitelisted

#### Minimum tests

- degraded benchmark cannot spawn fresh proof lane
- explicit operator override is required for exception

## Alert Catalog

This section defines the alerts that should exist after hardening.

### Budget alerts

1. `MC-BUDGET-SOFT-TOKENS`
   - Trigger: total tokens >= soft threshold
   - Action: enter degraded mode, notify operator
2. `MC-BUDGET-HARD-TOKENS`
   - Trigger: total tokens >= hard threshold
   - Action: pause benchmark launches
3. `MC-BUDGET-HARD-RUNS`
   - Trigger: run attempts >= hard threshold
   - Action: pause benchmark launches
4. `MC-BUDGET-HARD-THREADS`
   - Trigger: fresh threads >= hard threshold
   - Action: deny new thread creation

### Queue alerts

5. `MC-QUEUE-SUPERSEDED-STORM`
   - Trigger: superseded count exceeds threshold
   - Action: freeze new family creation
6. `MC-QUEUE-REVIEW-DEBT`
   - Trigger: needs_review backlog exceeds threshold
   - Action: cut concurrency and focus review closure
7. `MC-QUEUE-PATH-WAIT-STORM`
   - Trigger: waiting_on_paths exceeds threshold
   - Action: suppress overlapping launches

### Reliability alerts

8. `MC-RUNNER-QUOTA-BACKOFF`
   - Trigger: quota circuit opens
   - Action: benchmark-wide cooldown
9. `MC-RUNNER-INVALID-MODEL`
   - Trigger: launch denied for unsupported model
   - Action: operator-visible configuration correction
10. `MC-PERSISTENCE-LOCK-CONTENTION`
    - Trigger: DB lock error rate crosses threshold
    - Action: reduce concurrency and preserve append-only logs

### Quality alerts

11. `MC-QUALITY-ZERO-CHANGE-RATIO`
    - Trigger: zero-change ratio exceeds threshold
    - Action: suppress fanout and freeze families
12. `MC-QUALITY-NO-ACCEPTED-FIX-VELOCITY`
    - Trigger: accepted-fix velocity below threshold for time window
    - Action: degrade benchmark and require plan refresh

## Operator Runbooks

These runbooks are the human-facing counterpart to the code changes.

### Runbook A: Hard token budget tripped

1. Confirm project ID and benchmark ID.
2. Confirm current total tokens and hard threshold.
3. Verify no unrelated projects were paused.
4. Inspect top burning families.
5. Decide whether to:
   - reduce scope
   - re-budget
   - end benchmark
6. Re-arm only with a written reason.

### Runbook B: Quota circuit opened

1. Confirm provider and exact limit signal.
2. Inspect whether the trigger came from:
   - request-rate exhaustion
   - token-rate exhaustion
   - spend/credit exhaustion
3. Verify that no new expensive launches are happening.
4. Wait for cooldown or manually hold the benchmark.
5. Allow only explicit half-open probe if justified.

### Runbook C: Invalid model policy denial

1. Inspect selected manager and worker model.
2. Inspect active provider/runtime mode.
3. Confirm benchmark policy restrictions.
4. Correct settings.
5. Re-run preflight only.
6. Do not launch benchmark-wide work until preflight passes.

### Runbook D: Scheduler churn storm

1. Inspect family registry for duplicate families.
2. Count superseded tasks and unblock tasks.
3. Freeze new family creation.
4. Collapse duplicate families.
5. Resume only closure-oriented work.

### Runbook E: Persistence contention

1. Inspect DB lock rate.
2. Confirm append-only journals still writing.
3. Reduce concurrency immediately.
4. Reconcile stranded results.
5. Only then consider re-expansion.

## Anti-Pattern Catalog

Mission Control needs an explicit list of behaviors that are forbidden because they look helpful until they bankrupt the run.

### Anti-pattern 1: Retry because “it might work now”

Bad because:

- it is not evidence-based
- it multiplies cost
- it hides poor classification

### Anti-pattern 2: Recreate lane instead of fixing family state

Bad because:

- it resets visual state without resetting real cost
- it inflates thread count
- it breaks true retry accounting

### Anti-pattern 3: Use docs or ledger lanes as throughput filler

Bad because:

- it looks like activity
- it may count toward morale while harming benchmark completion

### Anti-pattern 4: Allow silent model fallback

Bad because:

- it hides runtime mismatch
- it makes results less reproducible

### Anti-pattern 5: Treat zero-change runs as neutral

Bad because:

- they are negative signal when frequent
- they indicate bad scoping or duplication

### Anti-pattern 6: Let monitor automations restart broken benchmarks indefinitely

Bad because:

- the babysitter becomes an accidental auto-amplifier

## Acceptance Criteria For The Hardened System

Mission Control should not be considered fixed enough for aggressive live benchmark runs until all of these are true.

### Economic controls

- hard token budget exists and is enforced
- hard run budget exists and is enforced
- hard thread budget exists and is enforced

### Launch controls

- all live launches route through one admission controller
- unsupported model combinations are denied before launch
- cloud and fast-mode prohibitions are enforced before launch

### Retry controls

- family retry budget exists
- quota breaker exists
- retries use jittered backoff
- nontransient failures do not auto-retry

### Quality controls

- zero-change runs cannot count as accepted fixes
- duplicate family work cannot inflate fix counts
- review debt suppresses fresh low-value lane creation

### Reliability controls

- append-only spend/result journals exist
- DB lock spikes reduce concurrency
- daemon restart preserves pause reasons and budget trips

### Operator controls

- project-scoped kill switch exists
- pause reasons are visible
- re-arm is auditable

## 30 / 60 / 90 Day Implementation Roadmap

### Day 0 to Day 30

Goals:

- stop the next catastrophe cheaply

Deliver:

- benchmark budgets
- launch admission controller skeleton
- fail-closed model policy gate
- quota breaker
- operator-visible pause reasons

Success signal:

- no benchmark can run without explicit budget config

### Day 31 to Day 60

Goals:

- eliminate major churn multipliers

Deliver:

- family registry
- retry budgets
- zero-change gating
- queue-health governor
- meta-lane suppression

Success signal:

- repeated family storms are prevented in replay tests

### Day 61 to Day 90

Goals:

- make the system resilient and observable under stress

Deliver:

- append-only journals
- adaptive concurrency based on DB health
- spend dashboards
- half-open recovery probes
- chaos and replay suites

Success signal:

- incident replay causes early self-stop instead of runaway burn

## Suggested Issue Backlog

This section turns the plan into directly actionable issue candidates.

1. Add benchmark budget models and migrations.
2. Add budget rollup service with hard-stop enforcement.
3. Add resolved runtime/model compatibility gate.
4. Add benchmark-wide provider quota breaker.
5. Add task-family model and dedupe keys.
6. Add family retry budgets.
7. Add zero-change output gate.
8. Add queue-health scoring and degraded-mode suppression.
9. Add append-only usage journal.
10. Add append-only result journal.
11. Add DB-lock adaptive throttling.
12. Add project-scoped operator kill switch.
13. Add re-arm audit records.
14. Add spend dashboard surfaces.
15. Add thread/session creation accounting.
16. Add replay tests for incident-style churn.
17. Add chaos tests for quota and overload.
18. Add documentation updates for benchmark policy and emergency controls.

## Final Design Position

The root lesson is simple even if the implementation is not:

Mission Control cannot be trusted to run aggressive parallel benchmarks until cost control is part of the core state machine, not just an after-the-fact metric.

The incident was not caused by having many agents. It was caused by allowing many expensive state transitions without enough skepticism, enough budget discipline, or enough refusal to continue.

The fix is to teach the system to say no earlier, more often, and for the right reasons.

## Subsystem Deep Dives

This section goes subsystem by subsystem so future implementation work can be split cleanly without losing architectural intent.

### Subsystem Deep Dive: Usage Tracking

Current strength:

- the repo already normalizes useful token and context metrics

Current weakness:

- usage state is not the authority for whether new work may start

Required end state:

- `usage_tracking.py` continues to normalize data
- a separate controller consumes those normalized values and emits policy decisions
- rollups are available by run, family, project, benchmark, and provider

Recommended design boundary:

- `usage_tracking.py` should not know business policy
- `budget_controller.py` should know budget policy
- `manager.py` and `orchestration.py` should ask the budget controller for a decision

Implementation notes:

- add helpers that emit normalized usage deltas rather than only merged snapshots
- store provenance of usage data:
  - estimated
  - partial
  - provider-reported
  - reconciled
- record confidence level because denial rules may differ when data is estimated versus verified

Why this matters:

If spend is not trustworthy enough for automated decisions, the controller must degrade conservatively. “We were not sure how much we spent” is not a reason to continue launching work.

### Subsystem Deep Dive: Project Settings And Model Policy

Current strength:

- settings normalization exists
- default Codex worker model is pinned to `gpt-5.4-mini`

Current weakness:

- normalization is not the same as preflight compatibility proof

Required end state:

- every project has a resolved, validated, launchable policy state

Suggested shape:

- `raw_settings`
- `normalized_settings`
- `validated_runtime_policy`

The system should not jump from raw settings directly to launch.

Implementation notes:

- add a preflight API and internal service that returns:
  - `launchable: true|false`
  - `blockers`
  - `normalized_provider`
  - `normalized_manager_model`
  - `normalized_worker_model`
  - `runtime_support_matrix`
- persist last successful validation result with timestamp
- invalidate cached validation after:
  - provider change
  - model change
  - runner mode change
  - authentication/runtime health change

Why this matters:

One invalid model storm is enough to prove that “normalization” is not a sufficient guarantee.

### Subsystem Deep Dive: Manager Scheduling

Current strength:

- the manager already contains much of the orchestration logic
- it already knows about swarm budgets, provider backoff, path waits, and benchmark reset concepts

Current weakness:

- too many responsibilities sit in one place without a strong admission-control choke point

Required end state:

- the manager becomes policy-aware but not policy-fragmented

Suggested internal decomposition:

- `BudgetController`
- `AdmissionController`
- `FamilyRegistry`
- `QueueHealthService`
- `ReviewDebtService`
- `BackoffCircuitService`

The manager should orchestrate decisions across these services, not duplicate their logic.

Implementation notes:

- before lane creation, ask `FamilyRegistry` whether family already exists
- before launch, ask `AdmissionController`
- after run completion, ask `BudgetController` and `QueueHealthService` whether concurrency should contract
- after repeated family failure, require explicit strategy shift instead of same-family relaunch

Why this matters:

The incident happened partly because the manager knew too many partial truths and not enough total truths.

### Subsystem Deep Dive: Orchestration Background Turns

Current strength:

- orchestration already has background turn scheduling and restart reconciliation logic

Current weakness:

- background retries can still amplify cost if benchmark state is unhealthy

Required end state:

- background work is cheap, bounded, and budget-aware

Implementation notes:

- background turns should carry an explicit spend class:
  - `freeish_control_plane`
  - `low_cost_probe`
  - `expensive_worker_launch`
- degraded benchmark state should allow only the first two by default
- background retries should require `AdmissionController` approval when they might trigger expensive work

Why this matters:

Control-plane retries are often where invisible cost begins.

### Subsystem Deep Dive: Runner Integration

Current strength:

- CLI runner can classify failure text and synthesize structured failure results

Current weakness:

- runner output classification happens after process launch, which is too late for some avoidable failures

Required end state:

- launch-time policy stops predictable failures
- runtime event parsing enriches accounting and breaker state
- result envelopes preserve enough detail for replay and audit

Implementation notes:

- add explicit runner event types for:
  - provider_rate_limited
  - provider_usage_limited
  - invalid_model_policy
  - structured_result_missing
  - context_window_high
- avoid relying only on freeform summary text for breaker logic

Why this matters:

String-matching summaries are better than nothing and worse than structured events.

### Subsystem Deep Dive: Task Board And Family Registry

Current strength:

- tasks already have statuses for waiting, review, done, blocked
- path-lock semantics exist

Current weakness:

- status alone is not enough to prevent duplicate logical work

Required end state:

- tasks are children of family state, not isolated atoms with weak memory

Implementation notes:

- task board rendering should group by family when relevant
- “unblock” should be a family transition, not automatically a fresh family
- superseding should preserve family accounting and visibility

Why this matters:

The system must remember what it already tried, not just what current task row says.

### Subsystem Deep Dive: Review And Handoff

Current strength:

- review gating exists
- handoff status is surfaced

Current weakness:

- review debt can grow while new work keeps spawning

Required end state:

- review backlog is a launch-suppression signal
- families cannot keep generating new work while previous evidence is unresolved

Implementation notes:

- cap outstanding review-producing lanes
- prioritize closure of review debt before spawning new validation-heavy or docs-heavy work
- distinguish between:
  - review debt for likely-valuable work
  - review debt for clearly duplicate or weak work

Why this matters:

Review is where truth catches up to ambition. If review falls behind, throughput metrics lie.

## Service-Level Indicators And Objectives

Mission Control needs measurable reliability goals for this exact problem class.

### Economic SLIs

1. `tokens_per_accepted_fix`
2. `fresh_threads_per_accepted_fix`
3. `family_attempts_per_accepted_fix`
4. `zero_change_runs_ratio`
5. `meta_lane_tokens_ratio`

### Reliability SLIs

1. `db_lock_failures_per_100_runs`
2. `runner_envelope_integrity_failure_rate`
3. `quota_breaker_open_events_per_benchmark`
4. `invalid_model_launch_denials_per_benchmark`

### Queue Health SLIs

1. `superseded_task_ratio`
2. `review_backlog_age_p95`
3. `waiting_on_paths_ratio`
4. `blocked_family_ratio`

### Suggested SLOs

These are starting points, not gospel.

- `zero_change_runs_ratio < 0.10` during healthy benchmark operation
- `fresh_threads_per_accepted_fix < 3`
- `family_attempts_per_accepted_fix < 5`
- `superseded_task_ratio < 0.15`
- `db_lock_failures_per_100_runs < 1`
- `meta_lane_tokens_ratio < 0.15` during core-fix benchmark windows

If these SLOs drift, Mission Control should treat it as degraded benchmark health even before hard budgets trip.

## Sample Benchmark Policy Profile

This is a concrete example of how a hardened benchmark policy could look.

```json
{
  "name": "50-fix-live-benchmark",
  "enabled": true,
  "runner_mode": "cli",
  "allow_cloud_execution": false,
  "allow_fast_mode": false,
  "allowed_manager_models": ["gpt-5.4", "gpt-5.4-mini"],
  "allowed_worker_models": ["gpt-5.4-mini"],
  "hard_total_tokens_limit": 120000000,
  "soft_total_tokens_limit": 80000000,
  "hard_run_attempt_limit": 300,
  "hard_thread_creation_limit": 250,
  "hard_zero_change_run_limit": 20,
  "hard_superseded_task_limit": 25,
  "max_active_workers": 8,
  "max_meta_lane_ratio": 0.15,
  "max_family_attempts": 6,
  "max_family_tokens": 6000000,
  "quota_cooldown_seconds": 1800,
  "manual_rearm_required_after_quota": true,
  "manual_rearm_required_after_hard_budget": true
}
```

The exact numbers may change. The important part is the structure. Policy has to exist in a durable, explicit, inspectable form.

## Sample Launch Decision Payload

This is what a launch decision should look like when the admission controller answers.

```json
{
  "project_id": 11,
  "benchmark_id": "50-fix-live-benchmark",
  "task_id": 356,
  "family_key": "apps-mcp-server-tests-defect-batch",
  "decision": "deny",
  "reason": "family_retry_budget_exhausted",
  "details": {
    "family_attempts": 7,
    "family_attempt_limit": 6,
    "family_total_tokens": 58125393,
    "family_token_limit": 6000000
  },
  "recommended_next_action": "re-plan_or_manual_review",
  "emitted_at": "2026-06-24T15:00:00Z"
}
```

Why this matters:

- operators can understand it
- tests can assert it
- monitor surfaces can display it
- logs can aggregate it

## Verification Appendix

This appendix lays out deeper scenario coverage than the shorter matrix earlier in the paper.

### Scenario Set 1: Preflight failures

1. Worker model unsupported but manager model valid.
2. Manager model unsupported but worker model valid.
3. Provider switched but stale validated policy remains cached.
4. Benchmark policy forbids cloud but runner is configured for cloud.
5. Benchmark policy forbids fast mode but profile requests it.

Expected pattern:

- all denied before worker process spawn
- denial reason machine-readable
- denial reason visible to operator

### Scenario Set 2: Budget pressure

1. Soft token budget crossed during healthy queue state.
2. Hard token budget crossed during healthy queue state.
3. Hard run budget crossed before hard token budget.
4. Hard thread budget crossed while token budget remains under soft limit.
5. Zero-change hard limit crossed while spend remains acceptable.

Expected pattern:

- budget-specific trip reason
- correct degraded or paused state
- no unrelated project impact

### Scenario Set 3: Family storms

1. Same logical family recreated under multiple task titles.
2. Same family retried after repeated no-change runs.
3. Same family retried after invalid model failure.
4. Same family retried after quota breaker opened.

Expected pattern:

- family counters accumulate across aliases
- family freeze occurs on threshold
- retries denied when nontransient

### Scenario Set 4: Queue overload

1. High review debt with low accepted-fix velocity.
2. High superseded count during active worker saturation.
3. Many waiting-on-paths tasks plus overlapping launches requested.
4. DB lock spikes while queue already degraded.

Expected pattern:

- concurrency reduction
- meta-lane suppression
- closure-oriented work prioritized

### Scenario Set 5: Persistence failure

1. Append-only usage journal write succeeds, relational merge fails.
2. Append-only result journal write succeeds, daemon restarts before merge.
3. Replay runs twice due restart.
4. Duplicate journal entries arrive out of order.

Expected pattern:

- no spend loss
- no double-count
- replay idempotent

### Scenario Set 6: Quota recovery

1. Quota breaker opens.
2. Cooldown expires.
3. One half-open probe runs.
4. Probe succeeds.
5. Probe fails.

Expected pattern:

- success closes breaker gradually
- failure reopens breaker immediately
- no swarm-wide relaunch without explicit policy

## Governance And Change Management

This class of failure is too expensive to leave purely to ad hoc code review.

### Required governance rules

1. Any change to runner launch policy must include replay tests.
2. Any change to model policy must include explicit allowlist tests.
3. Any change to benchmark accounting must include duplicate and zero-change tests.
4. Any change to retry logic must include quota and overload simulations.
5. Any change to persistence/reconciliation must include lock-contention tests.

### Required design-review questions

Before approving changes that touch orchestration, reviewers should ask:

1. Can this create more worker runs than before?
2. Can this create more fresh threads than before?
3. Can this bypass budget enforcement?
4. Can this reclassify nontransient failure as transient?
5. Can this make zero-change work look successful?
6. Can this create new family aliases accidentally?
7. Can this lose usage facts if reconciliation fails?

If the answer is “maybe,” the change needs deeper validation.

## Documentation Requirements After Hardening

This paper should not be the only place these rules live.

Mission Control should also gain:

- a benchmark policy guide
- an operator emergency-stop guide
- a model-policy compatibility guide
- a budget and spend telemetry guide
- a queue-health troubleshooting guide

Each guide should explicitly say:

- what the system enforces automatically
- what still requires human judgment
- what signals mean “stop immediately”

## What Success Looks Like

Mission Control is not “fixed” when it can avoid one exact repeat of this incident by lucky special casing.

Mission Control is fixed enough when:

- it can explain why it denied expensive work
- it can stop itself before burn becomes absurd
- it can recover from transient failures without retry storms
- it cannot accidentally use forbidden models or modes
- it does not count work that did not materially advance the benchmark
- operators can see and trust the system’s economic state

That is the standard.

## Metric Dictionary

This dictionary is here so future implementation work does not quietly redefine the core measurements.

### `accepted_fix_velocity`

Definition:

Accepted distinct fixes per hour over a rolling window.

Why it matters:

If this falls while spend rises, the benchmark is unhealthy even if tasks keep flipping state.

### `zero_change_ratio`

Definition:

`zero-change runs / total completed runs` over a rolling window.

Why it matters:

High zero-change ratio is a strong indicator of duplicate work, overvalidation, or poor lane design.

### `family_burn_rate`

Definition:

Tokens spent by one task family per hour.

Why it matters:

One pathological family can torch the budget while the overall queue still looks “busy.”

### `review_debt_age_p95`

Definition:

95th percentile age of `needs_review` items.

Why it matters:

If review debt ages badly, the system is outrunning its own truth-checking loop.

### `superseded_ratio`

Definition:

`superseded tasks / total tasks created` for a benchmark.

Why it matters:

This is a churn metric. High values mean the planner is producing too much disposable work.

### `thread_creation_ratio`

Definition:

Fresh threads created per accepted distinct fix.

Why it matters:

This approximates how much of the system’s cost is being eaten by context churn instead of real progress.

### `retry_effectiveness`

Definition:

`accepted fixes after retry / total retry-driven launches`

Why it matters:

Retries should justify themselves. If this number collapses, retry policy should tighten automatically.

### `quota_signal_density`

Definition:

Quota or usage-limit signals per 100 runs.

Why it matters:

This is a better early-warning metric than waiting for a full benchmark stall.

### `reconciliation_loss_risk`

Definition:

A composite score based on:

- DB lock frequency
- append-only journal lag
- unreconciled run count
- delayed usage rollup count

Why it matters:

Accounting uncertainty is itself a reason to reduce concurrency.

## File-By-File Execution Sequence

This section proposes a sane order for landing the code changes without detonating the repo.

### Step 1: Add schema and model surfaces

Files:

- [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)
- [schemas.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/schemas.py)
- [db.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/db.py)

Add:

- benchmark budget tables
- family registry tables
- quota circuit tables
- journal tables
- read models and update payloads

Reason for doing this first:

Everything else needs durable state and typed interfaces.

### Step 2: Build policy controllers in isolation

Files:

- new `budget_controller.py`
- new `admission_controller.py`
- new `family_registry.py`
- new `queue_health.py`

Add:

- pure logic services
- no launch-path wiring yet
- unit tests first

Reason:

You want policy logic independently testable before it is threaded through manager/orchestration.

### Step 3: Wire launch-time gates

Files:

- [project_settings.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/project_settings.py)
- [system_status.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/system_status.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)

Add:

- resolved runtime policy validation
- launch denials for unsupported combinations
- benchmark policy resolution

Reason:

This closes the invalid-model hole early.

### Step 4: Wire economic admission control

Files:

- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)

Add:

- budget checks before lane creation and worker launch
- project/benchmark degraded states
- benchmark pause states

Reason:

This closes the “observed spend but did not stop” hole.

### Step 5: Wire family registry and dedupe

Files:

- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [task_board.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/task_board.py)

Add:

- family assignment
- family-based retry budgeting
- prevention of duplicate unblock families

Reason:

This closes the churn hole.

### Step 6: Wire runner event improvements

Files:

- [codex_runner/cli_runner.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/codex_runner/cli_runner.py)
- any runner base abstractions

Add:

- explicit event flags for quota/model/result-integrity failures
- session/thread creation accounting
- journal writes

Reason:

This improves signal quality for controllers.

### Step 7: Wire operator UX

Files:

- [bridge_messages.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/bridge_messages.py)
- [bridge_formatter.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/bridge_formatter.py)
- [ascii_monitor.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/ascii_monitor.py)

Add:

- pause reason cards
- budget state summaries
- re-arm controls
- top burning families view

Reason:

Without this, the operator still ends up guessing.

### Step 8: Add replay and chaos suites

Files:

- runner and orchestration tests
- any new replay fixtures under tests or runtime fixtures

Add:

- quota storm replay
- invalid-model replay
- superseded-task storm replay
- DB lock contention replay

Reason:

This is what proves the fix is real.

## Sources

External primary sources used:

1. OpenAI API rate limits guide: [developers.openai.com/api/docs/guides/rate-limits](https://developers.openai.com/api/docs/guides/rate-limits)
2. OpenAI Help Center, rate-limit best practices: [help.openai.com/en/articles/6891753-best-practices-for-managing-my-rate-limits-in-the-api](https://help.openai.com/en/articles/6891753-best-practices-for-managing-my-rate-limits-in-the-api)
3. AWS Builders Library, timeouts/retries/backoff/jitter: [aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)
4. Google SRE, addressing cascading failures: [sre.google/sre-book/addressing-cascading-failures](https://sre.google/sre-book/addressing-cascading-failures/)
5. Microsoft Azure Architecture Center, Retry pattern: [learn.microsoft.com/en-us/azure/architecture/patterns/retry](https://learn.microsoft.com/en-us/azure/architecture/patterns/retry)
6. Microsoft Azure Architecture Center, Circuit Breaker pattern: [learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)

Internal repo evidence used:

- [mission-control-token-spike-postmortem-project-11.md](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/docs/forensics/mission-control-token-spike-postmortem-project-11.md)
- [usage_tracking.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/usage_tracking.py)
- [project_settings.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/project_settings.py)
- [orchestration.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/orchestration.py)
- [manager.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/manager.py)
- [models.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/models.py)
- [schemas.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/schemas.py)
- [cli_runner.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/codex_runner/cli_runner.py)
- [simulation/service.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/simulation/service.py)
- [task_board.py](/C:/Users/mike/OneDrive/Desktop/Codex%20Mission%20Control/apps/server/src/task_board.py)
