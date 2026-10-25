import sqlite3
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest
import zarr
from trackastra.tracking import graph_to_ctc

from citrackastra.workflow import SCHEMA, Settings, run_store, write_tables
from test_workflow import image


def test_binary_division_and_gap_have_correct_parentage_and_calibrated_links():
    masks = np.zeros((4, 16, 16), dtype="u4")
    masks[0, 7:9, 7:9] = 11
    masks[1, 5:7, 5:7] = 21
    masks[1, 9:11, 9:11] = 22
    masks[3, 5:7, 6:8] = 31
    graph = nx.DiGraph()
    for node, t, label in [(1, 0, 11), (2, 1, 21), (3, 1, 22), (4, 3, 31)]:
        graph.add_node(node, time=t, label=label)
    graph.add_edges_from([(1, 2), (1, 3), (2, 4)])
    table, tracked = graph_to_ctc(graph, masks)
    info = SimpleNamespace(scale=np.array([.5, .25]), offset=np.array([2., 4.]), seconds=10., time_origin=0., dimensions=2)
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    counts = write_tables(db, 1, graph, masks, tracked, table, info)
    assert counts == {"observations": 4, "tracks": 4, "links": 3}
    assert db.execute("SELECT count(*) FROM tracks WHERE parent_kind='division'").fetchone() == (2,)
    assert db.execute("SELECT count(*) FROM tracks WHERE parent_kind='gap'").fetchone() == (1,)
    gap = db.execute("SELECT distance_um,elapsed,speed FROM links WHERE kind='gap'").fetchone()
    assert gap == pytest.approx((.25, 20., .0125))
    assert db.execute("SELECT count(*) FROM links WHERE kind='division'").fetchone() == (2,)


def test_failed_inference_retains_evidence_without_publishing_completed_output(tmp_path):
    source = tmp_path / "source.ome.zarr"
    image(zarr.open_group(str(source), mode="w", zarr_format=2))
    class FailingModel:
        def track(self, *args, **kwargs):
            raise RuntimeError("Simulated inference failure")
    with pytest.raises(RuntimeError, match="Simulated"):
        run_store(source, tmp_path / "out", Settings(), model=FailingModel())
    assert not (tmp_path / "out/source__citrackastra").exists()
    assert len(list((tmp_path / "out").glob(".source*.partial-*/FAILED.json"))) == 1


def test_empty_sequence_outputs_empty_tables_without_false_objects(tmp_path):
    source = tmp_path / "source.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    group, _, _ = image(root)
    group["labels/instances/0"][:] = 0
    class EmptyModel:
        def track(self, imgs, masks, **kwargs):
            return nx.DiGraph(), masks
    result = run_store(source, tmp_path / "out", Settings(), model=EmptyModel())
    with sqlite3.connect(result / "tracking.sqlite") as db:
        assert db.execute("SELECT count(*) FROM observations").fetchone() == (0,)
