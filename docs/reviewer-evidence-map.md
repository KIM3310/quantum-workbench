# Review Guide - Quantum Workbench

Updated: 2026-05-30

Use this page as the short path through the repository. It keeps the review grounded in the code, docs, commands, and boundaries that are already present.

## Summary

| Field | Notes |
|---|---|
| Lane | B2B/B2C education and research tooling |
| Core idea | Experiment desk comparing local quantum simulation with optional managed backends. |
| Primary reader | Students, research teams, workshop instructors, and cloud/quantum platform evaluators. |
| Stack | Python |

## Open First

1. Start with the README fast path and architecture section.
2. Open `docs/monetization-playbook.md` only when reviewing the product or service angle.
3. Check the commands below before making claims about quality.
4. Skim the CI workflows and fixture data before deeper implementation review.
5. Read the boundaries section before presenting the project externally.

## Checks

| Purpose | Command |
|---|---|
| Test suite | `python -m pytest` |

## CI

- .github/workflows/architecture-blueprint.yml
- .github/workflows/ci.yml
- .github/workflows/dependency-review.yml
- .github/workflows/repository-health.yml
- .github/workflows/repository-surface.yml
- .github/workflows/secret-scan.yml

## Evidence

- pytest/ruff-style local verification path
- pytest passes
- Local simulator works
- Managed backend is opt-in

## Commercial Notes

| Possible offer | Working price assumption |
|---|---|
| Workshop artifact | $500-$2k workshop kit |
| Experiment dashboard starter | $3k-$12k research dashboard |
| Research-support prototype | $99-$499/month education workspace |

## Boundaries

- Budget controls for managed backends
- Approximation limits explicit
- No production decision claims

## Useful Metrics

- Experiment completion
- Backend cost visibility
- Learning outcome feedback
