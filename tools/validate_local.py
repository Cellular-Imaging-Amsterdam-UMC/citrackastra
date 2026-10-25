"""Run real local model inference, verify source preservation and retain evidence."""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import torch
import zarr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from citrackastra.models import MODELS
from citrackastra.workflow import Settings, run_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("publicdata/plates"))
    parser.add_argument("--output-dir", type=Path, default=Path("test-results/public"))
    parser.add_argument("--models", nargs="+", choices=list(MODELS), default=["general_2d", "ctc"])
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--modes", nargs="+", choices=["greedy", "greedy_nodiv", "ilp"], default=["greedy"])
    parser.add_argument("--model-dir", default="models")
    parser.add_argument("--movie", action="store_true")
    parser.add_argument("--inputs", nargs="+", type=Path, help="Explicit input plate stores instead of scanning the input directory")
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was requested but is unavailable; run install_cuda.cmd")
    # Respect allocated resources and avoid OpenMP oversubscription on small tests.
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    inputs = args.inputs or sorted(args.input_dir.glob("*.ome.zarr"))
    if not inputs:
        parser.error("No public OME-Zarr inputs; run tools/prepare_publicdata.py first")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    report = {"torch": torch.__version__, "cuda_runtime": torch.version.cuda,
              "device": torch.cuda.get_device_name(0) if args.device == "cuda" else "CPU", "runs": records,
              "scope": "Compatibility and real-model smoke validation on CTC reference markers, not an accuracy benchmark"}
    for model in args.models:
        for mode in args.modes:
            for source in inputs:
                if args.device == "cuda":
                    torch.cuda.reset_peak_memory_stats()
                result = run_store(source, args.output_dir / model / mode,
                                   Settings(model=model, model_dir=args.model_dir, device=args.device, mode=mode, movie=args.movie))
                original = zarr.open_group(str(source), mode="r")
                output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")
                from citrackastra.ngff import image_groups
                for field in image_groups(original):
                    np.testing.assert_array_equal(original[f"{field}/0"][:], output[f"{field}/0"][:])
                    np.testing.assert_array_equal(original[f"{field}/labels/instances/0"][:], output[f"{field}/labels/instances/0"][:])
                with sqlite3.connect(result / "tracking.sqlite") as db:
                    counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("tracks", "observations", "links")}
                    assert counts["observations"] > 0
                    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    counts["divisions"] = db.execute("SELECT count(*) FROM (SELECT source_frame,source_label FROM links WHERE kind='division' GROUP BY field_id,source_frame,source_label HAVING count(*)=2)").fetchone()[0]
                provenance = json.loads((result / "provenance.json").read_text(encoding="utf-8"))
                records.append({"dataset": source.name, "model": model, "mode": mode, "result": str(result.resolve()),
                                "runtime_seconds": provenance["runtime_seconds"], "counts": counts,
                                "peak_cuda_allocated_mib": torch.cuda.max_memory_allocated() / 1024**2 if args.device == "cuda" else None,
                                "source": dict(original.attrs["publicdata"]), "pixels_preserved": True,
                                "model_archive_sha256": provenance["model"]["archive_sha256"], "status": "passed"})
                if args.movie:
                    movie = json.loads((result / "movie.json").read_text(encoding="utf-8"))
                    records[-1]["movie"] = movie
                    for key in ("filename", "tracking_filename"):
                        if key in movie:
                            assert (result / movie[key]).stat().st_size > 0
                (args.output_dir / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
