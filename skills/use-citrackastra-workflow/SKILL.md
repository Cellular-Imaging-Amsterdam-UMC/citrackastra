---
name: use-citrackastra-workflow
description: Configure, launch and verify the CITrackastra Bilayers/BIOMERO workflow for calibrated 2D time-series plates with existing instance labels, including optional Divisualisation MP4 output.
metadata:
  version: "1"
---

# Use the CITrackastra workflow

Resolve the selected plate and configured workflow revision. Read the installed
descriptor and [PARAMETERS.md](references/PARAMETERS.md) before proposing settings.
CITrackastra accepts only NGFF HCS plates with 2D time series: every field needs
T>=2, Z absent/singleton, positive calibrated XY units and aligned instance labels.
It performs association, not segmentation. Reject standalone images, static plates,
volumes and labels-only overlays without the source pixels; do not project them.

Check label names, the one-based image channel, model availability, compute
resources and whether the installed runtime has requested movie/SAM2 extras.
Each field and label set is processed independently. Do not alter scientific
parameters silently to fit resource limits.

Use the user's execution request or existing authorization for submission.
Inspection alone is not a launch request. Submit once through the available
workflow interface and retain its run/job ID. Monitor that ID; a delayed status
or client timeout is not evidence that submission failed and is not a reason to
submit again. Ask only when required input is missing or the resolved scope
materially exceeds the authorized request.

Verify actual outputs after completion: a result OME-Zarr with matching original
pixels/labels and trajectory labels, a schema-1 SQLite database, CSV exports,
provenance and both MP4s and movie metadata when requested. Check complete status and
the shared output-store UUID. A scheduler completion alone is insufficient.
Retain workflow ref/commit, resolved parameters, input plate, run ID and output
identities. Preserve failed staging evidence; do not delete or overwrite it as
a recovery shortcut. Retry a failed job only within explicit user authorization,
after checking that no run remains active and no completed destination conflicts.

Each plate can produce a conventional 2D tracking MP4 and a spacetime MP4,
both with sequential field/label segments. The spacetime movie uses Divisualisation's spacetime display; the vertical coordinate is time, not Z.
No independent ground-truth error scoring is implied.
