"""Quantum experiment definitions, circuit builders, and analysis routines.

Provides a registry of experiments (Bell pair, GHZ, QAOA Max-Cut, H2 VQE),
Qiskit and Braket circuit construction, measurement analysis with per-experiment
metrics, and an H2 Hamiltonian reference implementation for chemistry workflows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import isfinite, pi
from typing import Any

from braket.circuits import Circuit as BraketCircuit
from qiskit.circuit import Parameter
from qiskit import QuantumCircuit
import numpy as np
from qiskit.quantum_info import SparsePauliOp, Statevector

logger = logging.getLogger("quantum_workbench.experiments")


@dataclass(frozen=True)
class ExperimentDefinition:
    """Immutable definition for a registered quantum experiment.

    Attributes:
        experiment_id: Unique identifier used in API paths and run records.
        title: Human-readable experiment title.
        summary: Brief description of the experiment's purpose.
        category: Classification (foundations, optimization, chemistry).
        qubits: Number of qubits required by the circuit.
        default_shots: Recommended shot count for local execution.
        parameter_defaults: Default values for parameterized circuits.
    """

    experiment_id: str
    title: str
    summary: str
    category: str
    qubits: int
    default_shots: int
    parameter_defaults: dict[str, float]


EXPERIMENTS: dict[str, ExperimentDefinition] = {
    "bell_pair": ExperimentDefinition(
        experiment_id="bell_pair",
        title="Bell Pair Entanglement",
        summary="Prepare a Bell state and compare ideal versus real-backend bitstring concentration.",
        category="foundations",
        qubits=2,
        default_shots=1024,
        parameter_defaults={},
    ),
    "ghz_three": ExperimentDefinition(
        experiment_id="ghz_three",
        title="GHZ State (3 Qubits)",
        summary="Prepare a 3-qubit GHZ state to observe multi-qubit coherence and hardware drift.",
        category="foundations",
        qubits=3,
        default_shots=1024,
        parameter_defaults={},
    ),
    "qaoa_triangle": ExperimentDefinition(
        experiment_id="qaoa_triangle",
        title="QAOA-Style Triangle Max-Cut",
        summary="Run a single-layer QAOA-style circuit for a small Max-Cut problem and compare expected cut quality.",
        category="optimization",
        qubits=3,
        default_shots=2048,
        parameter_defaults={"gamma": 0.9, "beta": 0.35},
    ),
    "h2_vqe_mini": ExperimentDefinition(
        experiment_id="h2_vqe_mini",
        title="H2 VQE Mini Workflow",
        summary="Solve a small H2-style Hamiltonian with a parameterized ansatz, exact baseline, and coarse energy sweep.",
        category="chemistry",
        qubits=2,
        default_shots=1024,
        parameter_defaults={"theta": 0.2},
    ),
}


def list_experiments() -> list[dict[str, Any]]:
    """Return all registered experiments as serializable dictionaries."""
    return [
        {
            "experiment_id": definition.experiment_id,
            "title": definition.title,
            "summary": definition.summary,
            "category": definition.category,
            "qubits": definition.qubits,
            "default_shots": definition.default_shots,
            "parameter_defaults": definition.parameter_defaults,
        }
        for definition in EXPERIMENTS.values()
    ]


def validate_circuit(
    circuit: QuantumCircuit, definition: ExperimentDefinition
) -> dict[str, Any]:
    """Validate a constructed circuit against its experiment definition.

    Checks qubit count, measurement count, circuit depth, and gate presence
    to catch construction errors before submission to a backend.

    Args:
        circuit: The Qiskit QuantumCircuit to validate.
        definition: The experiment definition to validate against.

    Returns:
        A dict with 'valid' (bool) and optional 'reason' (str) on failure.
    """
    if circuit.num_qubits != definition.qubits:
        return {
            "valid": False,
            "reason": f"Expected {definition.qubits} qubits, circuit has {circuit.num_qubits}",
        }

    ops = circuit.count_ops()
    measure_count = int(ops.get("measure", 0))
    if measure_count == 0:
        return {
            "valid": False,
            "reason": "Circuit has no measurement gates; results cannot be extracted",
        }

    if circuit.depth() == 0:
        return {
            "valid": False,
            "reason": "Circuit depth is zero; no operations present",
        }

    if circuit.size() < 2:
        return {
            "valid": False,
            "reason": f"Circuit has only {circuit.size()} operation(s); expected at least 2",
        }

    logger.debug(
        "circuit validation passed",
        extra={
            "experiment_id": definition.experiment_id,
            "qubits": circuit.num_qubits,
            "depth": circuit.depth(),
            "measurements": measure_count,
        },
    )
    return {"valid": True}


def build_experiment(
    experiment_id: str, parameters: dict[str, float] | None = None
) -> tuple[QuantumCircuit, ExperimentDefinition]:
    """Build a Qiskit QuantumCircuit for the given experiment.

    Args:
        experiment_id: Registered experiment identifier.
        parameters: Optional parameter overrides (e.g., gamma, beta, theta).

    Returns:
        Tuple of (constructed circuit, experiment definition).

    Raises:
        KeyError: If experiment_id is not registered.
        ValueError: If parameters are invalid (e.g., non-finite).
    """
    if experiment_id not in EXPERIMENTS:
        raise KeyError(f"Unknown experiment_id: {experiment_id}")

    definition = EXPERIMENTS[experiment_id]
    params = dict(definition.parameter_defaults)
    if parameters:
        params.update(parameters)

    if experiment_id == "bell_pair":
        circuit = _build_bell_pair()
    elif experiment_id == "ghz_three":
        circuit = _build_ghz_three()
    elif experiment_id == "qaoa_triangle":
        circuit = _build_qaoa_triangle(params["gamma"], params["beta"])
    elif experiment_id == "h2_vqe_mini":
        circuit = _build_h2_vqe_mini(params["theta"])
    else:
        raise KeyError(f"Unsupported experiment_id: {experiment_id}")

    return circuit, definition


def build_braket_experiment(
    experiment_id: str, parameters: dict[str, float] | None = None
) -> tuple[BraketCircuit, ExperimentDefinition]:
    """Build an Amazon Braket Circuit for the given experiment.

    Args:
        experiment_id: Registered experiment identifier.
        parameters: Optional parameter overrides.

    Returns:
        Tuple of (constructed Braket circuit, experiment definition).

    Raises:
        KeyError: If experiment_id is not registered.
        ValueError: If parameters are invalid.
    """
    if experiment_id not in EXPERIMENTS:
        raise KeyError(f"Unknown experiment_id: {experiment_id}")

    definition = EXPERIMENTS[experiment_id]
    params = dict(definition.parameter_defaults)
    if parameters:
        params.update(parameters)

    if experiment_id == "bell_pair":
        circuit = BraketCircuit().h(0).cnot(0, 1)
    elif experiment_id == "ghz_three":
        circuit = BraketCircuit().h(0).cnot(0, 1).cnot(1, 2)
    elif experiment_id == "qaoa_triangle":
        circuit = _build_braket_qaoa_triangle(params["gamma"], params["beta"])
    elif experiment_id == "h2_vqe_mini":
        circuit = _build_braket_h2_vqe_mini(params["theta"])
    else:
        raise KeyError(f"Unsupported experiment_id: {experiment_id}")

    return circuit, definition


def analyze_counts(experiment_id: str, counts: dict[str, int]) -> dict[str, Any]:
    """Analyze measurement counts for a specific experiment.

    Computes experiment-specific metrics (entanglement signal, GHZ signal,
    average cut score, or H2 energy estimate) along with general distribution
    statistics and dominant state rankings.

    Args:
        experiment_id: The experiment whose metric logic to apply.
        counts: Mapping of bitstring outcomes to their observed counts.

    Returns:
        Analysis dict with total_shots, dominant_states, distribution,
        and experiment-specific metric fields.

    Raises:
        ValueError: If counts is empty or total shot count is not positive.
    """
    if not counts:
        raise ValueError("counts must be a non-empty dictionary")
    total_shots = sum(counts.values())
    if total_shots <= 0:
        raise ValueError("total shot count must be positive")
    dominant = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:6]
    normalized = {
        state: round(value / total_shots, 4) if total_shots else 0.0
        for state, value in sorted(counts.items())
    }
    analysis: dict[str, Any] = {
        "total_shots": total_shots,
        "dominant_states": [
            {"state": state, "count": count} for state, count in dominant
        ],
        "distribution": normalized,
    }

    if experiment_id == "bell_pair":
        signal = _state_mass(counts, ["00", "11"])
        analysis.update(
            {
                "metric_name": "entanglement_signal",
                "metric_value": round(signal, 4),
                "metric_summary": "Probability mass on correlated Bell outcomes (00, 11).",
            }
        )
    elif experiment_id == "ghz_three":
        signal = _state_mass(counts, ["000", "111"])
        analysis.update(
            {
                "metric_name": "ghz_signal",
                "metric_value": round(signal, 4),
                "metric_summary": "Probability mass on GHZ outcomes (000, 111).",
            }
        )
    elif experiment_id == "qaoa_triangle":
        expected_cut = _average_cut_score(counts)
        analysis.update(
            {
                "metric_name": "avg_cut_score",
                "metric_value": round(expected_cut, 4),
                "metric_summary": "Average cut value for a triangle Max-Cut problem under sampled bitstrings.",
                "best_states": [
                    state for state in sorted(counts) if _triangle_cut_score(state) == 2
                ],
            }
        )
    elif experiment_id == "h2_vqe_mini":
        energy_summary = estimate_h2_energy_from_counts(counts)
        analysis.update(
            {
                "metric_name": "estimated_h2_energy",
                "metric_value": round(energy_summary["energy"], 4),
                "metric_summary": "Estimated expectation value for a small H2-style Hamiltonian from sampled bitstrings.",
                "reference_ground_energy": round(
                    energy_summary["reference_ground_energy"], 4
                ),
                "energy_error": round(energy_summary["energy_error"], 4),
            }
        )

    return analysis


def circuit_summary(circuit: QuantumCircuit) -> dict[str, Any]:
    """Return a serializable summary of a Qiskit circuit's structure and gate counts."""
    operations = circuit.count_ops()
    return {
        "name": circuit.name,
        "qubits": circuit.num_qubits,
        "clbits": circuit.num_clbits,
        "depth": circuit.depth(),
        "size": circuit.size(),
        "two_qubit_gates": int(
            operations.get("cx", 0) + operations.get("cz", 0) + operations.get("ecr", 0)
        ),
        "measurements": int(operations.get("measure", 0)),
        "ops": {key: int(value) for key, value in operations.items()},
    }


