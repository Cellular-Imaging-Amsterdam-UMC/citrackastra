import json
import shutil
import sqlite3

import dask
import dask.array as da
import numpy as np
import pytest
import zarr

from citrackastra.ngff import inspect_image, sequence
from citrackastra.streaming import normalize_sequence, working_bytes, retain_unlinked_instances
from citrackastra.workflow import Settings, run_store
from test_workflow import Model, image


@pytest.mark.parametrize("shape", [(7, 20, 30), (8, 272, 280)])
def test_lazy_normalization_exactly_matches_upstream_global_percentiles(shape):
    from trackastra.utils import normalize
    rng = np.random.default_rng(42)
    values = rng.normal(size=shape).astype("f4")
    values *= np.arange(1, shape[0] + 1)[:, None, None]
    lazy = da.from_array(values, chunks=(1, *shape[1:]))
    np.testing.assert_array_equal(normalize_sequence(lazy).compute(scheduler="synchronous"), normalize(values))


def test_standalone_full_roundtrip_preserves_pixels_labels_and_root_paths(tmp_path):
    fixture = tmp_path / "plate.zarr"
    root = zarr.open_group(str(fixture), mode="w", zarr_format=2)
    field, pixels, masks = image(root)
    source = tmp_path / "standalone.ome.zarr"
    shutil.copytree(fixture / field.path, source)
    result = run_store(source, tmp_path / "out", Settings(), model=Model())
    output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")
    np.testing.assert_array_equal(output["0"][:], pixels)
    np.testing.assert_array_equal(output["labels/instances/0"][:], masks)
    assert "instances_tracks" not in zarr.open_group(str(source), mode="r")["labels"]
    with sqlite3.connect(result / "tracking.sqlite") as db:
        assert db.execute("SELECT image_path FROM fields").fetchone() == ("",)
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone() == (3,)
        assert db.execute("SELECT COUNT(*) FROM links").fetchone() == (2,)
    report = json.loads((result / "provenance.json").read_text())
    assert report["execution"]["split_tracking"] is False
    assert output.attrs["biomero"]["result"] == {
        "schema_version": 1, "output_store_uuid": report["output_store_uuid"]}


def test_lazy_reads_retain_axes_and_do_not_decode_full_sequence(tmp_path, monkeypatch):
    root = zarr.open_group(str(tmp_path / "source.zarr"), mode="w", zarr_format=2)
    field, pixels, _ = image(root, order="ctzyx")
    info = inspect_image(field)
    lazy = sequence(field, info, channel=2, lazy=True)
    assert isinstance(lazy, da.Array)
    assert all(size == 1 for size in lazy.chunks[0])
    with dask.config.set(scheduler="synchronous"):
        np.testing.assert_array_equal(lazy[1].compute(), pixels[1, 1, 0])


def test_long_timelapse_budget_counts_frame_buffers_and_same_global_sample():
    estimate = working_bytes((700, 1, 1, 1000, 1000), list("tczyx"), 4)
    assert 1024**3 < estimate < 4 * 1024**3


def test_isolated_detections_survive_without_inventing_tracking_links():
    import networkx as nx
    from trackastra.tracking import graph_to_ctc
    masks = np.zeros((3, 12, 12), dtype="u4")
    masks[0, 1:3, 1:3] = 7
    masks[1, 1:3, 1:3] = 8
    masks[2, 8:10, 8:10] = 20
    graph = nx.DiGraph()
    graph.add_node(0, time=0, label=7, coords=(1.5, 1.5))
    graph.add_node(1, time=1, label=8, coords=(1.5, 1.5))
    graph.add_edge(0, 1, weight=.9)
    lazy = da.from_array(masks, chunks=(1, 12, 12))
    assert retain_unlinked_instances(graph, lazy) == 1
    assert set(graph.edges) == {(0, 1)}
    with dask.config.set(scheduler="synchronous"):
        table, tracked = graph_to_ctc(graph, lazy)
        assert len(table) == 2
        assert np.count_nonzero(tracked[2].compute()) == 4


@pytest.mark.parametrize("invalid", ["static", "volume", "uncalibrated", "mixed_image_plate"])
def test_standalone_validation_keeps_time_z_and_calibration_requirements(tmp_path, invalid):
    fixture = tmp_path / "plate.zarr"
    field, _, _ = image(zarr.open_group(str(fixture), mode="w", zarr_format=2), dimensions=3 if invalid == "volume" else 2)
    source = tmp_path / "image.ome.zarr"
    shutil.copytree(fixture / field.path, source)
    root = zarr.open_group(str(source), mode="a")
    if invalid == "static":
        root["0"].resize((1, 2, 1, 16, 20))
    elif invalid == "uncalibrated":
        ms = root.attrs["multiscales"]
        next(axis for axis in ms[0]["axes"] if axis["name"] == "y").pop("unit")
        root.attrs["multiscales"] = ms
    elif invalid == "mixed_image_plate":
        root.attrs["plate"] = {"version": "0.4", "wells": []}
    with pytest.raises(ValueError):
        run_store(source, tmp_path / "out", Settings(), model=Model())
    assert not (tmp_path / "out").exists()


def test_hcs_wells_and_fields_remain_independent(tmp_path):
    source = tmp_path / "multiwell.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    paths = ["A/1/0", "A/1/1", "B/2/0"]
    for path in paths:
        image(root, path)
    root.attrs["plate"] = {"version": "0.4", "rows": [{"name": "A"}, {"name": "B"}],
                           "columns": [{"name": "1"}, {"name": "2"}],
                           "wells": [{"path": "A/1", "rowIndex": 0, "columnIndex": 0},
                                     {"path": "B/2", "rowIndex": 1, "columnIndex": 1}]}
    result = run_store(source, tmp_path / "out", Settings(), model=Model())
    output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")
    assert output.attrs["plate"] == root.attrs["plate"]
    for path in paths:
        np.testing.assert_array_equal(output[f"{path}/0"][:], root[f"{path}/0"][:])
        np.testing.assert_array_equal(output[f"{path}/labels/instances/0"][:], root[f"{path}/labels/instances/0"][:])
    with sqlite3.connect(result / "tracking.sqlite") as db:
        assert db.execute("SELECT COUNT(DISTINCT field_id),COUNT(*) FROM tracks").fetchone() == (3, 3)
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone() == (9,)
        assert db.execute("SELECT COUNT(*) FROM links").fetchone() == (6,)
