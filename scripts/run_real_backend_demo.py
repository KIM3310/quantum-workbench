from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quantum.runtime import submit_braket_hardware, submit_hardware  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit a fixed quantum experiment to a real backend."
    )
    parser.add_argument("--provider", choices=("ibm", "braket"), required=True)
    parser.add_argument("--experiment", default="bell_pair")
    parser.add_argument("--shots", type=int, default=128)
    parser.add_argument(
        "--backend", default=None, help="IBM backend name or Braket backend ARN"
    )
    parser.add_argument("--gamma", type=float, default=0.9)
    parser.add_argument("--beta", type=float, default=0.35)
    parser.add_argument("--enable-twirling", action="store_true")
    parser.add_argument("--enable-dynamical-decoupling", action="store_true")
    parser.add_argument("--meas-type", default=None)
    parser.add_argument("--job-tag", action="append", default=[])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    parameters = {"gamma": args.gamma, "beta": args.beta}
    ibm_options = {
        "enable_twirling": args.enable_twirling,
        "enable_dynamical_decoupling": args.enable_dynamical_decoupling,
        "meas_type": args.meas_type,
        "job_tags": args.job_tag,
    }

    try:
        if args.provider == "ibm":
            result = submit_hardware(
                experiment_id=args.experiment,
                shots=args.shots,
                backend_name=args.backend,
                parameters=parameters,
                options_payload=ibm_options,
            )
        else:
            result = submit_braket_hardware(
                experiment_id=args.experiment,
                shots=args.shots,
                backend_arn=args.backend,
                parameters=parameters,
            )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()
    print(
        f"Next: poll GET /api/runs/{result['run_id']} or inspect artifacts/run_history.json"
    )


if __name__ == "__main__":
    main()
