from __future__ import annotations

import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANDIDATES = (8888, 8000, 18000, 8001, 8765)


def port_free(port: int) -> bool:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def pick_port() -> int:
    for port in CANDIDATES:
        if port_free(port):
            return port
    raise SystemExit("No free backend port in 8888/8000/18000/8001/8765")


def main() -> None:
    port = pick_port()
    runtime_dir = ROOT / "data"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "dev_port.txt").write_text(str(port), encoding="utf-8")
    print(f"Starting backend on http://127.0.0.1:{port}")
    print(f"API docs: http://127.0.0.1:{port}/docs")
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=True, reload_dirs=[str(ROOT / "app")])


if __name__ == "__main__":
    main()
