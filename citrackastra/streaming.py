"""Bound image memory without changing Trackastra's global normalization."""

import math

import dask.array as da
import numpy as np


def working_bytes(shape, names, label_itemsize, workers=0):
    """Estimate frame buffers and the exact upstream percentile sample.

    Features and graph size additionally depend on the number of instances.
    Raw sequences and relabelled outputs remain lazy, with one frame per chunk.
    """
    sizes = dict(zip(names, shape))
    pixels = math.prod(sizes[a] for a in "yx")
    stride = 4 if all(sizes[a] > 256 for a in "yx") else 1
    sample = sizes["t"] * math.prod(math.ceil(sizes[a] / stride) for a in "yx")
    return 1024**3 + pixels * (32 + label_itemsize) * max(1, workers) + sample * 8


def normalize_sequence(imgs):
    """Match trackastra.utils.normalize over the entire sequence exactly.

    Dask's upstream map_blocks(normalize) would normalize each frame separately.
    Compute the same global sampled percentiles once and apply them lazily.
    No time windows are tracked separately, so links across every boundary remain.
    """
    values = imgs.astype(np.float32)
    sample = values[..., ::4, ::4] if all(s > 256 for s in values.shape[-2:]) else values
    mi, ma = np.percentile(sample.compute(scheduler="synchronous"), (1, 99.8)).astype(np.float32)

    def normalize_block(block):
        result = block.astype(np.float32, copy=True)
        result -= mi
        result /= ma - mi + 1e-8
        return result

    return values.map_blocks(normalize_block, dtype=np.float32)


def retain_unlinked_instances(graph, masks):
    """Keep unmatched source detections as singleton tracks, inventing no links.

    Upstream greedy matching returns only nodes incident to accepted edges.
    The result contract also requires observations for isolated detections.
    """
    from skimage.measure import regionprops
    present = {(int(attrs["time"]), int(attrs["label"])) for _, attrs in graph.nodes(data=True)}
    next_id = max((int(node) for node in graph.nodes if isinstance(node, (int, np.integer))), default=-1) + 1
    added = 0
    for t in range(len(masks)):
        for region in regionprops(np.asarray(masks[t])):
            key = (t, int(region.label))
            if key not in present:
                graph.add_node(next_id, time=t, label=key[1], coords=tuple(region.centroid), weight=1)
                next_id += 1
                added += 1
    return added
