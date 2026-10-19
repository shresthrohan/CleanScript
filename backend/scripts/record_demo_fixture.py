"""Record the frontend's demo-mode fixture from a real run of the backend.

    cd backend
    .venv\\Scripts\\python scripts\\record_demo_fixture.py

Uploads examples/students.csv, compiles examples/students.clean and executes it through the
actual API (in-process TestClient), then writes the three responses to
frontend/src/demo/fixture.json. Re-run whenever the API output format changes.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def main():
    csv_bytes = (ROOT / "examples" / "students.csv").read_bytes()
    source = (ROOT / "examples" / "students.clean").read_text(encoding="utf-8")
    with TestClient(app) as client:
        upload = client.post("/api/sessions/upload", files={"file": ("students.csv", csv_bytes, "text/csv")})
        upload.raise_for_status()
        sid = upload.json()["session_id"]
        compiled = client.post(f"/api/sessions/{sid}/compile", json={"source": source}).json()
        assert compiled["status"] == "success", compiled["diagnostics"]
        executed = client.post(f"/api/sessions/{sid}/execute",
                               json={"compilation_id": compiled["compilation_id"]}).json()
        assert executed["status"] == "success", executed["error"]
    fixture = {
        "note": "Recorded from a real backend run by backend/scripts/record_demo_fixture.py. Demo mode only.",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "upload": upload.json(),
        "compile": compiled,
        "execute": executed,
    }
    out = ROOT / "frontend" / "src" / "demo" / "fixture.json"
    out.write_text(json.dumps(fixture, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
