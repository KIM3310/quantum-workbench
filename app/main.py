"""Quantum Workbench FastAPI application.

Exposes REST endpoints for quantum experiment execution on local simulators
and real hardware (IBM Quantum, Amazon Braket), run history, evidence
scorecards, and backend posture reporting.
"""

from __future__ import annotations

import logging
import sys
import os
import hmac
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.quantum.runtime import (
    compare_local_backends,
    get_error_metrics,
    list_available_backends,
    list_runs,
    refresh_run,
    review_pack,
    run_braket_local,
    run_local,
    runtime_brief,
    submit_braket_hardware,
    submit_hardware,
    evidence_scorecard,
    h2_vqe_pack,
)


# ---------------------------------------------------------------------------
# Structured logging configuration
# ---------------------------------------------------------------------------


def _configure_logging() -> None:
    """Configure structured logging for the quantum workbench runtime.

    Uses a consistent format with timestamps, logger names, and log levels
    for all quantum_workbench.* loggers. Defaults to INFO level; set
    LOG_LEVEL environment variable to override.
    """
    import os

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root_logger = logging.getLogger("quantum_workbench")
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.addHandler(handler)
    # Prevent duplicate log entries if uvicorn also configures the root logger
    root_logger.propagate = False


_configure_logging()

logger = logging.getLogger("quantum_workbench.api")


ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"

app = FastAPI(title="Quantum Workbench", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _hardware_operator_token() -> str:
    return (os.getenv("QUANTUM_OPERATOR_TOKEN") or "").strip()


def _read_presented_token(request: Request) -> str:
    header_token = str(request.headers.get("x-operator-token") or "").strip()
    if header_token:
        return header_token
    auth_header = str(request.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


def require_hardware_operator_token(request: Request) -> None:
    expected = _hardware_operator_token()
    if not expected:
        return
    presented = _read_presented_token(request)
    if presented and hmac.compare_digest(presented, expected):
        return
    raise HTTPException(
        status_code=401,
        detail="operator token required for hardware routes",
        headers={"x-required-operator-header": "x-operator-token"},
    )


class RunRequest(BaseModel):
    """Request body for submitting a quantum experiment run.

    Attributes:
        experiment_id: Registered experiment identifier.
        shots: Number of measurement shots (128-8192).
        backend_name: Optional specific backend name or ARN.
        parameters: Optional circuit parameter overrides.
        ibm_options: Optional IBM Runtime sampler options.
    """

    experiment_id: str
    shots: int = Field(default=1024, ge=128, le=8192)
    backend_name: str | None = None
    parameters: dict[str, float] = Field(default_factory=dict)
    ibm_options: dict[str, Any] = Field(default_factory=dict)


@app.get("/")
def root() -> FileResponse:
    """Serve the single-page UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, Any]:
    """Return service health status with available routes and hardware posture."""
    brief = runtime_brief()
    return {
        "service": brief["service"],
        "status": "ok",
        "mode": brief["mode"],
        "hardware_support": brief["hardware_support"],
        "routes": [
            "/api/runtime/brief",
            "/api/experiments",
            "/api/backends",
            "/api/runs",
            "/api/review-pack",
            "/api/error-metrics",
        ],
    }


@app.get("/api/runtime/brief")
def api_runtime_brief() -> dict[str, Any]:
    """Return the full runtime brief including experiments and hardware posture."""
    return runtime_brief()


@app.get("/api/experiments")
def api_experiments() -> list[dict[str, Any]]:
    """List all registered experiments."""
    return runtime_brief()["experiments"]


@app.get("/api/backends")
def api_backends() -> dict[str, Any]:
    """List available backends across IBM Quantum and Amazon Braket."""
    return list_available_backends()


@app.get("/api/runs")
def api_runs() -> list[dict[str, Any]]:
    """List all run records, most recent first."""
    return list_runs()


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> dict[str, Any]:
    """Retrieve and refresh a single run record by ID."""
    record = refresh_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@app.post("/api/runs/local")
def api_run_local(request: RunRequest) -> dict[str, Any]:
    """Execute an experiment on the local Qiskit simulator."""
    try:
        return run_local(
            experiment_id=request.experiment_id,
            shots=request.shots,
            parameters=request.parameters,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/runs/braket-local")
def api_run_braket_local(request: RunRequest) -> dict[str, Any]:
    """Execute an experiment on the Amazon Braket local simulator."""
    try:
        return run_braket_local(
            experiment_id=request.experiment_id,
            shots=request.shots,
            parameters=request.parameters,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/runs/hardware")
def api_run_hardware(request: Request, body: RunRequest) -> dict[str, Any]:
    """Submit an experiment to IBM Quantum hardware."""
    require_hardware_operator_token(request)
    try:
        return submit_hardware(
            experiment_id=body.experiment_id,
            shots=body.shots,
            backend_name=body.backend_name,
            parameters=body.parameters,
            options_payload=body.ibm_options,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/runs/braket-hardware")
def api_run_braket_hardware(request: Request, body: RunRequest) -> dict[str, Any]:
    """Submit an experiment to Amazon Braket QPU hardware."""
    require_hardware_operator_token(request)
    try:
        return submit_braket_hardware(
            experiment_id=body.experiment_id,
            shots=body.shots,
            backend_arn=body.backend_name,
            parameters=body.parameters,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/compare/local-backends")
def api_compare_local_backends(request: RunRequest) -> dict[str, Any]:
    """Run the same experiment on both local simulators and compare results."""
    try:
        return compare_local_backends(
            experiment_id=request.experiment_id,
            shots=request.shots,
            parameters=request.parameters,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/review-pack")
def api_review_pack() -> dict[str, Any]:
    """Generate the experiment summary pack."""
    return review_pack()


@app.get("/api/evidence/scorecard")
def api_evidence_scorecard() -> dict[str, Any]:
    """Return the evidence scorecard showing per-experiment execution coverage."""
    return evidence_scorecard()


@app.get("/api/domain/h2-vqe-pack")
def api_h2_vqe_pack() -> dict[str, Any]:
    """Return the H2 VQE chemistry domain pack."""
    return h2_vqe_pack()


@app.get("/api/error-metrics")
def api_error_metrics() -> dict[str, Any]:
    """Return error recovery metrics for operational observability."""
    return get_error_metrics()


@app.get("/api/ibm/backend-report")
def api_ibm_backend_report(
    request: Request,
    backend_name: str = "ibm_torino",
    experiment_id: str = "bell_pair",
) -> dict[str, Any]:
    """Generate a detailed IBM backend report with transpilation analysis."""
    require_hardware_operator_token(request)
    try:
        from app.quantum.runtime import ibm_backend_report

        return ibm_backend_report(
            backend_name=backend_name, experiment_id=experiment_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/ibm/proof-pack")
def api_ibm_proof_pack(
    request: Request, backend_name: str = "ibm_torino"
) -> dict[str, Any]:
    """Generate a comprehensive IBM proof pack for hardware verification."""
    require_hardware_operator_token(request)
    try:
        from app.quantum.runtime import ibm_proof_pack

        return ibm_proof_pack(backend_name=backend_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
