"""Comprehensive tests for the Quantum Workbench API and core modules."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.quantum.experiments import (
    analyze_counts,
    build_braket_experiment,
    build_experiment,
    circuit_summary,
    estimate_h2_energy_from_counts,
    exact_h2_ground_energy,
    h2_theta_sweep,
    list_experiments,
    validate_circuit,
)
from app.quantum.runtime import (
    _backend_name,
    _base_record,
    _comparison_summary,
    _safe_queue_depth,
    _scorecard_entry,
    evidence_scorecard,
    ibm_usage_summary,
    review_pack,
    runtime_brief,
)
from app.quantum.store import RunStore


client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Circuit construction validation
# ---------------------------------------------------------------------------


class TestCircuitConstruction:
    """Validate that each experiment builds valid Qiskit and Braket circuits."""

    def test_bell_pair_circuit_has_correct_shape(self) -> None:
        circuit, definition = build_experiment("bell_pair")
        assert circuit.num_qubits == 2
        assert circuit.num_clbits == 2
        ops = circuit.count_ops()
        assert ops.get("h", 0) >= 1
        assert ops.get("cx", 0) >= 1
        assert ops.get("measure", 0) == 2

    def test_ghz_three_circuit_depth_and_gates(self) -> None:
        circuit, definition = build_experiment("ghz_three")
        assert circuit.num_qubits == 3
        assert circuit.count_ops().get("cx", 0) == 2

    def test_qaoa_triangle_requires_finite_params(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            build_experiment("qaoa_triangle", {"gamma": float("inf"), "beta": 0.5})

    def test_h2_vqe_mini_requires_finite_theta(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            build_experiment("h2_vqe_mini", {"theta": float("nan")})

    def test_unknown_experiment_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="Unknown experiment_id"):
            build_experiment("nonexistent_experiment")

    def test_braket_bell_pair_builds_successfully(self) -> None:
        circuit, definition = build_braket_experiment("bell_pair")
        assert circuit.qubit_count == 2

    def test_braket_unknown_experiment_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="Unknown experiment_id"):
            build_braket_experiment("nonexistent_experiment")

    def test_circuit_summary_returns_expected_keys(self) -> None:
        circuit, _ = build_experiment("bell_pair")
        summary = circuit_summary(circuit)
        assert "qubits" in summary
        assert "depth" in summary
        assert "two_qubit_gates" in summary
        assert summary["qubits"] == 2

    def test_validate_circuit_passes_for_valid_bell_pair(self) -> None:
        circuit, definition = build_experiment("bell_pair")
        result = validate_circuit(circuit, definition)
        assert result["valid"] is True

    def test_validate_circuit_fails_for_wrong_qubit_count(self) -> None:
        from qiskit import QuantumCircuit as QC

        circuit = QC(5, 5)
        circuit.h(0)
        circuit.measure_all()
        _, definition = build_experiment("bell_pair")
        result = validate_circuit(circuit, definition)
        assert result["valid"] is False
        assert "qubits" in result["reason"]

    def test_validate_circuit_fails_for_no_measurements(self) -> None:
        from qiskit import QuantumCircuit as QC

        circuit = QC(2)
        circuit.h(0)
        circuit.cx(0, 1)
        _, definition = build_experiment("bell_pair")
        result = validate_circuit(circuit, definition)
        assert result["valid"] is False
        assert "measurement" in result["reason"]

    def test_list_experiments_returns_all_registered(self) -> None:
        experiments = list_experiments()
        ids = {e["experiment_id"] for e in experiments}
        assert ids == {"bell_pair", "ghz_three", "qaoa_triangle", "h2_vqe_mini"}


# ---------------------------------------------------------------------------
# 2. Backend selection logic
# ---------------------------------------------------------------------------


class TestBackendSelection:
    """Verify backend selection helpers and runtime mode detection."""

    def test_runtime_brief_without_tokens_is_local_review(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            brief = runtime_brief()
            assert brief["mode"] == "local-review"
            assert brief["hardware_support"]["ibm_quantum"]["token_configured"] is False
            assert (
                brief["hardware_support"]["aws_braket"]["credentials_configured"]
                is False
            )

    def test_runtime_brief_with_ibm_token_is_hardware_ready(self) -> None:
        with patch.dict("os.environ", {"IBM_QUANTUM_TOKEN": "fake-token"}, clear=True):
            brief = runtime_brief()
            assert brief["mode"] == "hardware-ready"
            assert brief["hardware_support"]["ibm_quantum"]["token_configured"] is True

    def test_runtime_brief_with_aws_credentials_is_hardware_ready(self) -> None:
        with patch.dict("os.environ", {"AWS_PROFILE": "test-profile"}, clear=True):
            brief = runtime_brief()
            assert brief["mode"] == "hardware-ready"
            assert (
                brief["hardware_support"]["aws_braket"]["credentials_configured"]
                is True
            )

    def test_safe_queue_depth_with_int(self) -> None:
        assert _safe_queue_depth(5) == 5

    def test_safe_queue_depth_with_string(self) -> None:
        assert _safe_queue_depth("42 jobs") == 42

    def test_safe_queue_depth_with_none(self) -> None:
        assert _safe_queue_depth(None) == 999999

    def test_backend_name_callable(self) -> None:
        class FakeBackend:
            def name(self) -> str:
                return "fake_backend"

        assert _backend_name(FakeBackend()) == "fake_backend"

    def test_backend_name_attribute(self) -> None:
        class FakeBackend:
            name = "attr_backend"

        assert _backend_name(FakeBackend()) == "attr_backend"


# ---------------------------------------------------------------------------
# 3. Result parsing
# ---------------------------------------------------------------------------


class TestResultParsing:
    """Validate count analysis and energy estimation logic."""

    def test_analyze_bell_pair_counts(self) -> None:
        counts = {"00": 500, "11": 500}
        analysis = analyze_counts("bell_pair", counts)
        assert analysis["metric_name"] == "entanglement_signal"
        assert analysis["metric_value"] == pytest.approx(1.0)
        assert analysis["total_shots"] == 1000

    def test_analyze_ghz_three_counts(self) -> None:
        counts = {"000": 400, "111": 400, "010": 200}
        analysis = analyze_counts("ghz_three", counts)
        assert analysis["metric_name"] == "ghz_signal"
        assert analysis["metric_value"] == pytest.approx(0.8)

    def test_analyze_qaoa_triangle_counts(self) -> None:
        # States with cut score 2: 011, 101, 110, 001, 010, 100
        # "011" -> bits[0]=0, bits[1]=1, bits[2]=1 -> edges (0,1)=1,(1,2)=0,(0,2)=1 -> score=2
        counts = {"011": 100, "101": 100, "000": 100}
        analysis = analyze_counts("qaoa_triangle", counts)
        assert analysis["metric_name"] == "avg_cut_score"
        assert "best_states" in analysis

    def test_analyze_h2_vqe_mini_counts(self) -> None:
        counts = {"00": 800, "01": 100, "10": 50, "11": 50}
        analysis = analyze_counts("h2_vqe_mini", counts)
        assert analysis["metric_name"] == "estimated_h2_energy"
        assert "reference_ground_energy" in analysis
        assert "energy_error" in analysis

    def test_estimate_h2_energy_from_counts_returns_reference(self) -> None:
        counts = {"00": 1000}
        result = estimate_h2_energy_from_counts(counts)
        assert "energy" in result
        assert "reference_ground_energy" in result
        assert isinstance(result["energy_error"], float)

    def test_exact_h2_ground_energy_is_finite(self) -> None:
        energy = exact_h2_ground_energy()
        assert math.isfinite(energy)
        assert energy < 0  # ground state energy should be negative


# ---------------------------------------------------------------------------
# 4. Evidence / proof pack generation
# ---------------------------------------------------------------------------


class TestEvidenceGeneration:
    """Test the evidence scorecard and summary generation."""

    def test_evidence_scorecard_structure(self) -> None:
        scorecard = evidence_scorecard()
        assert "summary" in scorecard
        assert "experiments" in scorecard
        assert "total_runs" in scorecard["summary"]
        assert "completed_hardware_runs" in scorecard["summary"]
        assert "completed_local_runs" in scorecard["summary"]

    def test_review_pack_structure(self) -> None:
        pack = review_pack()
        assert pack["service"] == "quantum-workbench"
        assert "why_it_matters" in pack
        assert "experiments" in pack
        assert "proof_sequence" in pack
        assert "evidence_scorecard" in pack

    def test_ibm_usage_summary_empty_when_no_runs(self) -> None:
        summary = ibm_usage_summary()
        assert "completed_runs" in summary
        assert "total_quantum_seconds" in summary
        assert isinstance(summary["records"], list)

    def test_scorecard_entry_none_input(self) -> None:
        assert _scorecard_entry(None) is None

    def test_scorecard_entry_with_run(self) -> None:
        run: dict[str, Any] = {
            "run_id": "test-123",
            "status": "completed",
            "backend_name": "test-backend",
            "shots": 1024,
            "updated_at": "2026-01-01T00:00:00Z",
            "analysis": {
                "metric_name": "test_metric",
                "metric_value": 0.95,
                "dominant_states": [{"state": "00", "count": 500}],
            },
        }
        entry = _scorecard_entry(run)
        assert entry is not None
        assert entry["run_id"] == "test-123"
        assert entry["metric_value"] == 0.95

    def test_base_record_has_required_fields(self) -> None:
        record = _base_record(
            experiment_id="bell_pair",
            mode="local",
            shots=1024,
            backend_name="test",
            parameters={},
            status="completed",
        )
        assert record["run_id"].startswith("qwl-")
        assert record["experiment_id"] == "bell_pair"
        assert "created_at" in record
        assert "updated_at" in record


# ---------------------------------------------------------------------------
# 5. API endpoint contracts
# ---------------------------------------------------------------------------


class TestAPIEndpoints:
    """Test the FastAPI endpoint contracts."""

    def test_health_returns_ok(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["service"] == "quantum-workbench"
        assert "hardware_support" in payload
        assert "routes" in payload

    def test_api_meta_runtime_brief(self) -> None:
        response = client.get("/api/runtime/brief")
        assert response.status_code == 200
        payload = response.json()
        assert payload["service"] == "quantum-workbench"
        assert "mode" in payload
        assert "experiments" in payload
        assert "hardware_support" in payload

    def test_api_runtime_brief_experiments_list(self) -> None:
        response = client.get("/api/runtime/brief")
        payload = response.json()
        ids = {e["experiment_id"] for e in payload["experiments"]}
        assert {"bell_pair", "ghz_three", "qaoa_triangle", "h2_vqe_mini"} == ids

    def test_api_review_pack(self) -> None:
        response = client.get("/api/review-pack")
        assert response.status_code == 200
        payload = response.json()
        assert payload["service"] == "quantum-workbench"
        assert "why_it_matters" in payload
        assert isinstance(payload["experiments"], list)

    def test_api_evidence_scorecard(self) -> None:
        response = client.get("/api/evidence/scorecard")
        assert response.status_code == 200
        payload = response.json()
        assert "summary" in payload
        assert "experiments" in payload

    def test_experiment_catalog(self) -> None:
        response = client.get("/api/experiments")
        assert response.status_code == 200
        payload = response.json()
        experiment_ids = {item["experiment_id"] for item in payload}
        assert {
            "bell_pair",
            "ghz_three",
            "qaoa_triangle",
            "h2_vqe_mini",
        } <= experiment_ids

    def test_local_run_returns_counts_and_analysis(self) -> None:
        response = client.post(
            "/api/runs/local",
            json={"experiment_id": "bell_pair", "shots": 512, "parameters": {}},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "local"
        assert payload["status"] == "completed"
        assert sum(payload["counts"].values()) == 512
        assert payload["analysis"]["metric_name"] == "entanglement_signal"

    def test_local_run_unknown_experiment_returns_404(self) -> None:
        response = client.post(
            "/api/runs/local",
            json={"experiment_id": "nonexistent", "shots": 512, "parameters": {}},
        )
        assert response.status_code == 404

    def test_local_run_invalid_shots_returns_422(self) -> None:
        response = client.post(
            "/api/runs/local",
            json={"experiment_id": "bell_pair", "shots": 10, "parameters": {}},
        )
        assert response.status_code == 422  # Pydantic validation: ge=128

    def test_hardware_requires_token(self) -> None:
        response = client.post(
            "/api/runs/hardware",
            json={"experiment_id": "bell_pair", "shots": 512, "parameters": {}},
        )
        assert response.status_code == 503
        assert "IBM_QUANTUM_TOKEN" in response.json()["detail"]

    def test_hardware_route_requires_operator_token_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("IBM_QUANTUM_TOKEN", "real-ish-token")
        monkeypatch.setenv("QUANTUM_OPERATOR_TOKEN", "ops-secret")
        response = client.post(
            "/api/runs/hardware",
            json={"experiment_id": "bell_pair", "shots": 512, "parameters": {}},
        )
        assert response.status_code == 401
        assert response.headers["x-required-operator-header"] == "x-operator-token"

    def test_hardware_route_accepts_operator_token_and_then_checks_runtime_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QUANTUM_OPERATOR_TOKEN", "ops-secret")
        monkeypatch.setattr(
            "app.quantum.runtime.ibm_backend_report",
            lambda backend_name="ibm_torino", experiment_id="bell_pair": {
                "backend_name": backend_name,
                "experiment_id": experiment_id,
                "status": "ok",
            },
        )
        response = client.get(
            "/api/ibm/backend-report",
            headers={"x-operator-token": "ops-secret"},
        )
        assert response.status_code == 200

    def test_braket_local_run_returns_counts(self) -> None:
        response = client.post(
            "/api/runs/braket-local",
            json={"experiment_id": "bell_pair", "shots": 256, "parameters": {}},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "braket-local"
        assert payload["status"] == "completed"
        assert sum(payload["counts"].values()) == 256

    def test_braket_hardware_requires_aws_credentials(self) -> None:
        response = client.post(
            "/api/runs/braket-hardware",
            json={"experiment_id": "bell_pair", "shots": 256, "parameters": {}},
        )
        assert response.status_code == 503
        assert "AWS credentials" in response.json()["detail"]

    def test_braket_hardware_requires_operator_token_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("QUANTUM_OPERATOR_TOKEN", "ops-secret")
        response = client.post(
            "/api/runs/braket-hardware",
            json={"experiment_id": "bell_pair", "shots": 256, "parameters": {}},
        )
        assert response.status_code == 401

    def test_ibm_proof_pack_requires_token(self) -> None:
        response = client.get("/api/ibm/proof-pack")
        assert response.status_code == 503
        assert "IBM_QUANTUM_TOKEN" in response.json()["detail"]

    def test_run_not_found_returns_404(self) -> None:
        response = client.get("/api/runs/nonexistent-run-id")
        assert response.status_code == 404

    def test_runs_list_returns_list(self) -> None:
        response = client.get("/api/runs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_error_metrics_endpoint_returns_structure(self) -> None:
        response = client.get("/api/error-metrics")
        assert response.status_code == 200
        payload = response.json()
        assert "backend_failures" in payload
        assert "circuit_validation_errors" in payload
        assert "provider_api_errors" in payload
        assert "result_extraction_errors" in payload
        assert "recent_errors" in payload


# ---------------------------------------------------------------------------
# 6. Chemistry workflow (H2 VQE)
# ---------------------------------------------------------------------------


class TestChemistryWorkflow:
    """Test the H2 VQE mini chemistry workflow."""

    def test_h2_vqe_pack_returns_domain_surface(self) -> None:
        response = client.get("/api/domain/h2-vqe-pack")
        assert response.status_code == 200
        payload = response.json()
        assert payload["domain"] == "chemistry-mini-workflow"
        assert "reference_ground_energy" in payload
        assert "theta_sweep" in payload
        assert "best_theta" in payload
        assert "best_energy" in payload

    def test_h2_theta_sweep_finds_minimum(self) -> None:
        sweep = h2_theta_sweep(samples=11)
        assert "best" in sweep
        assert "evaluations" in sweep
        assert len(sweep["evaluations"]) == 11
        best_energy = sweep["best"]["energy"]
        reference = sweep["reference_ground_energy"]
        # The best coarse-grained theta should get within 1.0 of exact ground energy
        # (coarse 11-sample sweep has limited resolution)
        assert abs(best_energy - reference) < 1.0

    def test_h2_theta_sweep_min_samples_enforced(self) -> None:
        sweep = h2_theta_sweep(samples=1)
        assert len(sweep["evaluations"]) >= 3

    def test_h2_vqe_local_run(self) -> None:
        response = client.post(
            "/api/runs/local",
            json={
                "experiment_id": "h2_vqe_mini",
                "shots": 512,
                "parameters": {"theta": 0.2},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis"]["metric_name"] == "estimated_h2_energy"
        assert "reference_ground_energy" in payload["analysis"]


# ---------------------------------------------------------------------------
# 7. Local vs cloud execution path
# ---------------------------------------------------------------------------


class TestLocalVsCloudPath:
    """Validate the local vs cloud execution path distinction."""

    def test_compare_local_backends_returns_delta_surface(self) -> None:
        response = client.post(
            "/api/compare/local-backends",
            json={"experiment_id": "bell_pair", "shots": 128, "parameters": {}},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["comparison"]["metric_name"] == "entanglement_signal"
        assert "total_variation_distance" in payload["comparison"]
        assert payload["runs"]["qiskit_local"]["mode"] == "local"
        assert payload["runs"]["braket_local"]["mode"] == "braket-local"

    def test_comparison_summary_bell_pair(self) -> None:
        summary = _comparison_summary("bell_pair", None, 0.05)
        assert "closely aligned" in summary

    def test_comparison_summary_bell_pair_divergent(self) -> None:
        summary = _comparison_summary("bell_pair", None, 0.2)
        assert "noticeably different" in summary

    def test_comparison_summary_qaoa(self) -> None:
        summary = _comparison_summary("qaoa_triangle", 0.05, 0.1)
        assert "higher" in summary

    def test_comparison_summary_unknown_experiment(self) -> None:
        summary = _comparison_summary("custom_experiment", None, 0.1)
        assert "total variation distance" in summary

    def test_local_and_braket_produce_same_experiment_id(self) -> None:
        r1 = client.post(
            "/api/runs/local",
            json={"experiment_id": "ghz_three", "shots": 128, "parameters": {}},
        )
        r2 = client.post(
            "/api/runs/braket-local",
            json={"experiment_id": "ghz_three", "shots": 128, "parameters": {}},
        )
        assert r1.json()["experiment_id"] == r2.json()["experiment_id"] == "ghz_three"
        assert r1.json()["mode"] == "local"
        assert r2.json()["mode"] == "braket-local"


# ---------------------------------------------------------------------------
# 8. Store persistence
# ---------------------------------------------------------------------------


class TestRunStore:
    """Test the RunStore persistence layer."""

    def test_store_upsert_and_retrieve(self, tmp_path: Path) -> None:
        store = RunStore(tmp_path / "test_runs.json")
        record: dict[str, Any] = {
            "run_id": "test-001",
            "experiment_id": "bell_pair",
            "mode": "local",
            "status": "completed",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        store.upsert_run(record)
        retrieved = store.get_run("test-001")
        assert retrieved is not None
        assert retrieved["run_id"] == "test-001"

    def test_store_upsert_updates_existing(self, tmp_path: Path) -> None:
        store = RunStore(tmp_path / "test_runs.json")
        record: dict[str, Any] = {
            "run_id": "test-002",
            "experiment_id": "bell_pair",
            "mode": "local",
            "status": "running",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        store.upsert_run(record)
        record["status"] = "completed"
        record["updated_at"] = "2026-01-01T00:01:00Z"
        store.upsert_run(record)
        runs = store.list_runs()
        matching = [r for r in runs if r["run_id"] == "test-002"]
        assert len(matching) == 1
        assert matching[0]["status"] == "completed"

    def test_store_get_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = RunStore(tmp_path / "test_runs.json")
        assert store.get_run("does-not-exist") is None

    def test_store_list_runs_sorted_by_updated_at(self, tmp_path: Path) -> None:
        store = RunStore(tmp_path / "test_runs.json")
        store.upsert_run(
            {
                "run_id": "old",
                "experiment_id": "bell_pair",
                "mode": "local",
                "status": "completed",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )
        store.upsert_run(
            {
                "run_id": "new",
                "experiment_id": "bell_pair",
                "mode": "local",
                "status": "completed",
                "created_at": "2026-01-02T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
            }
        )
        runs = store.list_runs()
        assert runs[0]["run_id"] == "new"
        assert runs[1]["run_id"] == "old"
