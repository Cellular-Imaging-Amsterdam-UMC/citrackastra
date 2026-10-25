"""Download calibrated CTC training images and write reproducible NGFF smoke inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import tifffile
import zarr
from numcodecs import Blosc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from citrackastra.models import sha256

CATALOG = {
    "Fluo-N2DH-GOWT1": {"pixel_um": .240, "seconds": 300., "description": "GFP-GOWT1 mouse stem-cell nuclei", "zenodo": 15608211},
    "Fluo-N2DH-SIM+": {"pixel_um": .125, "seconds": 1740., "description": "Simulated fluorescent HL60 nuclei", "zenodo": 15608207},
    "PhC-C2DH-U373": {"pixel_um": .65, "seconds": 900., "description": "Phase-contrast glioblastoma-astrocytoma cells", "zenodo": 15608252},
}
SOURCE = "https://celltrackingchallenge.net/2d-datasets/"


def write_store(path, images, masks, *, pixel_um, seconds, provenance):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    if not np.isfinite(pixel_um) or pixel_um <= 0 or not np.isfinite(seconds) or seconds <= 0:
        raise ValueError("Verified positive physical pixel size and frame interval are required")
    if images.shape != masks.shape or images.ndim != 3:
        raise ValueError("The converter requires matching TYX image and instance-mask stacks")
    root = zarr.open_group(str(path), mode="w", zarr_format=2)
    root.attrs["plate"] = {"version": "0.4", "name": path.stem, "rows": [{"name": "A"}], "columns": [{"name": "1"}],
                           "wells": [{"path": "A/1", "rowIndex": 0, "columnIndex": 0}], "field_count": 1}
    root.create_group("A/1").attrs["well"] = {"version": "0.4", "images": [{"path": "0"}]}
    field = root.create_group("A/1/0")
    axes = [{"name": a, "type": "time" if a == "t" else "channel" if a == "c" else "space", **({"unit": "second"} if a == "t" else {"unit": "micrometer"} if a in "zyx" else {})} for a in "tczyx"]
    scale = [seconds, 1., 1., pixel_um, pixel_um]
    ms = {"version": "0.4", "axes": axes, "datasets": [{"path": "0", "coordinateTransformations": [{"type": "scale", "scale": scale}]}]}
    compressor = Blosc(cname="zstd", clevel=3, shuffle=Blosc.BITSHUFFLE)
    for group, data in [(field, images), (field.create_group("labels/instances"), masks)]:
        array = group.create_array("0", data=data[:, None, None], chunks=(1, 1, 1, min(256, data.shape[-2]), min(256, data.shape[-1])), compressor=compressor)
        array.attrs["_ARRAY_DIMENSIONS"] = list("tczyx")
        group.attrs["multiscales"] = [ms]
    field["labels"].attrs["labels"] = ["instances"]
    field["labels/instances"].attrs["image-label"] = {"version": "0.4", "source": {"image": "../../"}}
    field.attrs["omero"] = {"channels": [{"label": "Source", "color": "FFFFFF", "active": True,
                                            "window": {"start": float(images.min()), "end": float(images.max()), "min": float(images.min()), "max": float(images.max())}}]}
    root.attrs["publicdata"] = provenance
    # Embed physical calibration for conventional OMERO/Bio-Formats readers as well.
    ns = "http://www.openmicroscopy.org/Schemas/OME/2016-06"
    ET.register_namespace("", ns)
    ome = ET.Element(f"{{{ns}}}OME")
    image = ET.SubElement(ome, f"{{{ns}}}Image", ID="Image:0", Name=path.stem)
    pixel_type = {"uint8": "uint8", "uint16": "uint16", "uint32": "uint32", "float32": "float"}.get(str(images.dtype))
    if pixel_type is None:
        raise ValueError(f"Unsupported source pixel dtype {images.dtype}")
    pixels = ET.SubElement(image, f"{{{ns}}}Pixels", ID="Pixels:0", DimensionOrder="XYZCT", Type=pixel_type,
                           SizeX=str(images.shape[2]), SizeY=str(images.shape[1]), SizeZ="1", SizeC="1", SizeT=str(images.shape[0]),
                           PhysicalSizeX=str(pixel_um), PhysicalSizeY=str(pixel_um), PhysicalSizeXUnit="µm", PhysicalSizeYUnit="µm",
                           TimeIncrement=str(seconds), TimeIncrementUnit="s")
    ET.SubElement(pixels, f"{{{ns}}}Channel", ID="Channel:0:0", Name="Source", SamplesPerPixel="1")
    ET.SubElement(pixels, f"{{{ns}}}MetadataOnly")
    plate_xml = ET.SubElement(ome, f"{{{ns}}}Plate", ID="Plate:0", Name=path.stem, Rows="1", Columns="1")
    well_xml = ET.SubElement(plate_xml, f"{{{ns}}}Well", ID="Well:0", Row="0", Column="0")
    sample = ET.SubElement(well_xml, f"{{{ns}}}WellSample", ID="WellSample:0", Index="0")
    ET.SubElement(sample, f"{{{ns}}}ImageRef", ID="Image:0")
    (path / "OME").mkdir()
    ET.ElementTree(ome).write(path / "OME/METADATA.ome.xml", encoding="utf-8", xml_declaration=True)
    np.testing.assert_array_equal(field["0"][:, 0, 0], images)
    np.testing.assert_array_equal(field["labels/instances/0"][:, 0, 0], masks)
    return path


def prepare(dataset, directory, frames=6, sequence="01"):
    spec = CATALOG[dataset]
    directory = Path(directory)
    downloads = directory / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / f"{dataset}.zip"
    # The CTC author's Zenodo mirrors remain reachable when its legacy data host times out.
    with urllib.request.urlopen(f"https://zenodo.org/api/records/{spec['zenodo']}", timeout=30) as response:
        record = json.load(response)
    source_file = next(f for f in record["files"] if f["key"] == archive.name)
    url = source_file["links"]["self"]
    if not archive.is_file():
        partial = archive.with_suffix(".zip.partial")
        print(f"Downloading {url}", flush=True)
        with urllib.request.urlopen(url, timeout=180) as response, partial.open("wb") as target:
            shutil.copyfileobj(response, target)
        with zipfile.ZipFile(partial) as check:
            if check.testzip() is not None:
                raise ValueError("Corrupt dataset ZIP")
        partial.rename(archive)
    algorithm, expected = source_file["checksum"].split(":", 1)
    digest = hashlib.new(algorithm)
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError(f"Dataset checksum differs from the source record: {archive}")
    output = directory / "plates" / f"{dataset}-{sequence}-{frames}frames.ome.zarr"
    if output.exists():
        print(f"Retaining existing {output}", flush=True)
        return output
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        images = sorted(n for n in names if re.search(rf"(?:^|/){sequence}/t\d+\.tif$", n))[:frames]
        masks = sorted(n for n in names if re.search(rf"(?:^|/){sequence}_GT/TRA/man_track\d+\.tif$", n))[:frames]
        if len(images) != frames or len(masks) != frames:
            raise ValueError(f"Expected {frames} matched source/TRA frames")
        image_indices = [int(re.search(r"t(\d+)\.tif$", n)[1]) for n in images]
        mask_indices = [int(re.search(r"man_track(\d+)\.tif$", n)[1]) for n in masks]
        if image_indices != mask_indices or image_indices != list(range(frames)):
            raise ValueError("Source and reference frames do not align")
        import io
        pixels = np.stack([tifffile.imread(io.BytesIO(source.read(n))) for n in images])
        labels = np.stack([tifffile.imread(io.BytesIO(source.read(n))) for n in masks])
        lineage_name = next(n for n in names if n.endswith(f"{sequence}_GT/TRA/man_track.txt"))
        lineage = [list(map(int, line.split())) for line in source.read(lineage_name).decode().splitlines() if line.strip()]
        divisions = {}
        for label, start, end, parent in lineage:
            if parent and 0 <= start < frames:
                divisions.setdefault(str(parent), []).append({"label": label, "start_frame": start})
        divisions = [{"parent_label": int(parent), "daughters": daughters} for parent, daughters in divisions.items() if len(daughters) == 2]
        provenance = {"dataset": dataset, "description": spec["description"], "url": url, "source_page": SOURCE,
                      "conditions": "https://celltrackingchallenge.net/datasets/", "archive_sha256": sha256(archive),
                      "zenodo_record": spec["zenodo"], "source_checksum": source_file["checksum"],
                      "license": record["metadata"].get("license", {}),
                      "pixel_um": spec["pixel_um"], "seconds_per_frame": spec["seconds"], "calibration_source": SOURCE,
                      "image_members": images, "mask_members": masks, "frame_range": [0, frames - 1],
                      "reference_lineage": lineage, "reference_divisions": divisions,
                      "label_semantics": "CTC TRA reference markers; not complete cell/nuclear segmentation",
                      "purpose": "Pipeline/model smoke test with reference markers, not an independent accuracy benchmark"}
        output.parent.mkdir(parents=True, exist_ok=True)
        stage = output.with_name(output.name + ".partial")
        write_store(stage, pixels, labels, pixel_um=spec["pixel_um"], seconds=spec["seconds"], provenance=provenance)
        stage.rename(output)
    (output.parent / f"{output.name}.source.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"Verified original pixels and labels: {output}", flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="+", choices=list(CATALOG), default=list(CATALOG))
    parser.add_argument("--publicdata", type=Path, default=Path("publicdata"))
    parser.add_argument("--frames", type=int, default=6)
    parser.add_argument("--sequence", choices=["01", "02"], default="01")
    args = parser.parse_args()
    if args.frames < 2:
        parser.error("At least two frames are required")
    for name in args.datasets:
        prepare(name, args.publicdata, args.frames, args.sequence)


if __name__ == "__main__":
    main()
