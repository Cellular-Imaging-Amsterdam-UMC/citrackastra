"""Create a multi-label selection fixture from the calibrated SIM+ test plate.

The additional Nuclei label contains the same reference-marker geometry with
IDs offset by 1000. It is a selection test, not a new segmentation or benchmark.
"""

import argparse
import copy
import shutil
from pathlib import Path

import numpy as np
import zarr


def prepare(source, destination):
    if destination.exists():
        raise FileExistsError(f"Example already exists: {destination}")
    shutil.copytree(source, destination)
    (destination / ".zmetadata").unlink(missing_ok=True)
    root = zarr.open_group(str(destination), mode="a", use_consolidated=False)
    field = root["A/1/0"]
    label = field.create_group("labels/Nuclei")
    masks = field["labels/instances/0"][:]
    alternate = np.where(masks > 0, masks + 1000, 0).astype(masks.dtype)
    label.create_array("0", data=alternate)
    label.attrs.update(copy.deepcopy(dict(field["labels/instances"].attrs)))
    field["labels"].attrs["labels"] = ["Nuclei", "instances"]
    root.attrs["label_selection_example"] = {"source": source.name, "default_label": "Nuclei", "second_label": "instances", "id_offset": 1000,
                                             "meaning": "Identical reference-marker geometry with alternative IDs; no new biological annotations"}
    print(f"Prepared two-label calibrated example: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("publicdata/plates/Fluo-N2DH-SIM+-01-6frames.ome.zarr"))
    parser.add_argument("--output", type=Path, default=Path("publicdata/plates/Fluo-N2DH-SIM+-01-6frames-multilabel.ome.zarr"))
    args = parser.parse_args()
    prepare(args.source, args.output)
