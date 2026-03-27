"""Quantum runtime layer for circuit execution on local simulators and real hardware.

Provides execution paths for IBM Quantum Runtime and Amazon Braket backends,
run history tracking, evidence scorecard generation, and backend posture reporting.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from braket.aws import AwsDevice, AwsDeviceType, AwsQuantumTask, AwsSession
from braket.devices import LocalSimulator as BraketLocalSimulator
from qiskit.primitives import StatevectorSampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
from qiskit_ibm_runtime.options import SamplerOptions

from .experiments import (
    analyze_counts,
    braket_circuit_summary,
    build_braket_experiment,
    build_experiment,
    circuit_summary,
    exact_h2_ground_energy,
    h2_theta_sweep,
    list_experiments,
    validate_circuit,
)
from .store import RunStore


logger = logging.getLogger("quantum_workbench.runtime")

ROOT_DIR = Path(__file__).resolve().parents[2]
STORE = RunStore(ROOT_DIR / "artifacts" / "run_history.json")


# ---------------------------------------------------------------------------
# Error recovery metrics
# ---------------------------------------------------------------------------


@dataclass
class _ErrorMetrics:
    """Tracks error counts by category for observability."""

    backend_failures: int = 0
    circuit_validation_errors: int = 0
    provider_api_errors: int = 0
    result_extraction_errors: int = 0
    _details: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self, category: str, error: Exception, context: dict[str, Any] | None = None
    ) -> None:
        """Record an error occurrence with optional context."""
        entry = {
            "category": category,
            "error_type": type(error).__name__,
            "message": str(error),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if context:
            entry["context"] = context
        self._details.append(entry)
        if category == "backend_failure":
            self.backend_failures += 1
        elif category == "circuit_validation":
            self.circuit_validation_errors += 1
        elif category == "provider_api":
            self.provider_api_errors += 1
        elif category == "result_extraction":
            self.result_extraction_errors += 1

    def summary(self) -> dict[str, Any]:
        """Return a summary of accumulated error metrics."""
        return {
            "backend_failures": self.backend_failures,
            "circuit_validation_errors": self.circuit_validation_errors,
            "provider_api_errors": self.provider_api_errors,
            "result_extraction_errors": self.result_extraction_errors,
            "recent_errors": self._details[-10:],
        }


ERROR_METRICS = _ErrorMetrics()


def get_error_metrics() -> dict[str, Any]:
    """Return current error recovery metrics for observability."""
    return ERROR_METRICS.summary()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def runtime_brief() -> dict[str, Any]:
    """Return a summary of the runtime environment, available experiments, and hardware posture."""
    token_configured = bool(os.getenv("IBM_QUANTUM_TOKEN"))
    aws_configured = bool(
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_PROFILE")
        or os.getenv("AWS_SESSION_TOKEN")
    )
    logger.info(
        "runtime_brief requested",
        extra={"ibm_configured": token_configured, "aws_configured": aws_configured},
    )
    return {
        "service": "quantum-workbench",
        "mode": "hardware-ready"
        if token_configured or aws_configured
        else "local-review",
        "summary": (
            "Local simulators plus real-backend submission paths are available."
            if token_configured or aws_configured
            else "Local simulators are available. Real hardware submission activates when IBM_QUANTUM_TOKEN or AWS credentials are configured."
        ),
        "hardware_support": {
            "ibm_quantum": {
                "provider": "IBM Quantum Runtime",
                "token_configured": token_configured,
                "channel": os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform"),
            },
            "aws_braket": {
                "provider": "Amazon Braket",
                "credentials_configured": aws_configured,
                "region": os.getenv("AWS_DEFAULT_REGION")
                or os.getenv("AWS_REGION")
                or "unset",
                "s3_bucket": os.getenv("AMZN_BRAKET_BUCKET") or "auto/default-bucket",
            },
        },
        "experiments": list_experiments(),
        "review_path": [
            "/api/runtime/brief",
            "POST /api/runs/local",
            "POST /api/runs/braket-local",
            "/api/runs",
            "POST /api/runs/hardware",
            "POST /api/runs/braket-hardware",
        ],
    }


def list_available_backends() -> dict[str, Any]:
    """List all available backends across IBM Quantum and Amazon Braket."""
    return {
        "ibm_quantum": _list_ibm_backends(),
        "aws_braket": _list_braket_backends(),
    }


def run_local(
    experiment_id: str, shots: int, parameters: dict[str, float] | None = None
) -> dict[str, Any]:
    """Execute an experiment on the local Qiskit StatevectorSampler.

    Args:
        experiment_id: Registered experiment identifier.
        shots: Number of measurement shots (must be positive).
        parameters: Optional parameter overrides for the circuit.

    Returns:
        Run record with counts, circuit summary, and analysis.

    Raises:
        KeyError: If experiment_id is not registered.
        ValueError: If shots is not positive or circuit validation fails.
    """
    if shots <= 0:
        raise ValueError("shots must be a positive integer")
    circuit, definition = build_experiment(experiment_id, parameters)

    validation = validate_circuit(circuit, definition)
    if not validation["valid"]:
        ERROR_METRICS.record(
            "circuit_validation",
            ValueError(validation["reason"]),
            {"experiment_id": experiment_id},
        )
        raise ValueError(f"Circuit validation failed: {validation['reason']}")

    logger.info(
        "executing local run",
        extra={
            "experiment_id": experiment_id,
            "shots": shots,
            "backend": "statevector-sampler",
        },
    )
    start_time = time.monotonic()
    sampler = StatevectorSampler(default_shots=shots)
    job = sampler.run([circuit])
    pub_result = job.result()[0]
    counts = _extract_counts(pub_result)
    elapsed = round(time.monotonic() - start_time, 4)

    record = _base_record(
        experiment_id=experiment_id,
        mode="local",
        shots=shots,
        backend_name="statevector-sampler",
        parameters=parameters or definition.parameter_defaults,
        status="completed",
    )
    record["counts"] = counts
    record["circuit"] = circuit_summary(circuit)
    record["analysis"] = analyze_counts(experiment_id, counts)
    record["provider"] = {
        "name": "qiskit.primitives.StatevectorSampler",
        "hardware": False,
    }
    record["execution_time_seconds"] = elapsed

    logger.info(
        "local run completed",
        extra={
            "experiment_id": experiment_id,
            "run_id": record["run_id"],
            "elapsed_s": elapsed,
        },
    )
    return STORE.upsert_run(record)


def run_braket_local(
    experiment_id: str, shots: int, parameters: dict[str, float] | None = None
) -> dict[str, Any]:
    """Execute an experiment on the Amazon Braket local simulator.

    Args:
        experiment_id: Registered experiment identifier.
        shots: Number of measurement shots (must be positive).
        parameters: Optional parameter overrides for the circuit.

    Returns:
        Run record with counts, circuit summary, and analysis.

    Raises:
        KeyError: If experiment_id is not registered.
        ValueError: If shots is not positive.
    """
    if shots <= 0:
        raise ValueError("shots must be a positive integer")
    circuit, definition = build_braket_experiment(experiment_id, parameters)

    logger.info(
        "executing braket local run",
        extra={
            "experiment_id": experiment_id,
            "shots": shots,
            "backend": "amazon-braket-local-simulator",
        },
    )
    start_time = time.monotonic()
    result = BraketLocalSimulator().run(circuit, shots=shots).result()
    counts = {
        str(state): int(value) for state, value in result.measurement_counts.items()
    }
    elapsed = round(time.monotonic() - start_time, 4)

    record = _base_record(
        experiment_id=experiment_id,
        mode="braket-local",
        shots=shots,
        backend_name="amazon-braket-local-simulator",
        parameters=parameters or definition.parameter_defaults,
        status="completed",
    )
    record["counts"] = counts
    record["circuit"] = braket_circuit_summary(circuit)
    record["analysis"] = analyze_counts(experiment_id, counts)
    record["provider"] = {"name": "Amazon Braket LocalSimulator", "hardware": False}
    record["execution_time_seconds"] = elapsed

    logger.info(
        "braket local run completed",
        extra={
            "experiment_id": experiment_id,
            "run_id": record["run_id"],
            "elapsed_s": elapsed,
        },
    )
    return STORE.upsert_run(record)


def submit_hardware(
    experiment_id: str,
    shots: int,
    backend_name: str | None = None,
    parameters: dict[str, float] | None = None,
    options_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit an experiment to IBM Quantum hardware.

    Args:
        experiment_id: Registered experiment identifier.
        shots: Number of measurement shots.
        backend_name: Specific IBM backend name, or None for least-busy selection.
        parameters: Optional parameter overrides for the circuit.
        options_payload: Optional IBM sampler options (twirling, DD, etc.).

    Returns:
        Run record with submission status and job metadata.

    Raises:
        KeyError: If experiment_id is not registered.
        RuntimeError: If IBM_QUANTUM_TOKEN is not configured.
        ValueError: If circuit validation fails.
    """
    service = _build_service()
    if service is None:
        raise RuntimeError("IBM_QUANTUM_TOKEN is not configured.")

    circuit, definition = build_experiment(experiment_id, parameters)

    validation = validate_circuit(circuit, definition)
    if not validation["valid"]:
        ERROR_METRICS.record(
            "circuit_validation",
            ValueError(validation["reason"]),
            {"experiment_id": experiment_id},
        )
        raise ValueError(f"Circuit validation failed: {validation['reason']}")

    logger.info(
        "submitting to IBM hardware",
        extra={
            "experiment_id": experiment_id,
            "shots": shots,
            "backend_name": backend_name,
        },
    )

    backend = _select_backend(service, backend_name, definition.qubits)
    pass_manager = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa_circuit = pass_manager.run(circuit)
    sampler = SamplerV2(
        mode=backend, options=_build_ibm_sampler_options(shots, options_payload)
    )
    job = sampler.run([isa_circuit], shots=shots)

    resolved_backend = _backend_name(backend)
    logger.info(
        "IBM hardware job submitted",
        extra={
            "experiment_id": experiment_id,
            "backend": resolved_backend,
            "job_id": job.job_id(),
        },
    )

    record = _base_record(
        experiment_id=experiment_id,
        mode="hardware",
        shots=shots,
        backend_name=resolved_backend,
        parameters=parameters or definition.parameter_defaults,
        status="submitted",
    )
    record["circuit"] = circuit_summary(isa_circuit)
    record["provider"] = {
        "name": "IBM Quantum Runtime",
        "hardware": True,
        "channel": os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform"),
    }
    record["ibm_options"] = options_payload or {}
    record["hardware_job"] = {
        "job_id": job.job_id(),
        "status": "submitted",
    }
    return STORE.upsert_run(record)