def braket_circuit_summary(circuit: BraketCircuit) -> dict[str, Any]:
    """Return a serializable summary of a Braket circuit's structure and gate counts."""
    instructions = circuit.instructions
    return {
        "name": "braket_circuit",
        "qubits": circuit.qubit_count,
        "clbits": 0,
        "depth": len(instructions),
        "size": len(instructions),
        "two_qubit_gates": sum(
            1 for instruction in instructions if len(instruction.target) == 2
        ),
        "measurements": 0,
        "ops": _count_braket_ops(instructions),
    }


def _build_bell_pair() -> QuantumCircuit:
    circuit = QuantumCircuit(2, 2, name="bell_pair")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def _build_ghz_three() -> QuantumCircuit:
    circuit = QuantumCircuit(3, 3, name="ghz_three")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.cx(1, 2)
    circuit.measure([0, 1, 2], [0, 1, 2])
    return circuit


def _build_qaoa_triangle(gamma: float, beta: float) -> QuantumCircuit:
    if not (isfinite(gamma) and isfinite(beta)):
        raise ValueError("gamma and beta must be finite")

    circuit = QuantumCircuit(3, 3, name="qaoa_triangle")
    edges = [(0, 1), (1, 2), (0, 2)]
    circuit.h(range(3))
    for control, target in edges:
        circuit.cx(control, target)
        circuit.rz(2 * gamma, target)
        circuit.cx(control, target)
    for qubit in range(3):
        circuit.rx(2 * beta, qubit)
    circuit.measure([0, 1, 2], [0, 1, 2])
    return circuit


