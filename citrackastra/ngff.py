"""NGFF image discovery, axis-aware reads and strict physical calibration."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
import zarr

LENGTH_UM = {"micrometer": 1., "nanometer": 1e-3, "millimeter": 1e3, "meter": 1e6,
             "centimeter": 1e4, "picometer": 1e-6}
TIME_S = {"second": 1., "millisecond": .001, "microsecond": 1e-6,
          "minute": 60., "hour": 3600., "day": 86400.}


def metadata(group):
    attrs = dict(group.attrs)
    return attrs.get("ome", attrs)


def multiscale(group):
    values = metadata(group).get("multiscales", [])
    if not values:
        raise ValueError(f"Missing NGFF multiscales at {group.path}")
    return values[0]


def safe_child(group, path):
    value = PurePosixPath(path)
    if value.is_absolute() or ".." in value.parts or "\\" in path or not value.parts:
        raise ValueError(f"Invalid NGFF child path: {path}")
    return group[path]


def image_groups(root):
    """Resolve only image fields explicitly listed in an NGFF HCS plate."""
    plate = metadata(root).get("plate")
    if not isinstance(plate, dict) or metadata(root).get("multiscales"):
        raise ValueError("Input must be an NGFF HCS plate with 2D time series; standalone images are not supported")
    paths = []
    for item in plate.get("wells", []):
        well = safe_child(root, item["path"])
        description = metadata(well).get("well", {})
        for field in description.get("images", []):
            group = safe_child(well, field["path"])
            if not metadata(group).get("multiscales"):
                raise ValueError(f"Missing NGFF image metadata at {group.path}")
            paths.append(group.path)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("HCS plate must list at least one unique, readable image field")
    return paths


def axes_of(ms, ndim):
    axes = ms.get("axes", [])
    names = [a if isinstance(a, str) else a["name"] for a in axes]
    if len(names) != ndim or len(set(names)) != ndim or set(names) - set("tczyx"):
        raise ValueError("NGFF must declare unique t/c/z/y/x axes matching the array rank")
    if not {"t", "y", "x"} <= set(names):
        raise ValueError("A tracking image requires explicit time, Y and X axes")
    return names


def transform(ms, ndim):
    scale, offset = np.ones(ndim), np.zeros(ndim)
    # NGFF applies dataset transforms first, followed by multiscale transforms.
    for tr in ms["datasets"][0].get("coordinateTransformations", []) + ms.get("coordinateTransformations", []):
        kind = tr.get("type")
        if kind not in {"scale", "translation", "identity"}:
            raise ValueError(f"Unsupported NGFF transform: {kind}")
        if kind == "identity":
            continue
        value = np.asarray(tr[kind], dtype=float)
        if value.shape != (ndim,) or not np.isfinite(value).all():
            raise ValueError("Malformed NGFF coordinate transform")
        if kind == "scale":
            if np.any(value <= 0):
                raise ValueError("NGFF scales must be finite and positive")
            scale *= value
            offset *= value
        else:
            offset += value
    return scale, offset


@dataclass
class ImageInfo:
    path: str
    names: list
    shape: tuple
    ms: dict
    scale: np.ndarray
    offset: np.ndarray
    seconds: float | None
    time_origin: float
    dimensions: int


def inspect_image(group):
    ms = multiscale(group)
    array = safe_child(group, ms["datasets"][0]["path"])
    names = axes_of(ms, array.ndim)
    scale, offset = transform(ms, array.ndim)
    units = {a["name"]: a.get("unit") for a in ms["axes"] if isinstance(a, dict)}
    dimensions = 3 if "z" in names and array.shape[names.index("z")] > 1 else 2
    if dimensions != 2:
        raise ValueError("Only 2D time series and 2D HCS plates are supported; Z must be absent or singleton")
    needed = "zyx" if dimensions == 3 else "yx"
    physical_scale, physical_origin = [], []
    for name in needed:
        if units.get(name) not in LENGTH_UM:
            raise ValueError(f"{group.path or '/'}: calibrated {name.upper()} axis with physical length units is required")
        i = names.index(name)
        # A positive default of 1 is not evidence of a supplied pixel size.
        transforms = ms["datasets"][0].get("coordinateTransformations", []) + ms.get("coordinateTransformations", [])
        if not any(t.get("type") == "scale" for t in transforms):
            raise ValueError("Explicit NGFF scale calibration is required")
        physical_scale.append(scale[i] * LENGTH_UM[units[name]])
        physical_origin.append(offset[i] * LENGTH_UM[units[name]])
    ti = names.index("t")
    seconds = scale[ti] * TIME_S[units["t"]] if units.get("t") in TIME_S else None
    if array.shape[ti] < 2:
        raise ValueError("Tracking requires at least two timepoints")
    return ImageInfo(group.path, names, array.shape, ms, np.array(physical_scale),
                     np.array(physical_origin), seconds, offset[ti] * TIME_S[units["t"]] if seconds else 0., dimensions)


def sequence(group, info, channel=None):
    ms = multiscale(group)
    arr = safe_child(group, ms["datasets"][0]["path"])
    names = axes_of(ms, arr.ndim)
    key, remaining = [], []
    for name, size in zip(names, arr.shape):
        if name == "c":
            index = 0 if channel is None else channel - 1
            if channel is None and size != 1:
                raise ValueError("Instance labels must have exactly one channel")
            if not 0 <= index < size:
                raise ValueError("Selected one-based image channel is outside the input")
            key.append(index)
        elif name == "z" and info.dimensions == 2:
            if size != 1:
                raise ValueError("Image/label Z dimensions do not match")
            key.append(0)
        else:
            key.append(slice(None))
            remaining.append(name)
    target = list("tzyx" if info.dimensions == 3 else "tyx")
    if set(remaining) != set(target):
        raise ValueError("Image and label axes are incompatible")
    return np.transpose(np.asarray(arr[tuple(key)]), [remaining.index(a) for a in target])


def label_names(group, selection=None):
    if "labels" not in group:
        raise ValueError(f"{group.path or '/'} has no instance labels; segment the image first")
    labels = group["labels"]
    registered = metadata(labels).get("labels")
    if registered is None:
        # Legacy stores without a registry have no declared order.
        available = sorted((name for name, child in labels.groups() if metadata(child).get("multiscales")), key=lambda n: (n.casefold(), n))
    else:
        if not isinstance(registered, list) or any(not isinstance(n, str) or not n for n in registered) or len(set(registered)) != len(registered):
            raise ValueError(f"{labels.path}: malformed NGFF label registry")
        available = registered
    if selection is not None and not isinstance(selection, str):
        raise ValueError("Label name must be a string or omitted")
    requested = (selection or "").strip()
    chosen = [name for name in available if name.casefold() == requested.casefold()] if requested else available[:1]
    if len(chosen) != 1:
        reason = "Ambiguous case-insensitive" if len(chosen) > 1 else "Unknown or missing"
        raise ValueError(f"{reason} label {selection!r} at {group.path}; available: {available}")
    try:
        child = safe_child(labels, chosen[0])
    except KeyError as exc:
        raise ValueError(f"Registered label does not exist: {chosen[0]}; available: {available}") from exc
    if not metadata(child).get("multiscales"):
        raise ValueError(f"Selected label is not an NGFF multiscale image: {chosen[0]}")
    return chosen


def check_label_alignment(group, label, info):
    ms = multiscale(label)
    arr = safe_child(label, ms["datasets"][0]["path"])
    names = axes_of(ms, arr.ndim)
    scale, offset = transform(ms, arr.ndim)
    image_scale, image_offset = transform(info.ms, len(info.names))
    label_units = {a["name"]: a.get("unit") for a in ms["axes"] if isinstance(a, dict)}
    image_units = {a["name"]: a.get("unit") for a in info.ms["axes"] if isinstance(a, dict)}
    for axis in set(names) | set(info.names):
        if axis == "c":
            continue
        if axis not in names or axis not in info.names:
            missing_shape = info.shape[info.names.index(axis)] if axis in info.names else arr.shape[names.index(axis)]
            if missing_shape != 1:
                raise ValueError("Image/label axes do not align")
            continue
        a, b = names.index(axis), info.names.index(axis)
        if arr.shape[a] != info.shape[b] or not np.isclose(scale[a], image_scale[b]) or not np.isclose(offset[a], image_offset[b]) or label_units.get(axis) != image_units.get(axis):
            raise ValueError(f"Image/label {axis.upper()} grid or calibration differs")
    if arr.dtype.kind not in "ui":
        raise ValueError("Instance labels must use a nonnegative integer dtype")
    return arr


def write_tracked(group, name, masks, info):
    labels = group.require_group("labels")
    output = labels.create_group(name)
    axes = list("tzyx" if info.dimensions == 3 else "tyx")
    indexes = [info.names.index(a) for a in axes]
    scale, offset = transform(info.ms, len(info.names))
    array = output.create_array("0", data=masks.astype("u4"), chunks=(1,) + tuple(min(256, s) for s in masks.shape[1:]))
    array.attrs["_ARRAY_DIMENSIONS"] = axes
    definitions = {a["name"]: a for a in info.ms["axes"] if isinstance(a, dict)}
    ms = {"version": "0.4", "name": name, "axes": [copy.deepcopy(definitions.get(a, {"name": a, "type": "time" if a == "t" else "space"})) for a in axes],
          "datasets": [{"path": "0", "coordinateTransformations": [{"type": "scale", "scale": scale[indexes].tolist()}, {"type": "translation", "translation": offset[indexes].tolist()}]}]}
    depth = len(PurePosixPath(output.path).relative_to(PurePosixPath(group.path)).parts)
    attrs = {"multiscales": [ms], "image-label": {"version": "0.4", "source": {"image": "../" * depth}}}
    if group.metadata.zarr_format == 3:
        ms.pop("version")
        attrs = {"ome": {"version": "0.5", **attrs}}
    output.attrs.update(attrs)
    registry = metadata(labels).get("labels", [])
    updated = list(dict.fromkeys([*registry, name]))
    if group.metadata.zarr_format == 3:
        labels.attrs["ome"] = {"version": "0.5", "labels": updated}
    else:
        labels.attrs["labels"] = updated
