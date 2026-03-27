# IBM Hardware Proof — 2026-03-17

## Run summary

- provider: `IBM Quantum Runtime`
- backend: `ibm_torino`
- real runs completed: `3`

### 1) Bell pair

- experiment: `bell_pair`
- shots: `128`
- job id: `d6sjce790okc73escie0`

```json
{
  "11": 51,
  "00": 64,
  "10": 7,
  "01": 6
}
```

- correlated Bell-outcome mass (`00` + `11`): `0.8984`
- off-target mass (`01` + `10`): `0.1016`

### 2) GHZ state

- experiment: `ghz_three`
- shots: `128`
- job id: `d6sjev7gtkcc73clkoqg`

```json
{
  "000": 60,
  "111": 48,
  "110": 9,
  "001": 6,
  "100": 2,
  "101": 2,
  "011": 1
}
```

- GHZ outcome mass (`000` + `111`): `0.8438`

### 3) QAOA-style Max-Cut

- experiment: `qaoa_triangle`
- shots: `128`
- job id: `d6sjfb790okc73esclkg`

- average cut score: `1.2344`
- top sampled states: `000`, `111`, `110`

## Why this matters

This is the key proof that the repo is not only simulator-first. The same workflow that runs locally can be submitted to a real IBM backend and returns readable evidence for:

- foundational entanglement
- multi-qubit coherence
- optimization-style sampling

In other words, the project now demonstrates both quantum-computing basics and backend productization on a real device.
