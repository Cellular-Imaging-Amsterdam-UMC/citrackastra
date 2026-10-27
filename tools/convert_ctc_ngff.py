"""Convert complete 2D CTC training ZIPs to standalone OME-Zarr NGFF 0.4.

No download, inference, resampling, relabelling or frame truncation is performed.
Complete annotation sequences become independent image-label overlays. Sparse
annotations are stored individually under ctc_annotations with explicit frame
indices, never padded with invented background masks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import numpy as np
import tifffile
import zarr
from numcodecs import Blosc


SOURCE = "https://celltrackingchallenge.net/2d-datasets/"
CATALOG = {
    "Fluo-N2DH-GOWT1": {"pixel_um": 0.240, "seconds": 300.0},
    "Fluo-N2DL-HeLa": {"pixel_um": 0.645, "seconds": 1800.0},
}
# Keep imperfect challenge detections distinct from silver and gold references.
LAYERS = {
    "ctc_err_seg": ("ERR_SEG", "mask", "Imperfect segmentation supplied for the linking benchmark"),
    "ctc_st_segmentation": ("ST/SEG", "man_seg", "Silver-truth segmentation"),
    "ctc_gt_segmentation": ("GT/SEG", "man_seg", "Gold-truth segmentation; may cover only selected frames"),
    "ctc_tra_markers": ("GT/TRA", "man_track", "Gold tracking markers, not necessarily complete nuclear masks"),
}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def member_index(archive, pattern):
    found = {}
    for name in archive.namelist():
        match = re.fullmatch(pattern, name)
        if match:
            frame = int(match[1])
            if frame in found:
                raise ValueError(f"Duplicate frame {frame}: {found[frame]} and {name}")
            found[frame] = name
    return dict(sorted(found.items()))


def tiff_header(archive, member):
    with archive.open(member) as stream, tifffile.TiffFile(stream) as image:
        series = image.series[0]
        if len(image.series) != 1 or series.ndim != 2:
            raise ValueError(f"Expected a single 2D grayscale TIFF: {member}")
        return tuple(series.shape), np.dtype(series.dtype)


def read_plane(archive, member):
    with archive.open(member) as stream:
        plane = tifffile.imread(stream)
    if plane.ndim != 2:
        raise ValueError(f"Expected a 2D plane: {member}")
    return plane


def inspect_archive(path, dataset, sequences=("01", "02")):
    """Read TIFF headers and member names only; do not materialize pixel arrays."""
    if dataset not in CATALOG:
        raise ValueError("Dataset has no verified acquisition calibration")
    plans = []
    with ZipFile(path) as archive:
        if len(set(archive.namelist())) != len(archive.namelist()):
            raise ValueError("Duplicate ZIP member names")
        for seq in sequences:
            if seq not in {"01", "02"}:
                raise ValueError("Sequence must be 01 or 02")
            base = rf"(?:{re.escape(dataset)}/)?{seq}"
            images = member_index(archive, base + r"/t(\d+)\.tiff?")
            if len(images) < 2 or list(images) != list(range(len(images))):
                raise ValueError(f"Sequence {seq} must contain contiguous frames starting at zero")
            shape, dtype = tiff_header(archive, next(iter(images.values())))
            if dtype.kind not in "uif" or dtype.itemsize > 8:
                raise ValueError(f"Unsupported image dtype: {dtype}")
            for member in images.values():
                if tiff_header(archive, member) != (shape, dtype):
                    raise ValueError(f"Image shape/dtype changes at {member}")
            layers = {}
            for label, (folder, prefix, semantics) in LAYERS.items():
                index = member_index(archive, base + "_" + re.escape(folder) + "/" + prefix + r"(\d+)\.tiff?")
                if not index:
                    continue
                if not set(index) <= set(images):
                    raise ValueError(f"Annotation timepoints outside sequence: {label}")
                label_dtype = tiff_header(archive, next(iter(index.values())))[1]
                if label_dtype.kind not in "ui":
                    raise ValueError(f"Instance labels must have integer dtype: {label}")
                for member in index.values():
                    if tiff_header(archive, member) != (shape, label_dtype):
                        raise ValueError(f"Annotation shape/dtype differs: {member}")
                layers[label] = {"members": index, "dtype": str(label_dtype),
                                 "complete": set(index) == set(images), "semantics": semantics}
            if not layers:
                raise ValueError(f"No recognized CTC annotations in sequence {seq}")
            # Never extract arbitrary ZIP paths to the filesystem.
            lineage = [name for name in archive.namelist()
                       if re.fullmatch(base + r"_GT/TRA/man_track\.txt", name)]
            plans.append({"sequence": seq, "images": images, "shape_yx": shape,
                          "dtype": str(dtype), "layers": layers,
                          "lineage_member": lineage[0] if lineage else None})
    return plans


def multiscales(name, calibration):
    return [{"version": "0.4", "name": name,
             "axes": [{"name": "t", "type": "time", "unit": "second"},
                      {"name": "c", "type": "channel"},
                      {"name": "y", "type": "space", "unit": "micrometer"},
                      {"name": "x", "type": "space", "unit": "micrometer"}],
             "datasets": [{"path": "0", "coordinateTransformations": [
                 {"type": "scale", "scale": [calibration["seconds"], 1.0,
                                               calibration["pixel_um"], calibration["pixel_um"]]}]}]}]


def create_image(group, name, shape, dtype, calibration):
    group.attrs["multiscales"] = multiscales(name, calibration)
    array = group.create_array("0", shape=shape, dtype=dtype,
                               chunks=(1, 1, min(256, shape[-2]), min(256, shape[-1])),
                               compressor=Blosc(cname="zstd", clevel=3, shuffle=Blosc.BITSHUFFLE),
                               chunk_key_encoding={"name": "v2", "configuration": {"separator": "/"}})
    array.attrs["_ARRAY_DIMENSIONS"] = list("tcyx")
    return array


def write_planes(archive, array, members, *, labels=False):
    low, high = float("inf"), float("-inf")
    for frame, member in members.items():
        plane = read_plane(archive, member)
        if labels and np.any(plane < 0):
            raise ValueError(f"Negative label ID: {member}")
        if not np.isfinite(plane).all():
            raise ValueError(f"Nonfinite pixels: {member}")
        array[frame, 0] = plane
        if not np.array_equal(np.asarray(array[frame, 0]), plane):
            raise ValueError(f"Pixel/label round-trip verification failed: {member}")
        low, high = min(low, float(plane.min())), max(high, float(plane.max()))
    return low, high


def convert_archive(path, output, dataset, sequences=("01", "02")):
    """Convert full sequences, publishing only after exact per-frame verification."""
    path, output = Path(path), Path(output)
    plans = inspect_archive(path, dataset, sequences)
    destinations = [output / f"{dataset}_{plan['sequence']}.ome.zarr" for plan in plans]
    if len(set(destinations)) != len(destinations) or any(p.exists() for p in destinations):
        raise FileExistsError("A destination exists or a sequence was selected twice")
    calibration = CATALOG[dataset]
    archive_hash = file_hash(path)
    output.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        with ZipFile(path) as archive:
            for plan, destination in zip(plans, destinations):
                stage = output / f".partial-{dataset}-{plan['sequence']}-{uuid4().hex}"
                staged.append((stage, destination))
                root = zarr.open_group(str(stage), mode="w", zarr_format=2)
                shape = (len(plan["images"]), 1, *plan["shape_yx"])
                source = create_image(root, destination.stem, shape, plan["dtype"], calibration)
                low, high = write_planes(archive, source, plan["images"])
                root.attrs["omero"] = {"channels": [{"label": "Nuclei", "color": "FFFFFF", "active": True,
                    "window": {"min": low, "max": max(high, low + 1), "start": low, "end": max(high, low + 1)}}]}
                overlay_names = []
                for label, layer in plan["layers"].items():
                    if layer["complete"]:
                        group = root.create_group(f"labels/{label}")
                        array = create_image(group, label, shape, layer["dtype"], calibration)
                        write_planes(archive, array, layer["members"], labels=True)
                        group.attrs["image-label"] = {"version": "0.4", "source": {"image": "../../"}}
                        group.attrs["ctc"] = {"semantics": layer["semantics"], "source_members": layer["members"]}
                        overlay_names.append(label)
                    else:
                        group = root.create_group(f"ctc_annotations/{label}")
                        group.attrs.update({"semantics": layer["semantics"], "frame_indices": list(layer["members"]),
                                            "missing_frames": "unannotated; no mask is synthesized",
                                            "source_members": layer["members"]})
                        for frame, member in layer["members"].items():
                            plane = read_plane(archive, member)
                            if np.any(plane < 0):
                                raise ValueError(f"Negative label ID: {member}")
                            array = group.create_array(f"frame_{frame:06d}", shape=plane.shape, dtype=layer["dtype"],
                                chunks=(min(256, plane.shape[0]), min(256, plane.shape[1])),
                                compressor=Blosc(cname="zstd", clevel=3, shuffle=Blosc.BITSHUFFLE))
                            array[:] = plane
                            array.attrs.update({"_ARRAY_DIMENSIONS": ["y", "x"], "source_timepoint": frame,
                                                "time_seconds": frame * calibration["seconds"]})
                            if not np.array_equal(np.asarray(array), plane):
                                raise ValueError(f"Sparse-label round-trip verification failed: {member}")
                if overlay_names:
                    root["labels"].attrs["labels"] = overlay_names
                lineage = archive.read(plan["lineage_member"]).decode("utf-8-sig") if plan["lineage_member"] else None
                root.attrs["ctc"] = {"schema_version": 1, "dataset": dataset, "sequence": plan["sequence"],
                    "archive_name": path.name, "archive_sha256": archive_hash, "calibration": calibration,
                    "calibration_source": SOURCE, "frame_indices": list(plan["images"]),
                    "source_members": plan["images"], "tracking_reference_text": lineage,
                    "tracking_reference_columns": ["label", "first_frame", "last_frame", "parent_label"],
                    "sparse_annotations": [name for name, layer in plan["layers"].items() if not layer["complete"]],
                    "verification": "Every image/annotation plane read back and compared exactly",
                    "training_overlap": "Pretrained CTC models may have seen these training sequences"}
                root.attrs["conversion_status"] = "complete"
                print(f"Verified {destination.name}: {shape[0]} frames; overlays {overlay_names}", flush=True)
        for stage, destination in staged:
            if destination.exists():
                raise FileExistsError(destination)
        for stage, destination in staged:
            stage.rename(destination)
    except Exception as error:
        for stage, _ in staged:
            if stage.exists():
                (stage / "FAILED.json").write_text(json.dumps({"error": str(error)}), encoding="utf-8")
        raise
    return destinations


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--dataset", choices=list(CATALOG), required=True)
    parser.add_argument("--output", type=Path, help="Required for conversion; existing stores are refused")
    parser.add_argument("--sequences", nargs="+", choices=["01", "02"], default=["01", "02"])
    parser.add_argument("--inspect", action="store_true", help="Report TIFF headers and frame coverage; write nothing")
    args = parser.parse_args(argv)
    if args.inspect:
        print(json.dumps(inspect_archive(args.archive, args.dataset, args.sequences), indent=2))
    elif args.output is None:
        parser.error("--output is required unless --inspect is used")
    else:
        convert_archive(args.archive, args.output, args.dataset, args.sequences)


if __name__ == "__main__":
    main()