def _build_h2_vqe_mini(theta: float) -> QuantumCircuit:
    if not isfinite(theta):
        raise ValueError("theta must be finite")
    circuit = QuantumCircuit(2, 2, name="h2_vqe_mini")
    circuit.ry(theta, 0)
    circuit.cx(0, 1)
    circuit.ry(-theta, 1)
    circuit.measure([0, 1], [0, 1])
    return circuit


def _build_braket_qaoa_triangle(gamma: float, beta: float) -> BraketCircuit:
    if not (isfinite(gamma) and isfinite(beta)):
        raise ValueError("gamma and beta must be finite")

    circuit = BraketCircuit().h(range(3))
    edges = [(0, 1), (1, 2), (0, 2)]
    for control, target in edges:
        circuit.cnot(control, target).rz(target, 2 * gamma).cnot(control, target)
    for qubit in range(3):
        circuit.rx(qubit, 2 * beta)
    return circuit


def _build_braket_h2_vqe_mini(theta: float) -> BraketCircuit:
    if not isfinite(theta):
        raise ValueError("theta must be finite")
    return BraketCircuit().ry(0, theta).cnot(0, 1).ry(1, -theta)


def _state_mass(counts: dict[str, int], target_states: list[str]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return sum(counts.get(state, 0) for state in target_states) / total


def _triangle_cut_score(state: str) -> int:
    bits = [int(bit) for bit in state]
    edges = [(0, 1), (1, 2), (0, 2)]
    return sum(1 for a, b in edges if bits[a] != bits[b])


def _average_cut_score(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    weighted = sum(
        _triangle_cut_score(state) * count for state, count in counts.items()
    )
    return weighted / total


def h2_reference_hamiltonian() -> SparsePauliOp:
    """Return the simplified H2 Hamiltonian as a SparsePauliOp."""
    return SparsePauliOp.from_list(
        [
            ("II", -1.05),
            ("ZI", 0.39),
            ("IZ", -0.39),
            ("XX", 0.18),
        ]
    )


def estimate_h2_energy_from_counts(counts: dict[str, int]) -> dict[str, float]:
    """Estimate the H2 ground-state energy from Z-basis measurement counts."""
    total = sum(counts.values()) or 1
    probs = {state: value / total for state, value in counts.items()}
    z0 = 0.0
    z1 = 0.0
    for state, prob in probs.items():
        bits = [int(bit) for bit in state]
        z0 += (1 if bits[0] == 0 else -1) * prob
        z1 += (1 if bits[1] == 0 else -1) * prob
    # XX cannot be recovered exactly from Z-basis counts; keep it explicit as an approximation gap.
    approx_xx = 0.0
    energy = -1.05 + 0.39 * z0 - 0.39 * z1 + 0.18 * approx_xx
    reference = exact_h2_ground_energy()
    return {
        "energy": float(energy),
        "reference_ground_energy": float(reference),
        "energy_error": float(energy - reference),
    }


def exact_h2_ground_energy() -> float:
    """Compute the exact ground-state energy of the H2 reference Hamiltonian via diagonalization."""
    hamiltonian = h2_reference_hamiltonian()
    eigenvalues = np.linalg.eigvalsh(hamiltonian.to_matrix())
    return float(eigenvalues.min().real)


def evaluate_h2_theta(theta: float) -> dict[str, float]:
    """Evaluate the H2 ansatz at a given theta using exact statevector simulation."""
    hamiltonian = h2_reference_hamiltonian()
    param = Parameter("theta")
    ansatz = QuantumCircuit(2)
    ansatz.ry(param, 0)
    ansatz.cx(0, 1)
    ansatz.ry(-param, 1)
    bound = ansatz.assign_parameters({param: theta})
    state = Statevector.from_instruction(bound)
    energy = float(state.expectation_value(hamiltonian).real)
    reference = exact_h2_ground_energy()
    return {
        "theta": float(theta),
        "energy": energy,
        "error": float(energy - reference),
    }


def h2_theta_sweep(samples: int = 21) -> dict[str, Any]:
    """Sweep theta across [-pi, pi] and return energies with the best variational angle."""
    if samples < 3:
        samples = 3
    thetas = [(-pi + (2 * pi * idx / (samples - 1))) for idx in range(samples)]
    evaluations = [evaluate_h2_theta(theta) for theta in thetas]
    best = min(evaluations, key=lambda item: item["energy"])
    return {
        "reference_ground_energy": exact_h2_ground_energy(),
        "best": best,
        "evaluations": evaluations,
    }


def _count_braket_ops(instructions: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for instruction in instructions:
        name = instruction.operator.name.lower()
        counts[name] = counts.get(name, 0) + 1
    return counts
