# IBM Runtime Options Note — 2026-03-17

## Backend

- backend: `ibm_torino`
- experiment: `bell_pair`
- shots: `128`

## Runs

### Baseline

- correlated Bell-outcome mass: `0.8984`
- off-target mass: `0.1016`

### Twirling enabled

- options:
  - `enable_twirling = true`
- correlated Bell-outcome mass: `0.8984`
- off-target mass: `0.1016`
- usage:
  - `quantum_seconds = 1`
  - `usage_estimation_quantum_seconds = 2.623782965`

### Dynamical decoupling enabled

- options:
  - `enable_dynamical_decoupling = true`
- correlated Bell-outcome mass: `0.8047`
- off-target mass: `0.1953`
- usage:
  - `quantum_seconds = 1`

## Reading

For this small Bell-state run on `ibm_torino`:

- twirling preserved the same Bell correlation signal as the baseline run
- the chosen dynamical-decoupling configuration did not improve the result and produced a lower Bell signal

That is useful evidence because it shows the project is not treating IBM Runtime options as decorative checkboxes. It is measuring whether those options actually help on a real backend.

