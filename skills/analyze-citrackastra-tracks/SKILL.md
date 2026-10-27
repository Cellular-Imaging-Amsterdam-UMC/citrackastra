---
name: analyze-citrackastra-tracks
description: Analyze CITrackastra SQLite attachments in omero.analysis for calibrated trajectories, motion, gap links and divisions; resolve the corresponding plate field, frame and label for image inspection.
metadata:
  version: "1"
---

# Analyze CITrackastra results

Read [SCHEMA.md](references/SCHEMA.md) before substantive queries unless the
consumer has already loaded it. Open attachments read-only using the available
database-query capability. Confirm `schema_info.format = CITrackastra tracking`
and `schema_version = 1`; cache verified schema facts while the file hash remains
unchanged. Do not apply CISegmentation measurement SQL to this database.

Start with `run` and `fields` when provenance, calibration or input scope matters.
Use `track_summary` for trajectory summaries and `object_navigation` for image
inspection. Aggregate/filter in SQL before loading a bounded result into Python.

Always retain `(field_id, track_id)` together: track IDs restart for every field
and label set. An observation's source key is image path, source label name,
timepoint and source label value. The tracked label value is its track ID.
Never join another database using numeric IDs alone. For a user-selected image
overlay, use the workspace Image input independently of the tracking database;
no shared UUID or source/result relationship is required. Verify native pixel
coordinates, dimensions and frame/Z indices against that image. Only an explicit
legacy UUID-navigation request requires matching the database output UUID to the
store's `citrackastra.output_store_uuid` (not an inherited source UUID).

Track IDs identify contiguous CTC tracklets. Both divisions and gap continuations
create child segments; count division events from `links.kind='division'`, not
from every non-NULL parent ID. Two daughter edges represent one binary division.
Use `parent_kind` to distinguish division from gap parentage. Tracklet speeds
exclude the cross-gap link; `links` records that displacement and elapsed time.

Report physical XY coordinates and lengths in micrometers. Inspect `time_unit`
and `speed_unit`: missing time calibration gives frames and micrometers/frame.
Singleton mean speeds are NULL. Do not interpret them as zero. Separate model
predictions from biological conclusions, segmentation quality and reference truth.

For a requested image gallery, query source and tracked keys plus XY coordinates
in one bounded result; inspect the available rendering tool's schema and map
those verified keys to its contract. Use Z=0 for the singleton 2D plane. Preserve
the field, label set, frame, ROI and label values together through rendering.
Do not imply that the optional movie contains independent ground-truth errors:
its vertical display axis is time, and plate fields play sequentially.
