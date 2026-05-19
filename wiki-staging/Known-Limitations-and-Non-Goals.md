# Known Limitations and Non Goals

This page captures the current edges of the product so the wiki does not oversell unfinished systems.

> Status: Current

## Reference

- standalone dashboard is optional, not primary
- some install/autowire surfaces remain planned or partial
- runner support depth varies by local environment
- worker orchestration hardening is still in progress
- plugin packaging may evolve

## Do not build right now

- standalone dashboard UI is optional/future
- dashboard widgets are not the current priority
- headless Codex chat UX is the current priority
- deeper app-server integration remains experimental
- API-backed runners require secure config and explicit user awareness

## GitHub wiki rendering notes

- the current staged wiki does not show broken internal links
- `_Sidebar.md` is moderate in size and does not appear unusually large
- filenames are plain Markdown names without encoded punctuation or unusual Unicode
- duplicate-looking pages are reference-oriented, not exact duplicates

Possible cause if GitHub still shows repeated `Uh oh! There was an error while loading.` messages:

- a transient GitHub wiki rendering or page-list issue
- a GitHub-side cache problem
- a partial sync state in the live wiki repo after page updates

If the error persists after pushing the pages, confirm the live wiki repo contents and then treat it as a possible GitHub rendering issue rather than assuming the markdown is broken.

## Example

Use this page when a user or contributor needs a compact reference instead of a full architecture walkthrough.

## Related pages

- [Roadmap](Roadmap)
- [Headless First Direction](Headless-First-Direction)
- [Troubleshooting CLI Runners](Troubleshooting-CLI-Runners)
