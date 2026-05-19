# Known Limitations and Non Goals

This page captures the current edges of the product so the wiki does not oversell unfinished systems.

> Status: Current

## Current limitations

- some install and autowire surfaces remain partial
- runner support depth varies by local environment
- orchestration hardening is still in progress
- plugin packaging and local setup may continue to evolve

## Do not build right now

- standalone dashboard UI is optional or future-facing
- dashboard widgets are not the current priority
- background-running Codex chat UX is the current priority
- deeper app-server integration remains experimental
- API-backed runners require secure configuration and explicit user awareness

## GitHub wiki rendering notes

- the staged wiki does not currently show broken internal links
- `_Sidebar.md` is moderate in size and does not appear unusually large
- filenames are plain Markdown names without unusual punctuation or Unicode
- there are no exact duplicate content pages in the staged set

If GitHub still shows repeated `Uh oh! There was an error while loading.` messages after a push, the most likely remaining causes are a GitHub-side rendering or cache issue rather than a broken staged markdown set.

## Related pages

- [Roadmap](Roadmap)
- [Background-Running Direction](Headless-First-Direction)
- [Troubleshooting CLI Runners](Troubleshooting-CLI-Runners)
