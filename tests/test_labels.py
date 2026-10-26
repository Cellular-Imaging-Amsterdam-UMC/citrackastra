import copy
import sqlite3

import numpy as np
import pytest
import zarr

from citrackastra.cli import main, parser
from citrackastra.ngff import label_names
from citrackastra.workflow import Settings, run_store
from test_workflow import Model, image


def add_label(field, name="Other_Nuclei"):
    original = field["labels/instances"]
    label = field.create_group("labels/" + name)
    masks = original["0"][:]
    masks[masks > 0] += 100
    label.create_array("0", data=masks)
    label.attrs.update(copy.deepcopy(dict(original.attrs)))
    return masks


@pytest.mark.parametrize("selection,expected", [("", "Other_Nuclei"), ("  ", "Other_Nuclei"), (None, "Other_Nuclei"), ("oThEr_nUcLeI", "Other_Nuclei"), ("InStAnCeS", "instances")])
def test_one_label_uses_registry_order_or_case_insensitive_name(tmp_path, selection, expected):
    source = tmp_path / "multi-label.ome.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    field, pixels, original_masks = image(root)
    other_masks = add_label(field)
    # Declared order deliberately differs from alphabetical order.
    field["labels"].attrs["labels"] = ["Other_Nuclei", "instances"]
    result = run_store(source, tmp_path / "out", Settings(labels=selection), model=Model())
    output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")["A/1/0"]
    np.testing.assert_array_equal(output["0"][:], pixels)
    np.testing.assert_array_equal(output["labels/instances/0"][:], original_masks)
    np.testing.assert_array_equal(output["labels/Other_Nuclei/0"][:], other_masks)
    assert output["labels"].attrs["labels"] == ["Other_Nuclei", "instances", expected + "_tracks"]
    assert len(list(output["labels"].groups())) == 3
    with sqlite3.connect(result / "tracking.sqlite") as db:
        assert db.execute("SELECT source_label,output_label FROM fields").fetchall() == [(expected, expected + "_tracks")]
        values = [r[0] for r in db.execute("SELECT source_label FROM observations ORDER BY timepoint")]
        assert values == ([107, 108, 109] if expected == "Other_Nuclei" else [7, 8, 9])


def test_default_settings_select_only_the_first_registered_label(tmp_path):
    field, _, _ = image(zarr.open_group(str(tmp_path / "p.zarr"), mode="w", zarr_format=2))
    add_label(field)
    assert Settings().labels == ""
    assert label_names(field, Settings().labels) == ["instances"]


def test_registry_free_legacy_store_uses_deterministic_alphabetical_order(tmp_path):
    field, _, _ = image(zarr.open_group(str(tmp_path / "p.zarr"), mode="w", zarr_format=2))
    add_label(field, "Alpha")
    del field["labels"].attrs["labels"]
    assert label_names(field) == ["Alpha"]


@pytest.mark.parametrize("requested", ["missing", "all", "instances,Other_Nuclei"])
def test_unknown_label_never_falls_back_or_selects_multiple_groups(tmp_path, requested):
    source = tmp_path / "p.zarr"
    field, _, _ = image(zarr.open_group(str(source), mode="w", zarr_format=2))
    add_label(field)
    field["labels"].attrs["labels"] = ["instances", "Other_Nuclei"]
    with pytest.raises(ValueError, match="available:"):
        run_store(source, tmp_path / "out", Settings(labels=requested))
    assert not (tmp_path / "out").exists()


def test_all_is_a_literal_label_name_and_case_collisions_are_rejected(tmp_path):
    field, _, _ = image(zarr.open_group(str(tmp_path / "p.zarr"), mode="w", zarr_format=2))
    add_label(field, "all")
    field["labels"].attrs["labels"] = ["instances", "all"]
    assert label_names(field, "ALL") == ["all"]
    field["labels"].attrs["labels"] = ["instances", "INSTANCES"]
    with pytest.raises(ValueError, match="Ambiguous case-insensitive"):
        label_names(field, "instances")


def test_missing_requested_label_in_later_field_fails_before_any_inference(tmp_path):
    source = tmp_path / "p.zarr"
    root = zarr.open_group(str(source), mode="w", zarr_format=2)
    field, _, _ = image(root)
    add_label(field)
    field["labels"].attrs["labels"] = ["instances", "Other_Nuclei"]
    image(root, "A/1/1")
    with pytest.raises(ValueError, match="Unknown or missing"):
        run_store(source, tmp_path / "out", Settings(labels="other_nuclei"))
    assert not (tmp_path / "out").exists()


def test_nested_registered_label_has_correct_source_reference(tmp_path):
    source = tmp_path / "p.zarr"
    field, _, _ = image(zarr.open_group(str(source), mode="w", zarr_format=2))
    add_label(field, "nested/Nuclei")
    field["labels"].attrs["labels"] = ["nested/Nuclei", "instances"]
    result = run_store(source, tmp_path / "out", Settings(labels="NESTED/NUCLEI"), model=Model())
    output = zarr.open_group(str(next(result.glob("*.ome.zarr"))), mode="r")
    assert output["A/1/0/labels/nested/Nuclei_tracks"].attrs["image-label"]["source"]["image"] == "../../../"


def test_cli_supports_singular_name_and_legacy_alias():
    assert parser().parse_args(["--label", "Nuclei"]).labels == "Nuclei"
    assert parser().parse_args(["--labels", "Nuclei"]).labels == "Nuclei"
    with pytest.raises(SystemExit):
        main(["--parameters", '{"labels": 42}'])


def test_zarr_v3_still_requires_conversion_before_tracking(tmp_path):
    source = tmp_path / "p.zarr"
    zarr.open_group(str(source), mode="w", zarr_format=3)
    with pytest.raises(ValueError, match="NGFF 0.4 / Zarr v2"):
        run_store(source, tmp_path / "out", Settings())
    assert not (tmp_path / "out").exists()
