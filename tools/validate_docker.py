"""Validate release images with offline tracking, calibration and movie checks.

Run after building the images. Source datasets and a local model cache stay
read-only. Each case writes a fresh result directory and retains its log.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import imageio.v2 as imageio
import numpy as np
import zarr


def execute(command, log=None, timeout=60):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if log:
        log.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Container command failed ({result.returncode}):\n{result.stdout[-1500:]}\n{result.stderr[-3500:]}")
    return result.stdout


def probe(image, gpu):
    script = "import json,torch,platform; from importlib.metadata import version; print(json.dumps({'python':platform.python_version(),'architecture':platform.machine(),'torch':torch.__version__,'cuda_runtime':torch.version.cuda,'cuda_available':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'trackastra':version('trackastra'),'divisualisation':version('divisualisation'),'napari':version('napari')}))"
    command = ["docker", "run", "--rm", "--network", "none"]
    if gpu:
        command += ["--gpus", "all"]
    command += ["--entrypoint", "python", image, "-c", script]
    return json.loads(execute(command).strip().splitlines()[-1])


def check_outputs(source, result, movies):
    original = zarr.open_group(str(source), mode="r")
    output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")
    database = sqlite3.connect((result / "tracking.sqlite").as_uri() + "?mode=ro", uri=True)
    try:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        counts = {table: database.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("fields", "tracks", "observations", "links")}
        assert counts["observations"] > 0
        fields = database.execute("SELECT field_id,image_path,source_label,output_label,scale_um_json,origin_um_json FROM fields").fetchall()
        for field_id, path, source_label, output_label, scales, origin in fields:
            np.testing.assert_array_equal(original[f"{path}/0"][:], output[f"{path}/0"][:])
            np.testing.assert_array_equal(original[f"{path}/labels/{source_label}/0"][:], output[f"{path}/labels/{source_label}/0"][:])
            assert output[f"{path}/labels/{output_label}/0"].shape[0] == original[f"{path}/0"].shape[0]
            assert all(v > 0 for v in json.loads(scales))
            expected_pixel_um = float(original.attrs["publicdata"]["pixel_um"])
            np.testing.assert_allclose(json.loads(scales), [expected_pixel_um, expected_pixel_um])
            for y, x, y_um, x_um in database.execute("SELECT y_px,x_px,y_um,x_um FROM observations WHERE field_id=? LIMIT 3", (field_id,)):
                np.testing.assert_allclose([y_um, x_um], np.array([y, x]) * expected_pixel_um + json.loads(origin))
        counts["divisions"] = database.execute("SELECT count(*) FROM (SELECT field_id,source_frame,source_label FROM links WHERE kind='division' GROUP BY field_id,source_frame,source_label HAVING count(*)=2)").fetchone()[0]
        uuid = database.execute("SELECT value FROM schema_info WHERE key='output_store_uuid'").fetchone()[0]
        assert uuid == output.attrs["citrackastra"]["output_store_uuid"]
    finally:
        database.close()
    provenance = json.loads((result / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["status"] == "complete"
    for table in ("fields", "tracks", "observations", "links"):
        assert (result / f"{table}.csv").is_file()
        with (result / f"{table}.csv").open(encoding="utf-8", newline="") as stream:
            assert sum(1 for _ in csv.reader(stream)) - 1 == counts[table]
    videos = []
    if movies:
        for filename in ("tracking_movie.mp4", "spacetime_movie.mp4"):
            with imageio.get_reader(result / filename) as reader:
                metadata = reader.get_meta_data()
                assert metadata["codec"] == "h264" and metadata["duration"] > 0
                frame = reader.get_data(int(metadata["duration"] * metadata["fps"] / 2))
                assert np.std(frame[80:, :, :3]) > 1, f"Blank video: {filename}"
                videos.append({"filename": filename, "codec": metadata["codec"], "size": list(metadata["size"]), "fps": metadata["fps"], "duration": metadata["duration"], "bytes": (result / filename).stat().st_size})
        assert json.loads((result / "movie.json").read_text(encoding="utf-8"))["ground_truth_errors"] is False
    return {"counts": counts, "source_pixels_and_labels_preserved": True, "sqlite_integrity": "ok", "calibration": "verified", "shared_output_uuid": True, "model_archive_sha256": provenance["model"]["archive_sha256"], "videos": videos}


def validate(args):
    args.input_dir = args.input_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.output_dir.exists():
        raise FileExistsError(f"Use a fresh Docker validation directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True)
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "running", "network": "none for every inference container", "platform": "linux/amd64", "image": args.image, "runtime_image": args.runtime_image, "cases": []}
    report["image_id"] = execute(["docker", "image", "inspect", args.image, "--format", "{{.Id}}"] ).strip()
    report["runtime_image_id"] = execute(["docker", "image", "inspect", args.runtime_image, "--format", "{{.Id}}"] ).strip()
    images = {name: json.loads(execute(["docker", "image", "inspect", name]))[0] for name in (args.image, args.runtime_image, args.models_image)}
    complete_layers = images[args.image]["RootFS"]["Layers"]
    runtime_layers = images[args.runtime_image]["RootFS"]["Layers"]
    model_layer = images[args.models_image]["RootFS"]["Layers"][0]
    assert complete_layers[:len(runtime_layers)] == runtime_layers
    assert model_layer in complete_layers, "Complete image must reuse the model-cache layer"
    report["shared_model_layer"] = model_layer
    report["runtime_layers_reused"] = True
    destination = args.output_dir / "docker-validation.json"
    report["gpu_probe"] = probe(args.image, True)
    assert report["gpu_probe"]["cuda_available"], "CUDA is unavailable in Docker"
    report["cpu_probe"] = probe(args.image, False)
    assert not report["cpu_probe"]["cuda_available"]
    cases = []
    datasets = ["Fluo-N2DH-GOWT1-01-6frames.ome.zarr", "Fluo-N2DH-SIM+-01-6frames.ome.zarr", "PhC-C2DH-U373-01-6frames.ome.zarr"]
    for model in ("general_2d", "ctc", "general_2d_w_SAM2_features"):
        for index, dataset in enumerate(datasets):
            cases.append({"name": f"cuda-{model}-{index}", "model": model, "dataset": dataset, "device": "cuda", "mode": "greedy", "movie": model.endswith("SAM2_features") and index == 0})
    cases += [
        {"name": "cpu-no-divisions-movies", "model": "general_2d", "dataset": datasets[0], "device": "cpu", "mode": "greedy_nodiv", "movie": True},
        {"name": "cpu-ilp", "model": "general_2d", "dataset": datasets[0], "device": "cpu", "mode": "ilp", "movie": False},
        {"name": "cuda-long-divisions-movies", "model": "general_2d", "dataset": "Fluo-N2DH-SIM+-01-65frames.ome.zarr", "device": "cuda", "mode": "greedy", "movie": True},
        {"name": "runtime-external-model-cache", "model": "general_2d", "dataset": datasets[0], "device": "cpu", "mode": "greedy", "movie": False, "external_models": True},
    ]
    try:
        for case in cases:
            print(f"Testing {case['name']}", flush=True)
            output = args.output_dir / case["name"]
            output.mkdir()
            image = args.runtime_image if case.get("external_models") else args.image
            container = "citrackastra-validation-" + uuid4().hex[:12]
            command = ["docker", "run", "--rm", "--name", container, "--network", "none", "--platform", "linux/amd64", "--cpus", "4", "--memory", "10g", "--shm-size", "1g",
                       "--mount", f"type=bind,source={args.input_dir},target=/data/in,readonly", "--mount", f"type=bind,source={output},target=/data/out"]
            if case["device"] == "cuda":
                command += ["--gpus", "all"]
            if case.get("external_models"):
                command += ["--mount", f"type=bind,source={args.model_dir.resolve()},target=/opt/models,readonly"]
            command += [image, "--infolder", f"/data/in/{case['dataset']}", "--outfolder", "/data/out", "--device", case["device"], "--model", case["model"], "--mode", case["mode"], "--movie", str(case["movie"]).lower(), "--workers", "0", "--batch-size", "1"]
            started = time.perf_counter()
            try:
                execute(command, output / "container.log", timeout=args.timeout_seconds)
            finally:
                subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = next(p for p in output.iterdir() if p.is_dir() and not p.name.startswith("."))
            evidence = check_outputs(args.input_dir / case["dataset"], result, case["movie"])
            if case["mode"] == "greedy_nodiv":
                assert evidence["counts"]["divisions"] == 0
            if "long-divisions" in case["name"]:
                assert evidence["counts"]["divisions"] > 0
            report["cases"].append({**case, **evidence, "status": "passed", "wall_seconds": time.perf_counter() - started})
            destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["status"] = "passed"
    except BaseException as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Passed {len(cases)} offline container cases: {destination}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="cellularimagingcf/w_citrackastra:v0.1.0")
    parser.add_argument("--runtime-image", default="cellularimagingcf/w_citrackastra:v0.1.0-runtime")
    parser.add_argument("--models-image", default="cellularimagingcf/citrackastra-models:v0.1.0")
    parser.add_argument("--input-dir", type=Path, default=Path("publicdata/plates"))
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    parser.add_argument("--output-dir", type=Path, default=Path("test-results/docker-v0.1.0"))
    parser.add_argument("--timeout-seconds", type=float, default=600, help="Maximum duration per public-data container")
    validate(parser.parse_args())
