# CITrackastra SQLite schema 1

`schema_info(key,value)` records `format`, `schema_version`, `output_store_uuid`.
`run(key,value)` stores JSON values: workflow/version, Trackastra version,
settings, model download URLs/hashes, output UUID, source path, field summaries,
completion status and optional movie metadata. Expect `status` to decode as
`complete`. A hidden failed staging directory is not a completed result.

| Relation | Keys and meaning |
| --- | --- |
| fields | `field_id` PK; `image_path`, `source_label`, `output_label`, `dimensions` (=2), `scale_um_json` and `origin_um_json` (YX), `seconds_per_frame` (nullable), `time_origin` |
| tracks | PK `(field_id,track_id)`; `parent_track_id`, `parent_kind` (division/gap/NULL), inclusive `start_frame/end_frame`, `observation_count`, `duration`, `path_length_um`, `displacement_um`, `mean_speed`, `time_unit`, `speed_unit` |
| observations | PK `(field_id,timepoint,source_label)`; `track_id`, original `source_label` raster value, `z_px/y_px/x_px`, `z_um/y_um/x_um`, `time`. Z coordinates are NULL for 2D. |
| links | PK `(field_id,source_frame,source_label,target_frame,target_label)`; `kind` (link/gap/division), `distance_um`, `elapsed`, `speed` |
| track_summary | tracks joined to field context: `image_path`, `source_label_name`, `tracked_label_name`, plus all track columns |
| object_navigation | `field_id`, `image_path`, `source_label_name/value`, `tracked_label_name/value`, `timepoint`, `z_index` (=0), `y_px/x_px`, `y_um/x_um`, `time` |

All frame indices are zero-based. Original instance IDs can change between frames.
Track IDs are local to a field-and-label set; use `field_id` with every join.
Pixel coordinates use integer pixel centers. Physical coordinates apply the full
ordered dataset/global NGFF transform, with axis units converted to micrometers.
`observations.time` includes calibrated time origin when seconds are known;
otherwise it is the zero-based frame index. Missing seconds never implies 1 Hz.

Tracklets split at divisions and gaps. Within-tracklet path length sums observed
steps; displacement joins its first and last observation. Mean speed is path
length/duration. Singleton speed is NULL. Cross-gap speed belongs to `links`.
Division hypotheses are predictions and need biological review.

## Read-only connection

```python
from pathlib import Path
import sqlite3
db_path = Path("tracking.sqlite").resolve()
db = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
```

When `omero.analysis` supplies an attachment-query capability, use it rather
than assuming the attachment is a local path. Run the schema identity query
once, then reuse verified schema facts.

```sql
SELECT key,value FROM schema_info;
SELECT field_id,image_path,source_label,output_label,scale_um_json,
       seconds_per_frame FROM fields ORDER BY field_id;

SELECT field_id,image_path,source_label_name,track_id,observation_count,
       path_length_um,mean_speed,speed_unit
FROM track_summary WHERE observation_count >= 3
ORDER BY mean_speed DESC LIMIT 25;

-- Count binary division parents, not daughter edges or cross-gap parents.
SELECT field_id,source_frame,source_label,count(*) AS daughter_count
FROM links WHERE kind='division'
GROUP BY field_id,source_frame,source_label
HAVING count(*)=2 ORDER BY field_id,source_frame LIMIT 100;

SELECT * FROM object_navigation
WHERE field_id=? AND tracked_label_value=? ORDER BY timepoint LIMIT 100;
```

To join CISegmentation measurements, first verify that it describes the same
source output store. Then match field resource path, label name, timepoint and
original raster value (`objects.label_value`), never `object_id = track_id`.
The result store retains original source labels and adds
`labels/<source_label>_tracks`; the original source label value and trajectory
label value are different namespaces.
