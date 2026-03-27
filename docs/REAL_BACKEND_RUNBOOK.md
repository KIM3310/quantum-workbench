# Real Backend Runbook

This repo already supports:

- `IBM Quantum Runtime`
- `Amazon Braket`

The fastest real-backend proof is still:

1. `bell_pair` on IBM Quantum
2. `bell_pair` on Amazon Braket

That keeps the explanation simple and the spend small.

## IBM Quantum

Set:

```bash
export IBM_QUANTUM_TOKEN="<your_token>"
export IBM_QUANTUM_CHANNEL="ibm_quantum_platform"
```

Run:

```bash
./.venv311/bin/python scripts/run_real_backend_demo.py --provider ibm --experiment bell_pair --shots 128
```

## Amazon Braket

Set:

```bash
export AWS_PROFILE="<your_profile>"
export AWS_DEFAULT_REGION="us-west-1"
export AMZN_BRAKET_BUCKET="<optional_bucket>"
```

Run:

```bash
./.venv311/bin/python scripts/run_real_backend_demo.py --provider braket --experiment bell_pair --shots 100
```

## Expected output

The helper script prints:

- selected provider
- selected experiment
- backend name
- run id
- submission status
- polling hint

If credentials are missing, the script fails fast with a clear message instead of pretending the run worked.

