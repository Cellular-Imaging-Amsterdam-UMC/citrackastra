import json
import sqlite3
from pathlib import Path

import networkx as nx
import numpy as np
import pytest
import zarr

from citrackastra.cli import parser
from citrackastra.models import sha256, verify_model
from citrackastra.ngff import inspect_image, sequence
from citrackastra.workflow import Settings, run_store


def image(root, path="", dimensions=2, order="tczyx", calibrated=True, units="micrometer"):
    path = path or "A/1/0"
    well_path, field_path = path.rsplit("/", 1)
    plate = root.attrs.get("plate", {"version": "0.4", "rows": [{"name": "A"}], "columns": [{"name": "1"}], "wells": []})
    if well_path not in [w["path"] for w in plate["wells"]]:
        plate["wells"].append({"path": well_path, "rowIndex": 0, "columnIndex": 0})
    root.attrs["plate"] = plate
    well = root.require_group(well_path)
    description = well.attrs.get("well", {"version": "0.4", "images": []})
    if field_path not in [i["path"] for i in description["images"]]:
        description["images"].append({"path": field_path})
    well.attrs["well"] = description
    group = root.require_group(path)
    sizes = {"t": 3, "c": 2, "z": 2 if dimensions == 3 else 1, "y": 16, "x": 20}
    canonical = np.arange(np.prod([sizes[a] for a in "tczyx"]), dtype="u2").reshape(tuple(sizes[a] for a in "tczyx"))
    source = np.transpose(canonical, ["tczyx".index(a) for a in order])
    definitions = [{"name": a, "type": "time" if a == "t" else "channel" if a == "c" else "space", **({"unit": "second"} if a == "t" else {"unit": units} if a in "zyx" and calibrated else {})} for a in order]
    scales = {"t": 5., "c": 1., "z": 2., "y": .5, "x": .25}
    offsets = {"t": 10., "c": 0., "z": 3., "y": 7., "x": 11.}
    ms = {"version": "0.4", "axes": definitions, "datasets": [{"path": "0", "coordinateTransformations": [{"type": "scale", "scale": [scales[a] for a in order]}, {"type": "translation", "translation": [offsets[a] for a in order]}]}]}
    group.create_array("0", data=source)
    group.attrs["multiscales"] = [ms]
    masks = np.zeros((3, 1, sizes["z"], 16, 20), dtype="u4")
    for t in range(3):
        masks[t, 0, :, 3:5, 4 + t:6 + t] = 7 + t
    labels = group.create_group("labels/instances")
    labels.create_array("0", data=masks)
    label_ms = json.loads(json.dumps(ms))
    label_ms["axes"] = [next(d for d in definitions if d["name"] == a) for a in "tczyx"]
    label_ms["datasets"][0]["coordinateTransformations"] = [{"type": "scale", "scale": [scales[a] for a in "tczyx"]}, {"type": "translation", "translation": [offsets[a] for a in "tczyx"]}]
    labels.attrs["multiscales"] = [label_ms]
    group["labels"].attrs["labels"] = ["instances"]
    return group, canonical, masks


class Model:
    def track(self, imgs, masks, **kwargs):
        graph = nx.DiGraph()
        previous = None
        for t in range(len(masks)):
            for value in np.unique(masks[t]):
                if value:
                    node = (t, int(value))
                    graph.add_node(node, time=t, label=int(value))
                    if previous is not None:
                        graph.add_edge(previous, node, weight=.99)
                    previous = node
        return graph, masks


@pytest.mark.parametrize("dimensions", [2])
@pytest.mark.parametrize("order", ["tczyx", "ctzyx", "tcyxz"])
def test_field_roundtrip_retains_pixels_labels_and_physical_positions(tmp_path, dimensions, order):
    source = tmp_path / "source.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    group, canonical, masks = image(root, dimensions=dimensions, order=order)
    result = run_store(source, tmp_path / "out", Settings(model="ctc"), model=Model())
    output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")
    output_field = output["A/1/0"]
    np.testing.assert_array_equal(output_field["0"][:], group["0"][:])
    np.testing.assert_array_equal(output_field["labels/instances/0"][:], masks)
    assert output_field["labels/instances_tracks/0"].shape == (3, 16, 20)
    assert "instances_tracks" not in group["labels"]
    with sqlite3.connect(result / "tracking.sqlite") as db:
        assert db.execute("SELECT observation_count,path_length_um,displacement_um,mean_speed FROM tracks").fetchone() == pytest.approx((3, .5, .5, .05))
        physical = db.execute("SELECT y_um,x_um,time FROM observations ORDER BY timepoint LIMIT 1").fetchone()
        assert physical == pytest.approx((8.75, 12.125, 10.))
        assert db.execute("SELECT DISTINCT speed_unit FROM tracks").fetchone() == ("micrometer/second",)
    assert (result / "observations.csv").is_file()
    assert json.loads((result / "provenance.json").read_text())["status"] == "complete"


def test_hcs_fields_never_link_to_each_other_and_preserve_plate_metadata(tmp_path):
    source = tmp_path / "plate.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    root.attrs["plate"] = {"version": "0.4", "wells": [{"path": "A/1"}]}
    root.create_group("A/1").attrs["well"] = {"images": [{"path": "0"}, {"path": "1"}]}
    image(root, "A/1/0")
    image(root, "A/1/1")
    result = run_store(source, tmp_path / "out", Settings(), model=Model())
    output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")
    assert output.attrs["plate"] == root.attrs["plate"]
    with sqlite3.connect(result / "tracking.sqlite") as db:
        assert db.execute("SELECT count(*),count(DISTINCT field_id) FROM tracks").fetchone() == (2, 2)
        assert db.execute("SELECT count(*) FROM observations").fetchone() == (6,)


