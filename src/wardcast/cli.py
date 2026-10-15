"""Portable command-line entry points. Serving a demo never trains or downloads."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def _project_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    if os.environ.get("WARDCAST_ROOT"):
        return Path(os.environ["WARDCAST_ROOT"]).expanduser().resolve()
    for candidate in (Path.cwd(), Path(__file__).resolve().parents[2]):
        if (candidate / "data/source_manifest.json").exists():
            return candidate
    raise SystemExit("Run from the repository root or pass --root /path/to/wardcast.")


def _ensure_macos_openmp() -> None:
    """Reuse sklearn's licensed OpenMP runtime when Homebrew is absent on macOS.

    dyld reads its library search path at process startup, so restart once before
    importing numerical libraries. This touches neither system nor package files.
    The regular Homebrew libomp installation also works without this helper.
    """
    if sys.platform != "darwin" or os.environ.get("WARDCAST_OPENMP_READY"):
        return
    import importlib.util

    spec = importlib.util.find_spec("sklearn")
    if spec and spec.origin:
        runtime = Path(spec.origin).parent / ".dylibs"
        if (runtime / "libomp.dylib").exists():
            env = dict(os.environ)
            env["DYLD_LIBRARY_PATH"] = str(runtime) + (
                ":" + env["DYLD_LIBRARY_PATH"] if env.get("DYLD_LIBRARY_PATH") else "")
            env["WARDCAST_OPENMP_READY"] = "1"
            os.execve(sys.executable, [sys.executable, "-m", "wardcast", *sys.argv[1:]], env)


def main() -> None:
    parser = argparse.ArgumentParser(prog="wardcast", description="WardCast reproducible capacity forecasts")
    parser.add_argument("--root", help="Repository root (defaults to current checkout)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download", help="Fetch and verify the 48 pinned NHS publications")
    commands.add_parser("prepare", help="Normalize sources, validate data, and build the DuckDB/Parquet panel")
    commands.add_parser("train", help="Run chronological benchmarks and generate trained demo artifacts")
    commands.add_parser("reproduce", help="Download, prepare, and train from the pinned source manifest")
    commands.add_parser("inspect", help="Print bundled data and model metadata")
    serve = commands.add_parser("serve", help="Serve the bundled app/API without downloading or training")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    root = _project_root(args.root)
    os.environ["WARDCAST_ROOT"] = str(root)
    if args.command in {"train", "reproduce"}:
        _ensure_macos_openmp()
    if args.command in {"download", "reproduce"}:
        from .data import download
        download(root)
    if args.command in {"prepare", "reproduce"}:
        from .data import prepare
        prepare(root)
    if args.command in {"train", "reproduce"}:
        from .training import train
        train(root)
    elif args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(root / "artifacts/demo.json"), host=args.host, port=args.port)
    elif args.command == "inspect":
        bundle = root / "artifacts/demo.json"
        if not bundle.exists():
            raise SystemExit("Demo artifacts missing. Run wardcast train.")
        data = json.loads(bundle.read_text())
        print(json.dumps({"metadata": data["metadata"], "selection": data["evaluation"]["selection"]}, indent=2))


if __name__ == "__main__":
    main()