def submit_braket_hardware(
    experiment_id: str,
    shots: int,
    backend_arn: str | None = None,
    parameters: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Submit an experiment to Amazon Braket QPU hardware.

    Args:
        experiment_id: Registered experiment identifier.
        shots: Number of measurement shots.
        backend_arn: Specific Braket device ARN, or None for auto-selection.
        parameters: Optional parameter overrides for the circuit.

    Returns:
        Run record with submission status and task metadata.

    Raises:
        KeyError: If experiment_id is not registered.
        RuntimeError: If AWS credentials are not configured or no QPU is available.
    """
    session = _build_braket_session()
    if session is None:
        raise RuntimeError("AWS credentials are not configured for Amazon Braket.")

    circuit, definition = build_braket_experiment(experiment_id, parameters)

    logger.info(
        "submitting to Braket hardware",
        extra={
            "experiment_id": experiment_id,
            "shots": shots,
            "backend_arn": backend_arn,
        },
    )

    device = _select_braket_backend(session, backend_arn)
    bucket = os.getenv("AMZN_BRAKET_BUCKET") or session.default_bucket()
    prefix = os.getenv("AMZN_BRAKET_PREFIX", "quantum-workbench")
    task = device.run(circuit, s3_destination_folder=(bucket, prefix), shots=shots)

    resolved_backend = _backend_name(device)
    logger.info(
        "Braket hardware task submitted",
        extra={
            "experiment_id": experiment_id,
            "backend": resolved_backend,
            "task_id": task.id,
        },
    )

    record = _base_record(
        experiment_id=experiment_id,
        mode="braket-hardware",
        shots=shots,
        backend_name=resolved_backend,
        parameters=parameters or definition.parameter_defaults,
        status="submitted",
    )
    record["circuit"] = braket_circuit_summary(circuit)
    record["provider"] = {
        "name": "Amazon Braket",
        "hardware": True,
        "provider_name": getattr(device, "provider_name", None),
    }
    record["hardware_job"] = {
        "job_id": task.id,
        "status": "submitted",
        "s3_destination": {"bucket": bucket, "prefix": prefix},
    }
    return STORE.upsert_run(record)


def refresh_run(run_id: str) -> dict[str, Any] | None:
    """Refresh the status of a previously submitted run.

    Polls the provider API (IBM or Braket) to update job status, and extracts
    results when the job has completed.

    Args:
        run_id: The unique run identifier to refresh.

    Returns:
        Updated run record, or None if run_id is not found.
    """
    record = STORE.get_run(run_id)
    if record is None:
        return None

    if record.get("mode") == "braket-hardware":
        return _refresh_braket_run(record)
    if record.get("mode") != "hardware":
        return record

    hardware_job = record.get("hardware_job") or {}
    if not hardware_job.get("job_id"):
        return record

    if record.get("status") in {"completed", "failed", "cancelled"}:
        return record

    service = _build_service()
    if service is None:
        record["status"] = "blocked"
        record["hardware_job"]["status"] = "token_missing"
        record["updated_at"] = _utc_now()
        return STORE.upsert_run(record)

    try:
        job = service.job(hardware_job["job_id"])
        status_value = getattr(job.status(), "name", str(job.status()))
        record["hardware_job"]["status"] = status_value.lower()

        job_done = bool(getattr(job, "done", lambda: False)())
        if job_done or status_value.upper() == "DONE":
            pub_result = job.result()[0]
            counts = _extract_counts(pub_result)
            record["counts"] = counts
            record["analysis"] = analyze_counts(record["experiment_id"], counts)
            record["usage"] = _extract_ibm_usage(job)
            record["status"] = "completed"
            logger.info(
                "IBM hardware run completed",
                extra={"run_id": run_id, "job_id": hardware_job["job_id"]},
            )
        elif status_value.upper() in {"ERROR", "CANCELLED"}:
            record["status"] = "failed"
            logger.warning(
                "IBM hardware run failed",
                extra={
                    "run_id": run_id,
                    "job_id": hardware_job["job_id"],
                    "status": status_value,
                },
            )
        else:
            record["status"] = "running"
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        ERROR_METRICS.record("provider_api", exc, {"run_id": run_id, "provider": "ibm"})
        logger.warning(
            "failed to refresh IBM job",
            extra={
                "run_id": run_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        record["hardware_job"]["status"] = "provider_error"
        record["status"] = "submitted"
        record["warning"] = f"Could not refresh job yet: {exc}"

    record["updated_at"] = _utc_now()
    return STORE.upsert_run(record)


def review_pack() -> dict[str, Any]:
    """Generate a experiment summary.

    Returns a structured summary including recent runs, evidence scorecard,
    IBM usage data, and explanatory context.
    """
    latest_runs = STORE.list_runs()[:5]
    return {
        "service": "quantum-workbench",
        "why_it_matters": [
            "It shows foundational quantum circuits and a small optimization workflow in one product surface.",
            "It also includes a chemistry-style VQE mini workflow so the repo demonstrates a domain problem rather than only abstract circuits.",
            "It separates ideal local execution from real hardware execution instead of hiding backend differences.",
            "It keeps run history, backend posture, local-stack comparisons, and experiment summaries reviewable through APIs and UI.",
        ],
        "experiments": list_experiments(),
        "proof_sequence": [
            "/api/runtime/brief",
            "/api/evidence/scorecard",
            "/api/ibm/proof-pack",
            "/api/domain/h2-vqe-pack",
            "POST /api/runs/local",
            "POST /api/compare/local-backends",
            "/api/runs",
            "POST /api/runs/hardware",
        ],
        "latest_runs": latest_runs,
        "evidence_scorecard": evidence_scorecard(),
        "ibm_usage_summary": ibm_usage_summary(),
    }


def list_runs() -> list[dict[str, Any]]:
    """Return all run records, most recent first."""
    return STORE.list_runs()


def evidence_scorecard() -> dict[str, Any]:
    """Build an evidence scorecard showing per-experiment execution coverage.

    Maps each experiment against local and hardware execution paths,
    tracking completion status and metric deltas across backends.
    """
    runs = STORE.list_runs()
    latest_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for run in runs:
        key = (run["experiment_id"], run["mode"])
        if key not in latest_by_key:
            latest_by_key[key] = run

    experiment_rows = []
    for experiment in list_experiments():
        experiment_id = experiment["experiment_id"]
        qiskit_local = latest_by_key.get((experiment_id, "local"))
        braket_local = latest_by_key.get((experiment_id, "braket-local"))
        ibm_hardware = latest_by_key.get((experiment_id, "hardware"))
        braket_hardware = latest_by_key.get((experiment_id, "braket-hardware"))

        row = {
            "experiment_id": experiment_id,
            "title": experiment["title"],
            "category": experiment["category"],
            "qiskit_local": _scorecard_entry(qiskit_local),
            "braket_local": _scorecard_entry(braket_local),
            "ibm_hardware": _scorecard_entry(ibm_hardware),
            "braket_hardware": _scorecard_entry(braket_hardware),
        }
        if qiskit_local and braket_local:
            q_metric = qiskit_local.get("analysis", {}).get("metric_value")
            b_metric = braket_local.get("analysis", {}).get("metric_value")
            if isinstance(q_metric, (int, float)) and isinstance(
                b_metric, (int, float)
            ):
                row["local_metric_delta"] = round(float(q_metric) - float(b_metric), 4)
        experiment_rows.append(row)

    hardware_count = sum(
        1
        for run in runs
        if run.get("mode") in {"hardware", "braket-hardware"}
        and run.get("status") == "completed"
    )
    return {
        "summary": {
            "total_runs": len(runs),
            "completed_hardware_runs": hardware_count,
            "completed_local_runs": sum(
                1
                for run in runs
                if run.get("mode") in {"local", "braket-local"}
                and run.get("status") == "completed"
            ),
        },
        "experiments": experiment_rows,
    }


def ibm_usage_summary() -> dict[str, Any]:
    """Summarize IBM Quantum hardware usage across completed runs.

    Returns total quantum seconds consumed, per-run breakdowns, and
    timing metadata from the IBM Runtime API.
    """
    runs = [
        run
        for run in STORE.list_runs()
        if run.get("mode") == "hardware" and run.get("status") == "completed"
    ]
    total_quantum_seconds = 0.0
    records = []
    for run in runs:
        usage = run.get("usage") or {}
        q_seconds = float(usage.get("quantum_seconds") or 0.0)
        total_quantum_seconds += q_seconds
        records.append(
            {
                "run_id": run["run_id"],
                "experiment_id": run["experiment_id"],
                "backend_name": run["backend_name"],
                "quantum_seconds": q_seconds,
                "usage_estimation_quantum_seconds": usage.get(
                    "usage_estimation_quantum_seconds"
                ),
                "timestamps": usage.get("timestamps"),
                "ibm_options": run.get("ibm_options", {}),
            }
        )
    return {
        "completed_runs": len(runs),
        "total_quantum_seconds": round(total_quantum_seconds, 4),
        "records": records,
    }


def ibm_backend_report(
    backend_name: str, experiment_id: str, parameters: dict[str, float] | None = None
) -> dict[str, Any]:
    """Generate a detailed backend report for a specific IBM Quantum device.

    Transpiles the experiment circuit for the target backend and reports
    circuit inflation, basis gates, coupling topology, and queue posture.

    Args:
        backend_name: IBM backend identifier (e.g., 'ibm_torino').
        experiment_id: Registered experiment to transpile.
        parameters: Optional parameter overrides.

    Returns:
        Backend metadata, transpilation summary, and optimization analysis.

    Raises:
        RuntimeError: If IBM_QUANTUM_TOKEN is not configured.
        KeyError: If experiment_id is not registered.
    """
    service = _build_service()
    if service is None:
        raise RuntimeError("IBM_QUANTUM_TOKEN is not configured.")

    logger.info(
        "generating IBM backend report",
        extra={"backend_name": backend_name, "experiment_id": experiment_id},
    )

    circuit, definition = build_experiment(experiment_id, parameters)
    backend = service.backend(backend_name)
    pass_manager = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa_circuit = pass_manager.run(circuit)
    return {
        "backend_name": _backend_name(backend),
        "experiment_id": experiment_id,
        "original_circuit": circuit_summary(circuit),
        "isa_circuit": circuit_summary(isa_circuit),
        "target": {
            "num_qubits": getattr(backend, "num_qubits", None),
            "basis_gates": list(getattr(backend, "operation_names", [])),
            "coupling_edges": len(backend.coupling_map.get_edges())
            if getattr(backend, "coupling_map", None)
            else None,
            "dt": getattr(backend.target, "dt", None),
            "pending_jobs": getattr(
                getattr(backend, "status", lambda: None)(), "pending_jobs", None
            ),
        },
        "optimization_summary": {
            "depth_delta": isa_circuit.depth() - circuit.depth(),
            "two_qubit_delta": circuit_summary(isa_circuit)["two_qubit_gates"]
            - circuit_summary(circuit)["two_qubit_gates"],
            "why_it_matters": (
                "Backend-aware transpilation makes the hardware constraints visible before any job is submitted."
            ),
        },
        "shots_recommendation": min(256, max(64, definition.default_shots // 4)),
    }


def ibm_proof_pack(backend_name: str = "ibm_torino") -> dict[str, Any]:
    """Generate a comprehensive IBM proof pack for hardware verification.

    Combines backend report, completed run history, scorecard summary,
    and usage data into a single consolidated package.

    Args:
        backend_name: IBM backend to report on (default: ibm_torino).

    Returns:
        Structured proof pack with hardware evidence.

    Raises:
        RuntimeError: If IBM_QUANTUM_TOKEN is not configured.
    """
    scorecard = evidence_scorecard()
    latest_ibm_runs = [
        run
        for run in STORE.list_runs()
        if run.get("mode") == "hardware" and run.get("status") == "completed"
    ][:6]
    report = ibm_backend_report(backend_name=backend_name, experiment_id="bell_pair")
    return {
        "service": "quantum-workbench",
        "provider": "IBM Quantum Runtime",
        "backend_report": report,
        "completed_ibm_runs": latest_ibm_runs,
        "scorecard_summary": scorecard["summary"],
        "ibm_usage_summary": ibm_usage_summary(),
        "why_it_matters": [
            "Real hardware results are paired with transpilation and backend metadata.",
            "The system exposes queue posture, basis gates, circuit inflation, usage timing, and measured outcomes in one consolidated pack.",
            "This reads more like backend product work than a one-off notebook execution.",
        ],
    }


def h2_vqe_pack() -> dict[str, Any]:
    """Generate the H2 VQE chemistry domain pack.

    Runs a theta parameter sweep against an H2-style Hamiltonian,
    identifies the best variational angle, and includes recent chemistry runs.

    Returns:
        Domain pack with sweep data, best parameters, and reference energies.
    """
    sweep = h2_theta_sweep(samples=21)
    chemistry_runs = [
        run for run in STORE.list_runs() if run.get("experiment_id") == "h2_vqe_mini"
    ][:6]
    return {
        "service": "quantum-workbench",
        "domain": "chemistry-mini-workflow",
        "reference_ground_energy": exact_h2_ground_energy(),
        "best_theta": sweep["best"]["theta"],
        "best_energy": sweep["best"]["energy"],
        "best_error": sweep["best"]["error"],
        "theta_sweep": sweep["evaluations"],
        "recent_runs": chemistry_runs,
        "why_it_matters": [
            "This is the missing domain layer: a chemistry-style Hamiltonian workflow instead of circuit execution alone.",
            "It proves the repo can connect quantum execution to a small scientific objective with an exact baseline.",
        ],
    }


def compare_local_backends(
    experiment_id: str, shots: int, parameters: dict[str, float] | None = None
) -> dict[str, Any]:
    """Run the same experiment on both Qiskit and Braket local simulators and compare results.

    Args:
        experiment_id: Registered experiment identifier.
        shots: Number of measurement shots.
        parameters: Optional parameter overrides.

    Returns:
        Comparison record with per-state deltas, total variation distance, and metric analysis.

    Raises:
        KeyError: If experiment_id is not registered.
        ValueError: If shots is not positive.
    """
    logger.info(
        "comparing local backends",
        extra={"experiment_id": experiment_id, "shots": shots},
    )

    qiskit_run = run_local(
        experiment_id=experiment_id, shots=shots, parameters=parameters
    )
    braket_run = run_braket_local(
        experiment_id=experiment_id, shots=shots, parameters=parameters
    )

    q_dist = qiskit_run["analysis"]["distribution"]
    b_dist = braket_run["analysis"]["distribution"]
    states = sorted(set(q_dist) | set(b_dist))
    per_state = []
    variation = 0.0
    for state in states:
        q_val = float(q_dist.get(state, 0.0))
        b_val = float(b_dist.get(state, 0.0))
        delta = round(q_val - b_val, 4)
        variation += abs(delta)
        per_state.append(
            {
                "state": state,
                "qiskit_local": q_val,
                "braket_local": b_val,
                "delta": delta,
            }
        )

    metric_name = qiskit_run["analysis"].get("metric_name")
    q_metric = qiskit_run["analysis"].get("metric_value")
    b_metric = braket_run["analysis"].get("metric_value")
    metric_delta = None
    if isinstance(q_metric, (int, float)) and isinstance(b_metric, (int, float)):
        metric_delta = round(float(q_metric) - float(b_metric), 4)

    return {
        "experiment_id": experiment_id,
        "shots": shots,
        "parameters": parameters or {},
        "comparison": {
            "metric_name": metric_name,
            "metric_delta": metric_delta,
            "total_variation_distance": round(variation / 2, 4),
            "per_state": per_state,
            "summary": _comparison_summary(experiment_id, metric_delta, variation / 2),
        },
        "runs": {
            "qiskit_local": qiskit_run,
            "braket_local": braket_run,
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_service() -> QiskitRuntimeService | None:
    """Build an IBM Quantum Runtime service client, or None if token is missing."""
    token = os.getenv("IBM_QUANTUM_TOKEN")
    if not token:
        return None
    channel = os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform")
    return QiskitRuntimeService(channel=channel, token=token)


def _build_ibm_sampler_options(
    shots: int, options_payload: dict[str, Any] | None
) -> SamplerOptions:
    """Construct IBM SamplerOptions from a shots count and optional user payload."""
    options = SamplerOptions()
    options.default_shots = shots
    if not options_payload:
        return options
    if options_payload.get("enable_dynamical_decoupling"):
        options.dynamical_decoupling.enable = True
    if options_payload.get("enable_twirling"):
        options.twirling.enable_gates = True
    meas_type = options_payload.get("meas_type")
    if meas_type:
        options.execution.meas_type = meas_type
    max_execution_time = options_payload.get("max_execution_time")
    if max_execution_time:
        options.max_execution_time = int(max_execution_time)
    job_tags = options_payload.get("job_tags")
    if job_tags:
        options.environment.job_tags = [str(tag) for tag in job_tags]
    return options


def _build_braket_session() -> AwsSession | None:
    """Build an AWS session for Braket, or None if credentials are missing."""
    if not (
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_PROFILE")
        or os.getenv("AWS_SESSION_TOKEN")
    ):
        return None
    bucket = os.getenv("AMZN_BRAKET_BUCKET")
    return AwsSession(default_bucket=bucket) if bucket else AwsSession()


def _select_backend(
    service: QiskitRuntimeService, backend_name: str | None, qubits: int
) -> Any:
    """Select an IBM backend by name, or pick the least-busy device with enough qubits."""
    if backend_name:
        return service.backend(backend_name)
    return service.least_busy(operational=True, simulator=False, min_num_qubits=qubits)


def _select_braket_backend(session: AwsSession, backend_arn: str | None) -> Any:
    """Select a Braket QPU by ARN, or pick the one with the shallowest queue."""
    if backend_arn:
        return AwsDevice(backend_arn, aws_session=session)

    devices = AwsDevice.get_devices(
        types=[AwsDeviceType.QPU],
        statuses=["ONLINE"],
        aws_session=session,
    )
    if not devices:
        raise RuntimeError("No online Amazon Braket QPU backend was found.")
    devices.sort(
        key=lambda device: (
            _safe_queue_depth(getattr(device, "queue_depth", None)),
            _backend_name(device),
        )
    )
    return devices[0]


def _backend_name(backend: Any) -> str:
    """Extract a human-readable name from a backend object."""
    name = getattr(backend, "name", None)
    if callable(name):
        return str(name())
    return str(name)


def _safe_queue_depth(queue_depth: Any) -> int:
    """Normalize queue depth to an integer, defaulting to 999999 for unknowns."""
    if isinstance(queue_depth, int):
        return queue_depth
    if isinstance(queue_depth, str):
        digits = "".join(char for char in queue_depth if char.isdigit())
        return int(digits) if digits else 999999
    return 999999


def _extract_counts(pub_result: Any) -> dict[str, int]:
    """Extract measurement counts from a Qiskit PubResult.

    Searches through known classical register names (meas, c, cr) and falls
    back to scanning all data attributes for a get_counts method.

    Raises:
        RuntimeError: If no counts can be extracted from the result.
    """
    data = pub_result.data
    for key in ("meas", "c", "cr"):
        container = getattr(data, key, None)
        if container is not None and hasattr(container, "get_counts"):
            counts = container.get_counts()
            return {str(state): int(value) for state, value in counts.items()}
    for attr in dir(data):
        if attr.startswith("_"):
            continue
        container = getattr(data, attr)
        if hasattr(container, "get_counts"):
            counts = container.get_counts()
            return {str(state): int(value) for state, value in counts.items()}
    raise RuntimeError("Could not extract counts from sampler result.")


def _list_ibm_backends() -> dict[str, Any]:
    """Query and normalize available IBM Quantum backends."""
    service = _build_service()
    if service is None:
        return {
            "configured": False,
            "backends": [],
            "message": "IBM_QUANTUM_TOKEN is not configured.",
        }

    try:
        backends = service.backends(simulator=False, operational=True)
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        ERROR_METRICS.record("backend_failure", exc, {"provider": "ibm"})
        logger.warning(
            "failed to query IBM backends",
            extra={"error_type": type(exc).__name__, "error": str(exc)},
        )
        return {
            "configured": True,
            "backends": [],
            "message": f"Could not query IBM Quantum backends: {exc}",
        }

    normalized = []
    for backend in backends:
        normalized.append(
            {
                "name": _backend_name(backend),
                "num_qubits": getattr(backend, "num_qubits", None),
                "simulator": getattr(backend, "simulator", False),
                "pending_jobs": getattr(
                    getattr(backend, "status", lambda: None)(), "pending_jobs", None
                ),
            }
        )
    normalized.sort(
        key=lambda item: (
            item["pending_jobs"] is None,
            item["pending_jobs"] or 0,
            -(item["num_qubits"] or 0),
        )
    )
    return {
        "configured": True,
        "backends": normalized[:12],
        "message": "Available IBM Quantum real hardware backends.",
    }


def _list_braket_backends() -> dict[str, Any]:
    """Query and normalize available Amazon Braket QPU backends."""
    session = _build_braket_session()
    if session is None:
        return {
            "configured": False,
            "backends": [],
            "message": "AWS credentials are not configured for Amazon Braket.",
        }
    try:
        devices = AwsDevice.get_devices(
            types=[AwsDeviceType.QPU],
            statuses=["ONLINE"],
            aws_session=session,
        )
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        ERROR_METRICS.record("backend_failure", exc, {"provider": "braket"})
        logger.warning(
            "failed to query Braket backends",
            extra={"error_type": type(exc).__name__, "error": str(exc)},
        )
        return {
            "configured": True,
            "backends": [],
            "message": f"Could not query Amazon Braket backends: {exc}",
        }

    normalized = []
    for device in devices:
        normalized.append(
            {
                "name": _backend_name(device),
                "arn": getattr(device, "arn", None),
                "provider_name": getattr(device, "provider_name", None),
                "num_qubits": getattr(device, "qubit_count", None),
                "queue_depth": getattr(device, "queue_depth", None),
            }
        )
    normalized.sort(
        key=lambda item: (_safe_queue_depth(item.get("queue_depth")), item["name"])
    )
    return {
        "configured": True,
        "backends": normalized[:12],
        "message": "Available Amazon Braket real hardware backends.",
    }


def _refresh_braket_run(record: dict[str, Any]) -> dict[str, Any]:
    """Poll Amazon Braket for updated task status and extract results on completion."""
    hardware_job = record.get("hardware_job") or {}
    if not hardware_job.get("job_id"):
        return record
    if record.get("status") in {"completed", "failed", "cancelled"}:
        return record

    session = _build_braket_session()
    if session is None:
        record["status"] = "blocked"
        record["hardware_job"]["status"] = "credentials_missing"
        record["updated_at"] = _utc_now()
        return STORE.upsert_run(record)

    try:
        task = AwsQuantumTask(hardware_job["job_id"], aws_session=session)
        state = str(task.state())
        record["hardware_job"]["status"] = state.lower()
        if state.upper() == "COMPLETED":
            result = task.result()
            counts = {
                str(bitstring): int(value)
                for bitstring, value in result.measurement_counts.items()
            }
            record["counts"] = counts
            record["analysis"] = analyze_counts(record["experiment_id"], counts)
            record["status"] = "completed"
            logger.info(
                "Braket hardware run completed",
                extra={
                    "run_id": record.get("run_id"),
                    "task_id": hardware_job["job_id"],
                },
            )
        elif state.upper() in {"FAILED", "CANCELLED"}:
            record["status"] = "failed"
            logger.warning(
                "Braket hardware run failed",
                extra={
                    "run_id": record.get("run_id"),
                    "task_id": hardware_job["job_id"],
                    "state": state,
                },
            )
        else:
            record["status"] = "running"
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        ERROR_METRICS.record(
            "provider_api", exc, {"run_id": record.get("run_id"), "provider": "braket"}
        )
        logger.warning(
            "failed to refresh Braket task",
            extra={
                "run_id": record.get("run_id"),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        record["warning"] = f"Could not refresh Braket task yet: {exc}"
    record["updated_at"] = _utc_now()
    return STORE.upsert_run(record)


def _comparison_summary(
    experiment_id: str, metric_delta: float | None, total_variation: float
) -> str:
    """Generate a human-readable summary of a local backend comparison."""
    if experiment_id in {"bell_pair", "ghz_three"}:
        closeness = (
            "closely aligned" if total_variation < 0.1 else "noticeably different"
        )
        return f"Local backends stayed {closeness} on correlated-state concentration with total variation distance {total_variation:.4f}."
    if experiment_id == "qaoa_triangle" and metric_delta is not None:
        direction = (
            "higher" if metric_delta > 0 else "lower" if metric_delta < 0 else "equal"
        )
        return f"Qiskit local cut score was {direction} than Braket local by {abs(metric_delta):.4f}, with total variation distance {total_variation:.4f}."
    return f"Local backends completed the comparison with total variation distance {total_variation:.4f}."


def _extract_ibm_usage(job: Any) -> dict[str, Any]:
    """Extract usage and timing metadata from an IBM Runtime job.

    Gracefully handles missing or unavailable metrics attributes, which
    may occur with certain IBM Runtime API versions or job states.
    """
    metrics: dict[str, Any] = {}
    try:
        metrics = job.metrics()
    except (AttributeError, RuntimeError, TypeError) as exc:
        logger.debug("could not extract IBM job metrics: %s", exc)
        metrics = {}
    usage: dict[str, Any] = {}
    try:
        usage_value = job.usage()
        usage["reported_seconds"] = usage_value
    except (AttributeError, RuntimeError, TypeError) as exc:
        logger.debug("could not extract IBM job usage: %s", exc)
    try:
        estimate = job.usage_estimation
        if isinstance(estimate, dict):
            usage["usage_estimation_quantum_seconds"] = estimate.get("quantum_seconds")
    except (AttributeError, RuntimeError, TypeError) as exc:
        logger.debug("could not extract IBM job usage estimation: %s", exc)
    if isinstance(metrics, dict):
        usage["metrics"] = metrics
        usage["timestamps"] = metrics.get("timestamps")
        if isinstance(metrics.get("usage"), dict):
            usage["quantum_seconds"] = metrics["usage"].get("quantum_seconds")
            usage["seconds"] = metrics["usage"].get("seconds")
    return usage


def _scorecard_entry(run: dict[str, Any] | None) -> dict[str, Any] | None:
    """Format a single run into a scorecard entry for the evidence grid."""
    if run is None:
        return None
    analysis = run.get("analysis") or {}
    return {
        "run_id": run.get("run_id"),
        "status": run.get("status"),
        "backend_name": run.get("backend_name"),
        "shots": run.get("shots"),
        "updated_at": run.get("updated_at"),
        "metric_name": analysis.get("metric_name"),
        "metric_value": analysis.get("metric_value"),
        "top_states": analysis.get("dominant_states", [])[:3],
        "ibm_options": run.get("ibm_options", {}),
        "usage_quantum_seconds": (run.get("usage") or {}).get("quantum_seconds"),
    }


def _base_record(
    experiment_id: str,
    mode: str,
    shots: int,
    backend_name: str,
    parameters: dict[str, float],
    status: str,
) -> dict[str, Any]:
    """Create a base run record with standard fields."""
    now = _utc_now()
    return {
        "run_id": f"qwl-{uuid4().hex[:12]}",
        "experiment_id": experiment_id,
        "mode": mode,
        "shots": shots,
        "backend_name": backend_name,
        "parameters": parameters,
        "status": status,
        "created_at": now,
        "updated_at": now,
    }


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
