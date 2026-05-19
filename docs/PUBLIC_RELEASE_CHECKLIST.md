# Public Release Checklist

> Status: Current

Use this checklist before treating the repository as ready for a public-facing release.

## Documentation

- README is short, clear, and background-running first
- LICENSE is present
- SECURITY.md is present
- CONTRIBUTING.md is present
- docs index is current
- wiki is polished
- background install docs are current
- the background-running happy path is documented
- known limitations are documented

## Quality and safety

- no old UI-first language remains in README
- no secrets appear in docs or examples
- tests and validation checks have been run
- health doctor workflow is documented
- API-backed runner caveats are explicit

## Release gate

- do not create the first public release tag until the documented happy path passes end to end
