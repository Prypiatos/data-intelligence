# Contributing Guidelines

## Branches
Each member has their own branch. Work there, don't push to other branches.

| Branch | Owner |
|---|---|
| `anomaly-detection` | Tharupahan |
| `data-ingestion` | [Name] |
| `load-forecasting` | [Name] |
| `stream-processing` | [Name] |
| `analytics-api` | [Name] |

## Commits
Keep them small and focused. One thing per commit.

```
add kafka consumer for smart meter topic
fix influxdb connection timeout
```

Not this:
```
changes
fixed stuff
wip
```

## Raising a PR
- Check Branch is up to date with `main` first.
- Fill in the PR template - [Find it here](.github/PULL_REQUEST_TEMPLATE.md)
- Tag the issue in PR description like this - `Closes #12`
- Don't merge your own PR. 

## Shared files
`requirements.txt`, `pyproject.toml`, `.env.example` - Be mindful when editing these not to overwrite others' work and avoid conflicts
