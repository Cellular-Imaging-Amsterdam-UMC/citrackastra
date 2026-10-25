# CITrackastra working instructions

- Use English for everything in this repository: documentation, code comments, docstrings, UI text, skills, tests, commit messages and GitHub Pages. Preserve proper names in citations.
- Use `.venv/Scripts/python.exe` explicitly on Windows. Keep environments, models, public datasets and generated results out of Git.
- Track existing instance labels; segmentation belongs upstream, for example in CISegmentation. Keep each image, HCS field and label set independent.
- Accept only NGFF HCS plates with 2D time series. Every selected field must have T >= 2 and Z absent or singleton. Reject standalone images, static fields and volumes; never project them silently.
- Optional movies include one conventional 2D tracking MP4 and one actual Divisualisation SpacetimeLift MP4 per input plate, with sequential field/label segments. Do not imply ground-truth error scoring without independently matched reference data. The lifted vertical axis is time, not physical Z.
- Require verified, positive physical spatial calibration. Preserve anisotropic scales, ordered NGFF transforms and image origins. Never invent missing calibration or interpret TIFF DPI as micrometers.
- Preserve source pixels and instance IDs. Write new stores, tracked labels and tables. Refuse existing destinations and publish results only after all fields succeed.
- Report model predictions separately from reference annotations and biological accuracy. Public smoke tests are compatibility checks, not independent accuracy benchmarks.
- Download models explicitly into the ignored local `models/` directory. Inference must load local weights and must not silently download models.
- Keep the headless Bilayers/BIOMERO workflow image separate from the optional model-cache image. Docker recipes are preparation only; do not build or publish images unless requested.
- GitHub Pages uses the visual style of CISegWeVisOneVL, dark by default, with a persistent Bright/Dark toggle. Scientific image colors must not change with the theme.
- Run unit/integration tests and actual public-data inference locally before claiming validation. Record exact package/model versions, dataset calibration, hashes and limitations.
