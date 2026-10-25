# Calibrated public test inputs

The starting catalog is Trackastra's
[pretrained.json](https://github.com/weigertlab/trackastra/blob/main/trackastra/model/pretrained.json).
It describes training sources, not a uniform collection of ready-to-import
plates. The source snapshot is retained in `third_party/trackastra-pretrained.json`.
Many entries are TIFF collections or single-field time series. Do not assume
that public availability implies physical calibration, plate structure or
independence from pretrained-model training.

The current usable set is:

| Dataset | XY µm/pixel | Acquisition interval | Author/source record |
| --- | ---: | ---: | --- |
| Fluo-N2DH-GOWT1 | 0.240 | 300 s | E. Bártová, Institute of Biophysics, Czech Academy of Sciences; [CTC Zenodo 15608211](https://zenodo.org/records/15608211) |
| Fluo-N2DH-SIM+ | 0.125 | 1740 s (published 29 min) | V. Ulman and D. Svoboda, CBIA, Masaryk University; [CTC Zenodo 15608207](https://zenodo.org/records/15608207) |
| PhC-C2DH-U373 | 0.650 | 900 s | S. Kumar, UC Berkeley; [CTC Zenodo 15608252](https://zenodo.org/records/15608252) |

Calibration and original contributor attribution follow the
[CTC acquisition descriptions](https://celltrackingchallenge.net/2d-datasets/).
The selected author-deposited Zenodo records report **CC BY 4.0**. Also preserve
the [CTC conditions and requested citations](https://celltrackingchallenge.net/datasets/).
The older CTC data host timed out during local preparation; the script uses
the CTC-authored Zenodo mirrors and verifies their published checksums.

`tools/prepare_publicdata.py` downloads original ZIPs into
`publicdata/downloads/`, verifies the record checksum, records SHA-256 and
prepares the first six frames of sequence 01. Original pixels, label values,
frame order and dtype are compared after conversion. The converter writes
NGFF 0.4 / Zarr v2 TCZYX fields, calibrated axes, embedded OME-XML and
`labels/instances` from CTC TRA reference markers.

Output inputs live under `publicdata/plates/`. Each movie is packaged as a
**single-well (A/1), single-field (0) test plate** to satisfy this adapter's
plate-only contract. This is a format wrapper, not an original multiwell screen;
it does not alter pixels or invent acquisition calibration. Original ZIPs and
provenance sidecars are retained. Synthetic tests separately exercise multiple
fields, independent labels and rejected 3D/static/standalone inputs.

TRA reference markers are often smaller than complete nuclear/cell masks.
They isolate association and pipeline compatibility, not segmentation accuracy.
The CTC datasets may overlap pretrained-model training, so these runs do not
establish independent biological generalization. The playback FPS of an exported
movie is unrelated to acquisition interval.

Other upstream catalog sources include Cell-ACDC yeast/stem-cell data, DeepCell,
btrack, epithelial benchmarks and several bacterial collections. They are
research leads, **not enabled test inputs** here until specimen-specific XY
calibration, frame ordering, instance annotations, licensing and a defensible
plate mapping have been verified. In particular, do not substitute TIFF DPI,
TrackMate placeholder units or calibration from a different microscope.