def test_all_fields_are_checked_before_model_or_output_creation(tmp_path):
    source = tmp_path / "plate.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    image(root, "A/1/0")
    image(root, "A/1/1", calibrated=False)
    with pytest.raises(ValueError, match="calibrated"):
        run_store(source, tmp_path / "out", Settings())
    assert not (tmp_path / "out").exists()


def test_volumetric_images_are_rejected_without_projection(tmp_path):
    source = tmp_path / "source.ome.zarr"
    image(zarr.open_group(str(source), mode="w", zarr_format=2), dimensions=3)
    with pytest.raises(ValueError, match="Only 2D"):
        run_store(source, tmp_path / "out", Settings(model="ctc"))
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("invalid", ["shape", "scale", "units", "negative", "missing_labels", "no_time"])
def test_rejects_incompatible_or_uncalibrated_inputs(tmp_path, invalid):
    source = tmp_path / "source.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    group, _, _ = image(root)
    label = group["labels/instances"]
    ms = label.attrs["multiscales"]
    if invalid == "shape":
        label["0"].resize((2, 1, 1, 16, 20))
    elif invalid == "scale":
        ms[0]["datasets"][0]["coordinateTransformations"][0]["scale"][-1] = 0
        label.attrs["multiscales"] = ms
    elif invalid == "units":
        ms[0]["axes"][-1]["unit"] = "nanometer"
        label.attrs["multiscales"] = ms
    elif invalid == "negative":
        original = label["0"][:].astype("i4")
        original[0, 0, 0, 0, 0] = -1
        del label["0"]
        label.create_array("0", data=original)
    elif invalid == "missing_labels":
        del group["labels"]
    else:
        group["0"].resize((1, 2, 1, 16, 20))
    with pytest.raises(ValueError):
        run_store(source, tmp_path / "out", Settings(), model=Model())


def test_refuses_overwrite_and_nested_outputs(tmp_path):
    source = tmp_path / "source.ome.zarr"
    image(zarr.open_group(str(source), mode="w", zarr_format=2))
    run_store(source, tmp_path / "out", Settings(), model=Model())
    with pytest.raises(FileExistsError):
        run_store(source, tmp_path / "out", Settings(), model=Model())
    with pytest.raises(ValueError, match="outside"):
        run_store(source, source / "out", Settings(), model=Model())


def test_memory_guard_precedes_loading(tmp_path):
    source = tmp_path / "source.ome.zarr"
    image(zarr.open_group(str(source), mode="w", zarr_format=2))
    with pytest.raises(MemoryError):
        run_store(source, tmp_path / "out", Settings(max_memory_gb=.000001))


def test_missing_time_units_are_frames_with_no_fabricated_seconds(tmp_path):
    source = tmp_path / "source.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    field, _, _ = image(root)
    for group in [field, field["labels/instances"]]:
        ms = group.attrs["multiscales"]
        ms[0]["axes"][0].pop("unit")
        group.attrs["multiscales"] = ms
    result = run_store(source, tmp_path / "out", Settings(), model=Model())
    with sqlite3.connect(result / "tracking.sqlite") as db:
        assert db.execute("SELECT seconds_per_frame FROM fields").fetchone() == (None,)
        assert db.execute("SELECT mean_speed,speed_unit FROM tracks").fetchone() == (.25, "micrometer/frame")


def test_ordered_global_transforms_and_unit_conversion(tmp_path):
    root = zarr.open_group(str(tmp_path / "a.zarr"), mode="w", zarr_format=2)
    group, _, _ = image(root, units="nanometer")
    ms = group.attrs["multiscales"]
    ms[0]["coordinateTransformations"] = [{"type": "scale", "scale": [1, 1, 1, 2, 3]}, {"type": "translation", "translation": [0, 0, 0, 5, 7]}]
    group.attrs["multiscales"] = ms
    info = inspect_image(group)
    assert info.scale == pytest.approx([.001, .00075])
    assert info.offset == pytest.approx([.019, .040])


def test_model_cache_detects_corruption(tmp_path):
    files = {}
    for name in ["config.yaml", "train_config.yaml", "model.pt"]:
        (tmp_path / name).write_text("fixture")
        files[name] = sha256(tmp_path / name)
    (tmp_path / "download.json").write_text(json.dumps({"files": files}))
    verify_model(tmp_path)
    (tmp_path / "model.pt").write_text("modified")
    with pytest.raises(ValueError, match="checksum"):
        verify_model(tmp_path)


def test_cli_uses_numeric_values_and_rejects_unknown_options():
    args = parser().parse_args(["--channel", "2", "--max-memory-gb", "3", "--batch-size", "4"])
    assert (args.channel, args.max_memory_gb, args.batch_size) == (2, 3., 4)
    with pytest.raises(SystemExit):
        parser().parse_args(["--unknown-option", "true"])
    assert parser().parse_args(["--movie", "false"]).movie is False
    assert parser().parse_args(["--movie"]).movie is True


def test_standalone_time_series_is_rejected(tmp_path):
    source = tmp_path / "standalone.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    image(root)
    del root.attrs["plate"]
    with pytest.raises(ValueError, match="HCS plate"):
        run_store(source, tmp_path / "out", Settings())
