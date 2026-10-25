# Sources and licenses

CITrackastra is a new OME-Zarr/Bilayers adapter maintained by Cellular Imaging,
Amsterdam UMC. Its own code is BSD-3-Clause, copyright 2026 Cellular Imaging,
Amsterdam UMC. It loads upstream pretrained models; it does not train a new model.

| Component | Source | License notice retained |
| --- | --- | --- |
| Trackastra 0.5.6 | https://github.com/weigertlab/trackastra | `third_party/TRACKASTRA-LICENSE`, BSD-3-Clause, Benjamin Gallusser and Martin Weigert |
| Trackastra pretrained weights/catalog | https://github.com/weigertlab/trackastra-models | `third_party/TRACKASTRA-MODELS-LICENSE`, BSD-3-Clause, weigertlab |
| Trackastra-et-Ultra features | https://github.com/C-Achard/Trackastra-et-Ultra | `third_party/TRACKASTRA-ET-ULTRA-LICENSE`, BSD-3-Clause, Gallusser, Weigert and Achard |
| SAM2.1 backbone | https://github.com/facebookresearch/sam2 | `third_party/SAM2-LICENSE`, Apache-2.0; observe upstream SAM2 attributions |
| Divisualisation 0.1.0 | https://github.com/bentaculum/divisualisation | `third_party/DIVISUALISATION-LICENSE`, MIT; actual SpacetimeLift API used by optional movie renderer |
| CI website styling | https://github.com/Cellular-Imaging-Amsterdam-UMC/ciseg-wevisonevl | `third_party/CISEG-WEVISONEVL-LICENSE`, MIT, Cellular Imaging Amsterdam UMC |
| Bilayers command helper / consumer manifest conventions | https://github.com/Cellular-Imaging-Amsterdam-UMC/cisegmentation | `third_party/CISEGMENTATION-LICENSE`, MIT, Cellular Imaging Amsterdam UMC |

The Trackastra and pretrained-model BSD notices apply to redistributed model
artifacts and model images. SAM2's separate license remains applicable to its
backbone. Other installed dependencies, including Qt, napari, FFmpeg, PyTorch
and the solver stack, retain their own licenses. The MP4 encoder uses the
FFmpeg distribution supplied by imageio-ffmpeg; retain its applicable notices
when distributing a built movie runtime.

Public dataset images are not covered by this repository's software license.
The selected CTC Zenodo records report CC BY 4.0; `docs/datasets.md` identifies
their authors, acquisition calibration, record IDs and conditions of use.
The Pages gallery contains resized display frames with percentile stretching
and actual predicted centroid paths, attributed to those sources. Full datasets,
weights, environments and result stores remain outside Git.

Cite Gallusser and Weigert, *Trackastra: Transformer-based cell tracking for
live-cell microscopy*, ECCV 2024. Cite SAM2 and the feature-model sources as
specified by the upstream catalog when using SAM2 features. Divisualisation
provides the spacetime renderer; without independent references, its output is
not an error-scored accuracy visualization.
