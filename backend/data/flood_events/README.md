# Historical flood-event acquisition

This directory contains a source-gated pipeline for documented event-level data. The
current inventory does **not** contain a verified, licensed bulk download of historical
Mumbai flood incidents, so the normalized and validated CSVs contain headers only.
That is an explicit no-data result, not a claim that no incidents occurred.

## Pipeline

Run commands from the repository root with the backend environment active:

```bash
python -m backend.data.flood_events.discover_sources
python -m backend.data.flood_events.download_events --source "Exact source name"
python -m backend.data.flood_events.normalize_events \
  --input backend/data/flood_events/raw/source.csv \
  --source-name "Exact source name" \
  --source-url "SOURCE PAGE URL" \
  --field-map backend/data/flood_events/field_map.json
python -m backend.data.flood_events.validate_events
python -m backend.data.flood_events.assign_ward_matches
python -m backend.data.flood_events.validate_events \
  --input backend/data/flood_events/validated_events.csv \
  --output backend/data/flood_events/validated_events.csv
python -m backend.data.flood_events.align_rainfall \
  --rainfall-timezone Asia/Kolkata
python -m backend.data.flood_events.event_quality_report
```

The downloader refuses sources without an inventory entry, verified public bulk URL,
documented license, HTTPS, and an allowed file extension. It records a SHA-256 manifest
and limits downloads to 250 MiB. Field mapping is explicit; unknown values remain null.
The raw source archive is optional and should be kept access-controlled when its source
contains sensitive records. Normalization always writes each original row to a new,
timestamped JSONL sidecar beside its input; `--raw-archive` selects an explicit new
path. Existing archive paths are never overwritten.
If an existing stable source record ID reappears with changed event values, the raw
revision is archived and normalization stops for review rather than silently replacing
the prior normalized record.

## Normalized event schema

| Field | Meaning |
|---|---|
| `event_id` | Stable SHA-256 identifier derived from the source record ID, or the complete canonicalized source row if no ID exists. |
| `event_timestamp` | Incident time normalized to UTC ISO 8601 only when the source provides a timezone or an explicit source timezone is supplied. |
| `latitude`, `longitude` | Source coordinates in decimal degrees; both null when not reported. |
| `ward_id` | Source ward code, or a spatially assigned ward only when the point matches exactly one registered polygon. |
| `spatial_ward_id` | Ward identified by the PostGIS match, kept separately to reveal disagreements with a source ward. |
| `location_description` | Source-provided place description; never generated from coordinates. |
| `event_type`, `flood_severity` | Source event classification and severity; no category is inferred from rainfall. |
| `water_depth_m`, `duration_minutes` | Reported numeric values only. |
| `source_name`, `source_url` | Source identity and page/dataset provenance. |
| `verification_status`, `confidence` | Source verification label and confidence, when explicitly provided. |
| `collection_timestamp` | UTC timestamp when the record was normalized. |
| `geospatial_match_confidence` | Null unless a documented source supplies a defensible measure; spatial containment alone does not quantify coordinate accuracy. |
| `ward_match_method`, `validation_issues` | Spatial procedure and machine-readable review flags. |

The PostGIS matcher uses `ST_Covers(geom, ST_SetSRID(ST_Point(longitude, latitude), 4326))`.
It preserves a source-provided ward, adds `spatial_ward_id` for comparison, and flags
boundary ambiguity, out-of-ward coordinates, or disagreements. A ward assignment can
be spatially deterministic without the source coordinate itself being accurate; for
that reason `geospatial_match_confidence` remains null unless a source establishes it.
Potential cross-source duplicates require both timestamps with explicit timezone offsets
and coordinates within 100 m and 60 minutes. They are review candidates and never
automatically deleted.

The canonical record also retains `source_record_id`, the SHA-256 of the acquired
source file, the explicitly declared source timezone, and an `evidence_category`.
Categories are never inferred from CV output or from the fact that a source is a
government publisher. Naive event timestamps remain null and receive a validation issue
unless the source timezone is explicitly provided; ambiguous or nonexistent local times
are not guessed. Raw source rows are archived with collection metadata and source-file
checksum.

## Evidence classes

The optional `evidence_category` must be explicitly mapped from source data or assigned
by an authorized curation process:

- `citizen_submitted`
- `operator_confirmed_citizen`
- `independently_verified_historical`
- `officially_confirmed_historical`

The verified-event rainfall alignment includes the three explicit verified categories
but preserves category labels. It does not merge them into one class. An operator
confirmation remains a citizen-report record and is not an official BMC confirmation.

## Historical rainfall alignment

`align_rainfall.py` reads the existing Mumbai-region hourly/daily QC files and writes a
separate `rainfall_aligned_events.csv` plus `rainfall_alignment_report.json`. It records
the nearest station and its distance for event coordinates, or for a registered ward
centroid when the event lacks coordinates and has a ward ID. The distance basis is
recorded; a centroid is not presented as the exact incident location.

