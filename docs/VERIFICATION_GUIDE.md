# Verification Guide

Fastest path:

1. `GET /api/runtime/brief`
2. `POST /api/runs/local` with `bell_pair`
3. `POST /api/runs/braket-local` with `bell_pair`
4. `POST /api/compare/local-backends` with `bell_pair`
5. `POST /api/runs/local` with `qaoa_triangle`
6. `POST /api/runs/hardware` or `POST /api/runs/braket-hardware` when credentials are configured
7. `GET /api/runs`

What should be obvious:

- the system differentiates local simulator runs from Braket local runs and real hardware runs
- the system can compare two local execution stacks before anyone overclaims hardware readiness
- hardware mode is explicit and does not pretend to exist without credentials
- Bell and GHZ show foundational circuit understanding
- QAOA-style Max-Cut shows a small optimization workflow
- result history is persisted and inspectable instead of being lost in notebook output
