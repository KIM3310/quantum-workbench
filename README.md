# Quantum Workbench

A web-based experiment desk for running quantum circuits across local simulators, Amazon Braket, and IBM Quantum hardware, then comparing results side by side.

![Quantum Workbench home](docs/screenshots/quantum-workbench-home.png)

## What it does

- Pick from built-in experiments (Bell pair, GHZ, QAOA, H2 VQE)
- Run locally on Qiskit's ideal sampler or Braket's local simulator
- Submit the same circuit to real IBM Quantum or Braket hardware
- Compare counts, noise, and backend metadata across runs
- Persist run history through a simple API and lightweight UI

## Experiments

| Experiment | Description |
|---|---|
| `bell_pair` | 2-qubit Bell state - shows entanglement and hardware noise |
| `ghz_three` | 3-qubit GHZ state - shows multi-qubit coherence |
| `qaoa_triangle` | Single-layer QAOA Max-Cut on a triangle graph |
| `h2_vqe_mini` | Small H2 Hamiltonian with exact baseline and parameter sweep |

## Real hardware results

Verified on `ibm_torino` (2026-03-17):
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
```

### Amazon Braket (optional)
```bash
export AWS_PROFILE="<your_profile>"
export AWS_DEFAULT_REGION="us-west-1"
```

If credentials aren't set, hardware routes are blocked and local simulation still works.

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
| `POST /api/runs/hardware` | Submit to IBM hardware |
| `POST /api/runs/braket-hardware` | Submit to Braket hardware |
| `GET /api/evidence/scorecard` | Latest run summary |
| `GET /api/ibm/proof-pack` | IBM backend results and metadata |

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

58 tests covering circuit construction, backend selection, result parsing, API contracts, chemistry workflow, and store persistence.

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

This repository includes a neutral cloud and AI engineering blueprint that maps the current proof surface to runtime boundaries, data contracts, model-risk controls, deployment posture, and validation hooks.

- [Cloud + AI architecture blueprint](docs/cloud-ai-architecture.md)
- [Machine-readable architecture manifest](docs/architecture/blueprint.json)
- Validation command: `python3 scripts/validate_architecture_blueprint.py`
