# Quantum Workbench

## Live Demo

- [Open the public Cloudflare Pages demo](https://quantum-workbench.pages.dev/)
- Scope: credential-free, synthetic-data demo for technical review paths and evaluators.

> **Curated supporting repo**
> This repository is kept as optional proof, but it no longer leads the portfolio.
> Current front door: **agent-orchestration-benchmark, tool-call-finetune-lab, and stage-pilot**.
> Reason: Broad education/research tooling is less targeted than the current AI platform, governance, and ops lanes.

A web-based experiment desk for running quantum circuits across local simulators, Amazon Braket, and IBM Quantum hardware, then comparing results side by side.

![Quantum Workbench home](docs/screenshots/quantum-workbench-home.png)

## System Overview

A quantum experiment desk that shows research-tool discipline: local simulation first, managed backends second.

| Area | Details |
|---|---|
| Users | Research teams, students, technical reviewers, and cloud/quantum platform evaluators. |
| System scope | Qiskit/Braket framing, local simulation, optional managed-backend adapters, and experiment review surfaces. |
| Operating boundary | Managed backend use should be opt-in and budget-controlled; local simulation remains the safe default. |
| Evaluation path | Run the local simulation path and inspect generated experiment outputs and adapter boundaries. |

## Evaluation Path

- **Start here:** Generate one circuit, inspect the explanation, then compare the simulation output.
- **Local demo:** Run the Quick Start commands and open `http://127.0.0.1:8000/`.
- **Checks:** Run `pytest -v` and the architecture validation script when reviewing repository posture.

## Service Launch Playbook

- [Service launch playbook](docs/service-launch-playbook.md) maps the repository to its product scope, operating gates, operating boundaries, and risk controls.

## Architecture Notes

- [Architecture guide](docs/architecture-evidence-map.md) summarizes the system scope, first files to inspect, runtime commands, and known boundaries.
- [Quality notes](docs/quality-gate.md) lists the local checks, CI surface, and release expectations for this repository.
- [Enterprise readiness notes](docs/enterprise-readiness.md) outlines security, data, operations, integration, and handoff expectations.
- [Repository positioning](docs/repository-positioning.md) explains why this repository is archived/supporting and where the current technical entry points live.

## What it does

- Pick from built-in experiments (Bell pair, GHZ, QAOA, H2 VQE)
- Run locally on Qiskit's ideal sampler or Braket's local simulator
- When credentials and an operator token are configured, submit the same circuit to IBM Quantum or Braket hardware
- Compare counts, noise, and backend metadata across runs
- Persist run history through a simple API and lightweight UI

## Experiments

| Experiment | Description |
|---|---|
| `bell_pair` | 2-qubit Bell state - shows entanglement and hardware noise |
| `ghz_three` | 3-qubit GHZ state - shows multi-qubit coherence |
| `qaoa_triangle` | Single-layer QAOA Max-Cut on a triangle graph |
| `h2_vqe_mini` | Small H2 Hamiltonian with exact baseline and parameter sweep |

## Real hardware evidence

Historical hardware run on `ibm_torino` (2026-03-17). This is evidence of adapter behavior, not a public hardware-access guarantee:
- `bell_pair`: entanglement signal 0.8984 (115/128 correlated outcomes)
- `ghz_three`: GHZ signal 0.8438 (108/128)
- `qaoa_triangle`: avg cut score 1.2344, close to local baseline with visible device noise

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/`

### IBM Quantum (optional)
```bash
export IBM_QUANTUM_TOKEN="<your_token>"
export QUANTUM_OPERATOR_TOKEN="<operator-token-for-hardware-routes>"
```

### Amazon Braket (optional)
```bash
export AWS_PROFILE="<your_profile>"
export AWS_DEFAULT_REGION="us-west-1"
```

If credentials aren't set, hardware routes are blocked and local simulation still works. If provider credentials exist but `QUANTUM_OPERATOR_TOKEN` is missing, hardware routes still fail closed.

## API

| Endpoint | Description |
|---|---|
| `GET /health` | Runtime status |
| `GET /api/experiments` | Experiment catalog |
| `GET /api/backends` | Available hardware backends |
| `GET /api/runs` | Run history |
| `POST /api/runs/local` | Run on ideal local sampler |
| `POST /api/runs/braket-local` | Run on Braket local simulator |
| `POST /api/compare/local-backends` | Compare both local stacks |
| `POST /api/runs/hardware` | Operator-token guarded IBM hardware submission |
| `POST /api/runs/braket-hardware` | Operator-token guarded Braket hardware submission |
| `GET /api/evidence/scorecard` | Latest run summary |
| `GET /api/ibm/proof-pack` | Operator-token guarded IBM backend results and metadata |

## Architecture

```text
+------------------+       +------------------+       +-------------------+
|   Browser / UI   | ----> |   FastAPI App    | ----> |  Quantum Runtime  |
|  (static files)  |       |   (main.py)      |       |   (runtime.py)    |
+------------------+       +------------------+       +-------------------+
                                   |                         |
                                   v                         v
                           +---------------+     +-----------------------+
                           |  RunStore     |     |   Experiments         |
                           | (store.py)    |     |   (experiments.py)    |
                           | JSON persist  |     |   Circuit builders    |
                           +---------------+     +-----------------------+
                                                         |
                                        +----------------+----------------+
                                        v                v                v
                                 +-----------+   +-----------+   +-----------+
                                 |  Qiskit   |   |  Braket   |   |  IBM /    |
                                 |  Local    |   |  Local    |   |  Braket   |
                                 | Simulator |   | Simulator |   | Hardware  |
                                 +-----------+   +-----------+   +-----------+
```

## Tests

The automated suite covers circuit construction, backend selection, result parsing, API contracts, the chemistry workflow, and store persistence.

```bash
pytest -v
```

## Project structure

```text
quantum-workbench/
  app/
    main.py
    quantum/
      experiments.py
      runtime.py
      store.py
    static/
      index.html, app.js, style.css
  docs/
  scripts/
  tests/
```

## References

- [IBM Quantum Docs](https://docs.quantum.ibm.com)
- [Amazon Braket Docs](https://docs.aws.amazon.com/braket/)

## Cloud + AI Architecture

- [Cloud + AI architecture blueprint](docs/cloud-ai-architecture.md)
- [Machine-readable architecture manifest](docs/architecture/blueprint.json)
- Validation command: `python3 scripts/validate_architecture_blueprint.py`

## Enterprise Productization

- [Product operating model](docs/product-operating-model.md) defines the product scope, trust boundary, operating checks, and service path for this repository.

## System Architecture

- [System architecture](docs/system-architecture.md) maps the runtime boundary, data/control flow, cloud or local deployment surface, and operating assumptions for this repository.

## Service Architecture

- [Service architecture](docs/service-architecture.md) defines the cloud resources, account information, cost controls, and production guardrails needed to turn this repo into a scoped service without publishing public financial assumptions.

<!-- search-growth-readme:start -->

## Search And Service Surface

- Public entry: free simulator-first demo and static architecture page
- Paid boundary: private prototype customization for simulator-first lab workspaces, course bundles, and provider-cost planning reports
- Canonical URL: https://quantum-workbench.pages.dev/
- Lead capture: https://kim3310-doeon-kim-portfolio.pages.dev/?offer=quantum-workbench&inquiry=consumer-prototype-customization#private-inquiry
- Resource route: https://kim3310-doeon-kim-portfolio.pages.dev/resources/quantum-workbench/
- Commercial route: https://kim3310-doeon-kim-portfolio.pages.dev/?offer=quantum-workbench#service-offers
- Machine-readable offer: [docs/service-offer.json](docs/service-offer.json)
- Search growth implementation: [docs/search-growth-implementation.md](docs/search-growth-implementation.md)
- Revenue architecture: [docs/revenue-architecture.md](docs/revenue-architecture.md)
- Claim boundary: public pages use synthetic/local demo data; managed hardware paths require customer/operator credentials and do not imply public hardware access or revenue.

<!-- search-growth-readme:end -->

<!-- KIM3310:AD-DATA-PIVOT:START -->
## Free Resource, Advertising, and Aggregate Data

- [Public utility and architecture checklist](https://kim3310-doeon-kim-portfolio.pages.dev/resources/quantum-workbench/)
- Revenue model: contextual advertising on the policy-eligible central resource page.
- Aggregate value: anonymous aggregate quantum-learning topic interest and resource CTA counts
- Boundary: ads allowed only on public learning pages; experiment state, saved notes, and result flows are ad-free
- Consent defaults off, DNT/GPC fail closed, and personal or sensitive data is never sold.
<!-- KIM3310:AD-DATA-PIVOT:END -->
