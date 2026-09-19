#!/usr/bin/env python3
"""Generate a sample report against the mock endpoint."""

import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from test_endpoint import run_mock_endpoint, find_free_port


def main():
    port = find_free_port()
    endpoint_url = f"http://127.0.0.1:{port}/v1"

    print(f"Starting mock endpoint on {endpoint_url}...")
    server = run_mock_endpoint(port)

    try:
        time.sleep(0.5)

        out_dir = Path(__file__).parent.parent / "sample_runs" / "mock-endpoint-test"
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"Running dialproof against {endpoint_url}...")
        result = subprocess.run(
            [
                "dialproof",
                "run",
                "--endpoint",
                endpoint_url,
                "--model",
                "test-model",
                "--allow",
                f"127.0.0.1:{port}",
                "--out",
                str(out_dir),
            ],
            capture_output=True,
            text=True,
        )

        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode == 0:
            print(f"\n✓ Sample report generated in {out_dir}/")
            report_path = out_dir / "report.json"
            if report_path.exists():
                print(f"  - report.json")
                # Print first few lines
                with open(report_path) as f:
                    import json
                    data = json.load(f)
                    print(f"  - Run ID: {data.get('run_id')}")
                    print(f"  - Verdict: {data.get('verdict', {}).get('conformance')}")
        else:
            print(f"✗ Run failed with exit code {result.returncode}")
            sys.exit(1)

    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
