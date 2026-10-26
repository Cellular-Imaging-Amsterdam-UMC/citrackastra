"""Independent field/label tracking with staged outputs and physical result tables."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import numpy as np
import psutil
import zarr

from . import __version__
from .models import MODELS, load_model, verify_model
from .ngff import check_label_alignment, image_groups, inspect_image, label_names, sequence, write_tracked


@dataclass
class Settings:
    model: str = "general_2d"
    model_dir: str = os.environ.get("CITRACKASTRA_MODELS", "models")
    labels: str = ""
    channel: int = 1
    mode: str = "greedy"
    device: str = "auto"
    max_memory_gb: float = 4.
    workers: int = 0
    batch_size: int = 1
    movie: bool = False
    movie_fps: int = 12

    def validate(self):
        if self.model not in MODELS or self.mode not in {"greedy", "greedy_nodiv", "ilp"}:
            raise ValueError("Unknown model or linking mode")
        if self.device not in {"auto", "cpu", "cuda", "mps"}:
            raise ValueError("Device must be auto, cpu, cuda or mps")
        if self.labels is not None and not isinstance(self.labels, str):
            raise ValueError("Label name must be a string or omitted")
        if any(type(v) is not int for v in (self.channel, self.workers, self.batch_size)) or self.channel < 1 or self.workers < 0 or self.batch_size < 1:
            raise ValueError("Channel/batch size must be positive; workers must be nonnegative")
        if not math.isfinite(self.max_memory_gb) or self.max_memory_gb <= 0:
            raise ValueError("Maximum memory must be finite and positive")
        if not isinstance(self.movie, bool) or type(self.movie_fps) is not int or not 1 <= self.movie_fps <= 60:
            raise ValueError("Movie must be a boolean; movie FPS must be between 1 and 60")


SCHEMA = """
CREATE TABLE schema_info (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE run (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE fields (field_id INTEGER PRIMARY KEY, image_path TEXT, source_label TEXT, output_label TEXT, dimensions INTEGER, scale_um_json TEXT, origin_um_json TEXT, seconds_per_frame REAL, time_origin REAL);
CREATE TABLE tracks (field_id INTEGER, track_id INTEGER, parent_track_id INTEGER, parent_kind TEXT, start_frame INTEGER, end_frame INTEGER, observation_count INTEGER, duration REAL, path_length_um REAL, displacement_um REAL, mean_speed REAL, time_unit TEXT, speed_unit TEXT, PRIMARY KEY(field_id,track_id));
CREATE TABLE observations (field_id INTEGER, track_id INTEGER, timepoint INTEGER, source_label INTEGER, z_px REAL, y_px REAL, x_px REAL, z_um REAL, y_um REAL, x_um REAL, time REAL, PRIMARY KEY(field_id,timepoint,source_label));
CREATE TABLE links (field_id INTEGER, source_frame INTEGER, source_label INTEGER, target_frame INTEGER, target_label INTEGER, kind TEXT, distance_um REAL, elapsed REAL, speed REAL, PRIMARY KEY(field_id,source_frame,source_label,target_frame,target_label));
CREATE VIEW track_summary AS SELECT f.image_path,f.source_label AS source_label_name,f.output_label AS tracked_label_name,t.* FROM tracks t JOIN fields f USING(field_id);
CREATE VIEW object_navigation AS SELECT o.field_id,f.image_path,f.source_label AS source_label_name,o.source_label AS source_label_value,f.output_label AS tracked_label_name,o.track_id AS tracked_label_value,o.timepoint,0 AS z_index,o.y_px,o.x_px,o.y_um,o.x_um,o.time FROM observations o JOIN fields f USING(field_id);
"""


def write_tables(db, field_id, graph, source_masks, tracked, tracklets, info):
    """Map source instances to trajectory IDs; measure centroids in physical units."""
    from skimage.measure import regionprops

    positions, observations, track_points = {}, {}, {}
    for t, frame in enumerate(source_masks):
        for region in regionprops(frame):
            key = (t, int(region.label))
            pixel = np.asarray(region.centroid)
            physical = pixel * info.scale + info.offset
            output_values = np.unique(tracked[t][tuple(region.coords.T)])
            if len(output_values) != 1 or output_values[0] == 0:
                raise RuntimeError(f"Source object {key} is absent or split in the result")
            track_id = int(output_values[0])
            positions[key], observations[key] = physical, track_id
            track_points.setdefault(track_id, []).append((t, physical))
            xyz_px = [None, *pixel] if info.dimensions == 2 else pixel.tolist()
            xyz_um = [None, *physical] if info.dimensions == 2 else physical.tolist()
            timestamp = info.time_origin + t * (info.seconds or 1.)
            db.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)", (field_id, track_id, t, int(region.label), *xyz_px, *xyz_um, timestamp))
    graph_keys = {(int(n["time"]), int(n["label"])) for _, n in graph.nodes(data=True)}
    if graph_keys != set(observations) or len(graph_keys) != graph.number_of_nodes():
        raise RuntimeError("Tracking graph does not cover every source instance exactly once")
    dt = info.seconds or 1.
    unit = "second" if info.seconds else "frame"
    for row in tracklets.itertuples(index=False):
        points = sorted(track_points[int(row.label)], key=lambda p: p[0])
        path = sum(float(np.linalg.norm(b[1] - a[1])) for a, b in zip(points, points[1:]))
        displacement = float(np.linalg.norm(points[-1][1] - points[0][1]))
        duration = (points[-1][0] - points[0][0]) * dt
        parent_kind = None
        if row.parent:
            start = next(n for n, attrs in graph.nodes(data=True) if int(attrs["time"]) == points[0][0] and observations[(int(attrs["time"]), int(attrs["label"]))] == int(row.label))
            parent = next(iter(graph.predecessors(start)))
            parent_kind = "division" if graph.out_degree(parent) == 2 else "gap"
        db.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (field_id, int(row.label), int(row.parent) or None, parent_kind, int(row.t1), int(row.t2), len(points), duration, path, displacement, path / duration if duration else None, unit, f"micrometer/{unit}"))
    for a, b in graph.edges:
        source, target = graph.nodes[a], graph.nodes[b]
        ka, kb = (int(source["time"]), int(source["label"])), (int(target["time"]), int(target["label"]))
        gap = kb[0] - ka[0]
        if gap <= 0 or graph.in_degree(b) > 1:
            raise RuntimeError("Tracking graph contains a backward link or unsupported merge")
        distance = float(np.linalg.norm(positions[kb] - positions[ka]))
        kind = "division" if graph.out_degree(a) > 1 else "gap" if gap > 1 else "link"
        db.execute("INSERT INTO links VALUES (?,?,?,?,?,?,?,?,?)", (field_id, *ka, *kb, kind, distance, gap * dt, distance / (gap * dt)))
    return {"observations": len(observations), "tracks": len(track_points), "links": graph.number_of_edges()}


def export_csv(db, folder):
    for table in ("fields", "tracks", "observations", "links"):
        cursor = db.execute(f"SELECT * FROM {table}")
        with (folder / f"{table}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow([col[0] for col in cursor.description])
            while rows := cursor.fetchmany(1024):
                writer.writerows(rows)


def run_store(source, output_dir, settings, *, model=None, log=print):
    settings.validate()
    if settings.movie:
        from .movie import check_renderer
        check_renderer()
    source = Path(source).resolve()
    output_dir = Path(output_dir).resolve()
    if not source.is_dir() or not source.name.endswith(".zarr"):
        raise ValueError("Input must be a local OME-Zarr directory")
    if output_dir == source or output_dir.is_relative_to(source):
        raise ValueError("Output directory must be outside the source store")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Input must be a complete local store without symbolic links")
    name = source.name.removesuffix(".ome.zarr").removesuffix(".zarr") + "__citrackastra"
    final = output_dir / name
    if final.exists():
        raise FileExistsError(f"Output already exists: {final}")
    root = zarr.open_group(str(source), mode="r", use_consolidated=False)
    if root.metadata.zarr_format != 2:
        raise ValueError("This BIOMERO adapter requires NGFF 0.4 / Zarr v2 stores; convert Zarr v3 inputs first")
    paths = image_groups(root)
    if not paths:
        raise ValueError("No NGFF images found")
    jobs = []
    # Check every field and label grid before copying or running the model.
    for path in paths:
        group = root[path] if path else root
        info = inspect_image(group)
        if info.dimensions not in MODELS[settings.model]["dimensions"]:
            raise ValueError("Only 2D images and 2D plates are supported")
        if "c" not in info.names and settings.channel != 1:
            raise ValueError("A channel-free image only supports channel 1")
        if "c" in info.names and settings.channel > info.shape[info.names.index("c")]:
            raise ValueError("Image channel is outside the input")
        for label in label_names(group, settings.labels):
            array = check_label_alignment(group, group[f"labels/{label}"], info)
            if f"{label}_tracks" in group["labels"]:
                raise FileExistsError(f"Tracked label already exists: {path}/{label}_tracks")
            spatial_size = math.prod(size for axis, size in zip(info.names, info.shape) if axis != "c")
            # Arrays, normalized pixels, relabelled masks and working memory; graph costs are data dependent.
            estimate = spatial_size * (32 + array.dtype.itemsize)
            budget = min(settings.max_memory_gb * 1024**3, psutil.virtual_memory().available * .6)
            if estimate > budget:
                raise MemoryError(f"{path or '/'} needs at least {estimate / 1024**3:.2f} GiB working memory; split the sequence or raise --max-memory-gb")
            jobs.append((path, label, info))
    manifest = verify_model(Path(settings.model_dir) / settings.model) if model is None else {"name": "injected-test-model"}
    model = model or load_model(settings.model, settings.model_dir, settings.device)
    output_dir.mkdir(parents=True, exist_ok=True)
    stage = output_dir / f".{name}.partial-{uuid4().hex[:8]}"
    stage.mkdir()
    db = None
    started = time.perf_counter()
    try:
        store = stage / f"{name}.ome.zarr"
        shutil.copytree(source, store)
        # Appending metadata invalidates any consolidated source metadata.
        (store / ".zmetadata").unlink(missing_ok=True)
        target = zarr.open_group(str(store), mode="a", use_consolidated=False)
        db = sqlite3.connect(stage / "tracking.sqlite")
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO schema_info VALUES (?,?)", [("format", "CITrackastra tracking"), ("schema_version", "1")])
        summaries = []
        from trackastra.tracking import graph_to_ctc

        for field_id, (path, label, info) in enumerate(jobs, 1):
            group = root[path] if path else root
            log(f"Tracking {path or '/'} / {label} with {settings.model} ({settings.mode})")
            imgs = sequence(group, info, settings.channel)
            masks = sequence(group[f"labels/{label}"], info)
            if imgs.shape != masks.shape or np.any(masks < 0):
                raise ValueError("Image/mask shapes differ or masks contain negative labels")
            if not np.isfinite(imgs).all():
                raise ValueError("Image contains nonfinite intensities")
            if settings.model == "general_2d_w_SAM2_features":
                model.imgs_path = stage / "_feature_cache" / str(field_id)
            graph, _ = model.track(imgs, masks, mode=settings.mode, n_workers=settings.workers, batch_size=settings.batch_size)
            if any(graph.out_degree(n) > 2 or graph.in_degree(n) > 1 for n in graph):
                raise RuntimeError("Tracking graph contains a nonbinary division or unsupported merge")
            if any(int(graph.nodes[b]["time"]) <= int(graph.nodes[a]["time"]) for a, b in graph.edges):
                raise RuntimeError("Tracking graph contains a backward or same-frame link")
            table, tracked = graph_to_ctc(graph, masks, check=True)
            if len(table) > np.iinfo(np.uint32).max:
                raise OverflowError("Track IDs exceed uint32 capacity")
            counts = write_tables(db, field_id, graph, masks, tracked, table, info)
            outgroup = target[path] if path else target
            write_tracked(outgroup, f"{label}_tracks", tracked, info)
            db.execute("INSERT INTO fields VALUES (?,?,?,?,?,?,?,?,?)", (field_id, path, label, f"{label}_tracks", info.dimensions, json.dumps(info.scale.tolist()), json.dumps(info.offset.tolist()), info.seconds, info.time_origin))
            summaries.append({"field_id": field_id, "image_path": path, "label": label, **counts})
        feature_cache = (stage / "_feature_cache").resolve()
        if feature_cache.exists():
            if not feature_cache.is_relative_to(stage.resolve()) or feature_cache.is_symlink():
                raise RuntimeError("Feature cache is outside the current result staging directory")
            model.feature_extractor = None
            shutil.rmtree(feature_cache)
        report = {"workflow": "CITrackastra", "schema_version": 1, "output_store_uuid": str(uuid4()),
                  "source_store_uuid": dict(root.attrs.get("cisegmentation", {})).get("output_store_uuid"),
                  "version": __version__, "trackastra_version": version("trackastra"),
                  "status": "complete", "source": str(source), "settings": asdict(settings), "model": manifest,
                  "fields": summaries, "runtime_seconds": time.perf_counter() - started,
                  "coordinate_convention": "integer pixel centers; calibrated NGFF scale and translation",
                  "inference_coordinates": "original pixel grid (no physical resampling)",
                  "limitations": "In-memory sequence inference; no claim of biological accuracy or production OMERO roundtrip validation."}
        db.execute("INSERT INTO schema_info VALUES (?,?)", ("output_store_uuid", report["output_store_uuid"]))
        for key, value in report.items():
            db.execute("INSERT INTO run VALUES (?,?)", (key, json.dumps(value)))
        db.commit()
        export_csv(db, stage)
        if settings.movie:
            from .movie import render_movie
            report["movie"] = render_movie(stage, settings)
            db.execute("INSERT INTO run VALUES (?,?)", ("movie", json.dumps(report["movie"])))
            db.commit()
        db.close()
        db = None
        target.attrs["citrackastra"] = report
        (stage / "provenance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        # All result artifacts publish together by a same-filesystem directory rename.
        stage.rename(final)
        log(f"Completed: {final}")
        return final
    except BaseException as exc:
        if db is not None:
            db.close()
        (stage / "FAILED.json").write_text(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, indent=2), encoding="utf-8")
        raise


def run_workflow(input_dir, output_dir, settings):
    source = Path(input_dir)
    stores = [source] if source.name.endswith(".zarr") else sorted(source.glob("*.zarr"))
    if not stores:
        raise ValueError(f"No local OME-Zarr stores found in {source}")
    return [run_store(store, output_dir, settings) for store in stores]