The rainfall files contain timezone-naive timestamps. The command therefore requires
`--rainfall-timezone`; verify the correct timezone against the rainfall provider before
scientific use. It never uses readings after the event timestamp or interpolates. A
window total is emitted only when the expected observations are present at the station's
recorded schedule. Incomplete windows have a null total, an observed-measurement sum
for review, and a missing-coverage status; missing values are never replaced with zero.
The source rainfall files are read-only inputs.

## Coordinate caution

GeoJSON Point coordinates are read as `[longitude, latitude]`. The existing
`frontend/public/data/mumbai-wards.geojson` was inspected and contains coordinates
ordered as `[latitude, longitude]`, contrary to GeoJSON convention. Event ward matching
therefore uses the registered PostGIS geometries (SRID 4326), not those frontend
coordinates. Verify any future source geometry's CRS and coordinate order independently.

## Source status

See [`sources.json`](./sources.json) for the investigated inventory. The OpenCity
downloadable resource is monthly rainfall, not event labels. IMD and project rainfall
assets remain covariates and are not copied, modified, or converted into flood events.
A research paper reports an MCGM-derived inventory of 234 waterlogged locations, but
its underlying records were not found as a public download and do not establish dated
incident labels. Citizen submissions remain in the internal database and are not
exported here without an approved data-governance decision.

The BMC historical records request is prepared but **has not been submitted**:
[`requests/bmc_records_request.md`](./requests/bmc_records_request.md). Its status,
permissions, and any future responses/files must be updated in
[`requests/historical_requests.json`](./requests/historical_requests.json). Until
permission and source terms are documented in the source inventory, the downloader and
normalizer reject that source.

## Prospective citizen-report verification

Apply the additive Alembic migration before starting the updated backend:

```bash
cd backend
venv/bin/alembic -c migrations/alembic.ini upgrade head
```

Configure named operator credentials in the backend environment as
`FLOOD_OPERATOR_TOKENS`, a JSON object mapping stable operator IDs to unique,
high-entropy bearer tokens of at least 32 characters. Example shape only:

```text
FLOOD_OPERATOR_TOKENS={"<operator-id>":"<generated-unique-token-at-least-32-characters>"}
```

Do not commit real tokens or put them in browser code. Verification APIs fail closed
with `503` when this setting is absent or invalid; missing or invalid bearer
credentials receive `401`.

The decision endpoint expects an `action`, plus corrected `event_timestamp`,
`latitude`/`longitude`, `water_depth`, or `water_depth_m` only when verified or
measured. Use the actual report timestamp with its timezone and the evidence-supported
coordinates/depth; omit measured depth when unknown. A rejection or review flag
requires a non-empty reason. API calls use a bearer token in the `Authorization`
header; the operator console keeps it in its server-side encrypted session, not
browser storage.

- `GET /v1/reports/operator/queue` lists pending/review-needed reports. Authenticated
  operators may filter by a verification status.
- `POST /v1/reports/{report_id}/verification` accepts `action` (`confirm`, `reject`,
  or `review`), optional reason, timezone-qualified corrected timestamp, paired
  latitude/longitude, categorical depth, and a measured depth in metres when known.
  Reject/review actions require a reason. Missing corrections retain the citizen's
  actual submitted values; no CV estimate is copied into the measured-depth field.
- `POST /v1/reports/{report_id}/verification-evidence` accepts multipart `note` and
  up to five JPEG/PNG/WebP photographs, capped at 10 MiB total.
- `GET /v1/reports/{report_id}/verification-history` returns the append-only audit log.
- `GET /v1/reports/ground-truth/events` lists only currently operator-confirmed event
  records. Citizen reports remain `source_kind=citizen_report` and
  `official_confirmation=false`; operator review is not an official BMC confirmation.

Every action records the operator ID, previous/new state, timestamp, location, depth,
reason, duplicate linkage, and evidence references. The history table has a database
trigger preventing update/delete. Confirmed event candidates are separate from citizen
submissions; later rejection/review changes their current status without deleting
their review history. Duplicate source reports remain explicitly flagged and are not
silently merged. Ward assignment uses PostGIS and is left null when a point is
ambiguous or outside registered ward polygons. The current evidence files use local
development storage under `/tmp/flood_verification_evidence`; citizen report uploads
remain separate under `/tmp/flood_reports`. Local evidence storage is not durable
production storage. See [`verification_evidence_storage.md`](../../docs/verification_evidence_storage.md)
for the private S3 configuration and outstanding infrastructure requirements.

The generated [`DATA_QUALITY_REPORT.md`](./DATA_QUALITY_REPORT.md),
`event_quality_report.json`, and `ward_coverage.csv` report the historical CSV dataset,
registered wards, and count-only summaries of prospective citizen reports and operator
event records. Citizen submissions are not exported or folded into historical labels.
Do not train a supervised model until verified, timestamped event labels with
defensible geographic and temporal coverage are acquired.
