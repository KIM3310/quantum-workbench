from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def main() -> None:
    client = TestClient(app)
    for path in (
        "/health",
        "/api/runtime/brief",
        "/api/experiments",
        "/api/review-pack",
    ):
        response = client.get(path)
        response.raise_for_status()

    response = client.post(
        "/api/runs/local",
        json={
            "experiment_id": "qaoa_triangle",
            "shots": 512,
            "parameters": {"gamma": 0.9, "beta": 0.35},
        },
    )
    response.raise_for_status()
    run_payload = response.json()
    assert run_payload["status"] == "completed"
    response = client.post(
        "/api/runs/braket-local",
        json={"experiment_id": "bell_pair", "shots": 256, "parameters": {}},
    )
    response.raise_for_status()
    braket_payload = response.json()
    assert braket_payload["status"] == "completed"
    response = client.post(
        "/api/compare/local-backends",
        json={"experiment_id": "bell_pair", "shots": 128, "parameters": {}},
    )
    response.raise_for_status()
    comparison = response.json()
    assert "total_variation_distance" in comparison["comparison"]
    print("runtime exercise ok")


if __name__ == "__main__":
    main()
