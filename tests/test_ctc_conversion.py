import io
from zipfile import ZipFile

import numpy as np
import pytest
import zarr
import tifffile

from citrackastra.ngff import inspect_image, label_names
from tools.convert_ctc_ngff import convert_archive, inspect_archive


def make_archive(path, *, missing_source=False, bad_label_shape=False, sequences=("01",)):
    source = np.arange(3 * 6 * 8, dtype=np.uint16).reshape(3, 6, 8)
    labels = np.zeros((3, 6, 8), dtype=np.uint32)
    labels[:, 2:4, 3:5] = 70001

    def put(archive, name, plane):
        stream = io.BytesIO()
        tifffile.imwrite(stream, plane, photometric="minisblack")
        archive.writestr("Fluo-N2DH-GOWT1/" + name, stream.getvalue())

    with ZipFile(path, "w") as archive:
        for sequence in sequences:
            for t in range(3):
                if not (missing_source and t == 1):
                    put(archive, f"{sequence}/t{t:03d}.tif", source[t])
                put(archive, f"{sequence}_GT/TRA/man_track{t:03d}.tif", labels[t])
                plane = labels[t, :-1] if bad_label_shape and t == 1 else labels[t]
                put(archive, f"{sequence}_ERR_SEG/mask{t:03d}.tif", plane)
            # Only one frame was segmented manually: two frames are unannotated.
            put(archive, f"{sequence}_GT/SEG/man_seg002.tif", labels[2])
            archive.writestr(f"Fluo-N2DH-GOWT1/{sequence}_GT/TRA/man_track.txt", "70001 0 2 0\n")
    return source, labels


def test_full_sequence_exact_values_native_dtype_and_sparse_annotation_coverage(tmp_path):
    archive = tmp_path / "source.zip"
    source, labels = make_archive(archive)
    stores = convert_archive(archive, tmp_path / "out", "Fluo-N2DH-GOWT1", ("01",))
    root = zarr.open_group(str(stores[0]), mode="r")
    assert root.metadata.zarr_format == 2
    assert "plate" not in root.attrs
    assert root.attrs["multiscales"][0]["version"] == "0.4"
    assert np.array_equal(root["0"][:, 0], source)
    assert root["0"].dtype == source.dtype
    assert root["0"].chunks[0] == 1
    assert root["labels"].attrs["labels"] == ["ctc_err_seg", "ctc_tra_markers"]
    assert label_names(root) == ["ctc_err_seg"]
    for label in root["labels"].attrs["labels"]:
        assert np.array_equal(root[f"labels/{label}/0"][:, 0], labels)
        assert root[f"labels/{label}/0"].dtype == labels.dtype
        assert root[f"labels/{label}"].attrs["image-label"]["source"]["image"] == "../../"
    sparse = root["ctc_annotations/ctc_gt_segmentation"]
    assert sparse.attrs["frame_indices"] == [2]
    assert set(sparse.array_keys()) == {"frame_000002"}
    assert np.array_equal(sparse["frame_000002"][:], labels[2])
    assert "ctc_gt_segmentation" not in root["labels"].attrs["labels"]
    assert root.attrs["ctc"]["tracking_reference_text"] == "70001 0 2 0\n"
    info = inspect_image(root)
    assert info.dimensions == 2
    assert info.seconds == 300
    assert np.allclose(info.scale, [0.240, 0.240])
    # Reader compatibility is checked without running any tracking model.
    assert root.attrs["conversion_status"] == "complete"


def test_sequences_remain_independent_and_existing_destinations_are_refused(tmp_path):
    archive = tmp_path / "source.zip"
    make_archive(archive, sequences=("01", "02"))
    stores = convert_archive(archive, tmp_path / "out", "Fluo-N2DH-GOWT1")
    assert len(stores) == 2
    assert [zarr.open_group(str(p), mode="r").attrs["ctc"]["sequence"] for p in stores] == ["01", "02"]
    with pytest.raises(FileExistsError):
        convert_archive(archive, tmp_path / "out", "Fluo-N2DH-GOWT1")


@pytest.mark.parametrize("options,match", [
    ({"missing_source": True}, "contiguous frames"),
    ({"bad_label_shape": True}, "shape/dtype differs"),
])
def test_invalid_inputs_fail_before_any_output_is_written(tmp_path, options, match):
    archive = tmp_path / "source.zip"
    make_archive(archive, **options)
    with pytest.raises(ValueError, match=match):
        convert_archive(archive, tmp_path / "out", "Fluo-N2DH-GOWT1", ("01",))
    assert not (tmp_path / "out").exists()


def test_inspection_only_reads_headers_and_keeps_unknown_calibration_rejected(tmp_path, monkeypatch):
    archive = tmp_path / "source.zip"
    make_archive(archive)
    monkeypatch.setattr("tools.convert_ctc_ngff.read_plane", lambda *args: pytest.fail("Inspection read pixels"))
    plan = inspect_archive(archive, "Fluo-N2DH-GOWT1", ("01",))[0]
    assert len(plan["images"]) == 3
    assert not plan["layers"]["ctc_gt_segmentation"]["complete"]
    with pytest.raises(ValueError, match="calibration"):
        inspect_archive(archive, "unknown", ("01",))
