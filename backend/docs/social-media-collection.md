# Social media collection

The social collection pipeline is separate from citizen reports and flood-event
ground truth. Collected posts remain unverified source signals; they are not
automatically classified, confirmed, or promoted to incidents.

## Enablement

Collection is disabled by default. Before enabling it, an authorized deployment
owner must confirm provider API access, permitted research/display/storage uses,
and applicable retention/deletion obligations. Set the server-side variables
shown in [`.env.example`](../.env.example); set `SOCIAL_COLLECTION_ENABLED=true`
only after that review. The adapters never scrape web pages or bypass API access
controls.

Supported adapters are Reddit's OAuth API for recent posts in `r/mumbai` and
the X API recent-search endpoint. Missing credentials produce a
`not_configured` status. Provider errors and rate limits are recorded using
sanitized error codes; credentials and raw provider responses are not logged or
returned.

### Activation readiness review — 2026-11-11

The local development database migration was applied to `fip_db`, revision
`0006_social_media_collection`. It creates only `social_media_posts` and
`social_collection_runs`; the 41 citizen reports, zero legacy social signals,
and zero flood events were unchanged. Both new tables were empty after upgrade.

Provider credentials were present in local configuration, but the minimal
connectivity checks did not establish usable collection access:

* Reddit's OAuth token request returned HTTP 401. Authentication failed; search
  access was not tested, and no posts were requested.
* X's recent-counts endpoint returned HTTP 402. No post objects were requested.
  The endpoint's API-plan/payment entitlement is unavailable; this response
  does not establish recent-post search permission or independently prove
  bearer-token validity.

No live collection test was run. `SOCIAL_COLLECTION_ENABLED` remains `false`.
Resolve Reddit's rejected credentials through the authorized app owner and
confirm X endpoint access and billing in the developer console before any
collection attempt.

### Provider terms, stored fields, and deletion readiness

Terms reviewed on 2026-11-11:

* [Reddit Data API Terms](https://www.redditinc.com/policies/data-api-terms)
  require use/retention to stay within the approved use case and immediate
  deletion of data not required for it. They require deletion of cached or
  stored permitted content when API access ends. The
  [Reddit Developer Terms](https://www.redditinc.com/policies/developer-terms)
  require content removed, protected, suspended, withheld, modified, or deleted
  on Reddit to be deleted or updated as soon as possible, including on a
  user's request; required Reddit attribution must follow the API documentation.
* The [X Developer Policy](https://docs.x.com/developer-terms/policy) requires
  current X content when displaying posts through a service other than X
  embeds, and removal as soon as reasonably possible (or within 24 hours of a
  removal request). X's agreement restricts storing location/geographic data
  except with the associated X content and limits its use to identifying the
  location tagged by that content. X also restricts redistribution of content.
  [X Batch Compliance](https://docs.x.com/x-api/compliance/batch-compliance/introduction)
  reports delete, protected, suspended, and edited-post actions;
  [compliance streams](https://docs.x.com/x-api/compliance/streams/introduction)
  provide near-real-time updates but require Enterprise access.

This application currently stores full text, external URLs, matched terms,
location fields, and media references without an expiry, provider deletion
sync, content rehydration, takedown workflow, or compliance-event consumer. The
dashboard renders post text directly rather than embedding provider-controlled
current content. It has basic platform labels and source links, but its
attribution/display behavior has not been validated against each provider's
requirements. Therefore, the current storage and display implementation is
**not approved for live collection**.

Before enabling persistence, an authorized owner must document the accepted
use case and permitted fields with each provider, approved retention duration,
and display/attribution requirements. Then implement and test:

1. Per-record expiry and a deletion job that actually removes expired text,
   media references, and associated location fields.
2. Reddit removal/deletion request handling, and a reconciliation process that
   deletes or updates records when Reddit content is removed or access ends.
3. X compliance event processing (or an approved batch-compliance polling
   alternative), applying `delete`, `scrub_geo`, and `rehydrate` actions and
   ensuring removal requests are handled within the applicable deadline.
4. Freshness-aware X display (or approved X embeds), source attribution, and
   validation that any retained location remains attached to its source post
   and is used only as permitted.
5. A user/provider takedown intake and audit trail, with deletion tests covering
   text, media references, coordinates, ward assignment, and cached copies.

Until those requirements and access approvals are complete, do not set
`SOCIAL_COLLECTION_ENABLED=true`, start the social worker, or run the collection
task.

### Frontend dependency security check — 2026-11-11

The installed dependency tree has two production-impacting audit findings:

* `next@14.2.35` is a direct production dependency and is reported **critical**.
  The affected ranges include Next 14 and versions through 15.5.27; for example,
  [GHSA-2464-fhr4-w9xw](https://github.com/advisories/GHSA-2464-fhr4-w9xw)
  covers unauthenticated RCE in the Image Optimization API when SVG files are
  used. Applicability depends on enabled features, but the installed framework
  is within the reported affected range.
* `postcss@8.4.31` is nested under production Next and is reported **high**
  (affected through 8.5.22), including
  [GHSA-fxqj-rqcc-2cmp](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp).
  `npm audit --omit=dev` reports the same two findings.

An isolated dependency-resolution audit of `next@15.5.29` with a PostCSS
override referencing the root PostCSS dependency (`"postcss": "$postcss"`)
reported zero advisories in both full and production-only scans. This was an
audit-only candidate: no project dependency files were changed, and application
build/runtime compatibility with Next 15 has not been validated. Upgrade to
that patched 15.5 line and run the complete frontend regression/build checks
before deployment; do not use `npm audit fix --force`.

## Migration and worker

Apply the additive schema migration before deploying the new API:

```sh
alembic -c backend/migrations/alembic.ini upgrade head
```

The task is routed only to `social_ingest`; it is not added to the weather Beat
or any Beat schedule. Once collection has been approved and enabled, run a
dedicated worker:

```sh
celery -A backend.tasks.celery_app:celery_app worker -Q social_ingest
```

Trigger collection on demand with:

```sh
celery -A backend.tasks.celery_app:celery_app call backend.tasks.scheduled_tasks.task_poll_and_ingest_social_signals
```

No social scheduler is started by this phase. The existing weather-only Beat,
its queue, and its 10-minute schedule remain independent.

Activation review confirmed the registered routes separately route the social
task to `social_ingest` and weather ingestion to `weather_ingest`. The active
worker subscribed only to `weather_ingest`; no social worker was started. The
weather-only Beat lease and heartbeat matched, and its single 600-second
schedule remains unchanged.

## API and location handling

The operator-authenticated endpoints are `GET /v1/social/status`,
`GET /v1/social/posts`, `GET /v1/social/posts/{post_id}`, and
`GET /v1/social/summary`. The frontend accesses them through the server-side
operator session proxy.

Only exact platform coordinates are spatially matched. A ward is stored only
when PostGIS identifies exactly one containing ward. Text locations remain
unresolved; ambiguous boundaries and invalid coordinates are not converted
into guessed locations. Media is referenced only when a public URL is returned
by the provider API; files are not downloaded or copied to public uploads.

### Activation readiness recheck — 2026-11-13

The local development database is still at revision
`0006_social_media_collection`; no migration was run during this recheck. The
additive migration's tables, indexes, uniqueness constraint, nullable source
fields, coordinate/confidence checks, and ward foreign key are present.
`social_media_posts`, `social_collection_runs`, `social_signals`, and
`flood_events` each contain zero rows; `citizen_reports` contains 41 rows.
No records were changed by this review.

Provider credentials are configured, but neither source is ready for
collection:

* Reddit's official OAuth token request again returned HTTP 401. Authentication
  failed; no search request or post retrieval was made. Search permission and
  rate-limit allowance remain unverified.
* X's official recent-counts endpoint returned HTTP 402. The response included
  rate-limit headers, but does not establish access to recent-post search or
  confirm the required API-plan entitlement. No post objects were requested.

No live collection or social worker was started. `SOCIAL_COLLECTION_ENABLED`
is `false`. The social task remains routed to `social_ingest`, the weather task
to `weather_ingest`, and the only weather Beat entry remains the existing
600-second schedule. The weather-only worker (PID 41008) and Beat (PID 43175)
were observed running and were not restarted. Once separately approved,
the dedicated worker command is:

```sh
celery -A backend.tasks.celery_app:celery_app worker -Q social_ingest --concurrency=1
```

The current [Reddit Data API Terms](https://www.redditinc.com/policies/data-api-terms)
(last revised July 20, 2026) limit content use and retention to the approved
use case, require immediate deletion of data not needed for it, and require
deletion of permitted cached/stored content when access ends. They grant
content use only as needed to develop, deploy, distribute, and run the
application, require applicable attribution, and reserve API limits and
changes. They do not establish an indefinite retention period for this
application. The [X Developer Policy](https://docs.x.com/developer-terms/policy)
requires current content for public display and removal when it is no longer
available, as soon as reasonably possible and within 24 hours of a removal
request. X's [Batch Compliance](https://docs.x.com/x-api/compliance/batch-compliance/introduction)
reports delete, rehydrate, and scrub-geo actions; its
[near-real-time compliance streams](https://docs.x.com/x-api/compliance/streams/introduction)
require Enterprise access.

The existing implementation has no expiry, takedown intake, provider
deletion/compliance reconciliation, or rehydration process. For a provider
delete/removal, the implementation needs to remove the post record and its
text, URL, matched terms, media references, coordinates, location text,
confidence, ward assignment, and cached/display copies. A geo-scrub action
must remove location-derived fields and ward assignment. A rehydrate action
must refresh current source content and recompute matched terms and
location-derived values. Author identifiers are not collected. The dashboard
shows post text directly, so current-content checks and provider attribution
are not yet enforced. Applicable permitted fields, retention duration,
display/attribution, and an operational deletion/reconciliation method still
need provider-specific approval and implementation. Collection therefore
remains **not ready** and must stay disabled.

The production npm audit was repeated against the installed dependency tree:
it reports two affected production packages (one critical, one high),
`next@14.2.35` and its transitive `postcss@8.4.31`. In an isolated,
audit-only resolution, `next@15.5.29` with `postcss@8.5.23` resolved with zero
production advisories. This candidate was not applied or build-tested; it
requires a Next 14-to-15 compatibility review and the normal application
regression/build checks before adoption. The current installed frontend still
passes TypeScript validation and its production build. No dependency manifest
or lockfile was changed.

## Phase 9.4.1.3 — lifecycle implementation status

The following implementation supersedes the earlier lifecycle-readiness
description above. It is an engineering control set, **not** a provider or
legal compliance approval.

### Provider requirements and remaining decisions

Reviewed the current official [Reddit Data API Terms](https://www.redditinc.com/policies/data-api-terms),
[Reddit Developer Terms](https://www.redditinc.com/policies/developer-terms),
[X Developer Policy](https://docs.x.com/developer-terms/policy), and
[X Developer Agreement](https://docs.x.com/developer-terms/agreement), plus
the X [Batch Compliance](https://docs.x.com/x-api/compliance/batch-compliance/introduction)
and [Compliance Streams](https://docs.x.com/x-api/compliance/streams/introduction)
documentation.

Confirmed at the policy level:

* Reddit use and retention must remain within the approved use case; data no
  longer needed must be deleted, and cached/stored content must be deleted when
  API access ends. Reddit content removed, withheld, or deleted must be removed
  or updated promptly. Required attribution follows Reddit's API
  documentation. The reviewed terms do not establish this application's
  retention duration.
* X requires displayed content to be current and content that is no longer
  available to be removed as soon as reasonably possible; removal requests
  carry a 24-hour limit. X compliance tooling describes delete, rehydrate, and
  geographic-scrub operations. Compliance Streams require Enterprise access.
  The agreement restricts redistribution and limits use of licensed content.
* The adapters do not collect author/profile identifiers or download media.
  They can normalize post text, source IDs/URLs, timestamps, location
  coordinates/text, and media references. Permission to retain each field
  must still be approved for the exact application use case.

Still unresolved: the provider-approved use case and field-by-field storage
permissions; a provider-approved retention duration for each provider;
display/attribution requirements for this dashboard; Reddit's application-
specific removal synchronization method and timing; and X's entitlement to
search and use Batch Compliance or Compliance Streams. Public availability
does not settle those questions. No fixed duration is represented as a
provider requirement.

### Implemented controls

* Provider-specific settings default to unapproved, with no permitted fields,
  no retention duration, and no reconciliation interval. Collection requires
  collection enablement, lifecycle enablement, provider approval, an explicit
  positive duration and reconciliation interval, a permitted external ID, and
  a stable random tombstone HMAC key of at least 32 bytes. Unknown policy
  fails closed.
* Expiry is calculated from collection time and is not extended by
  rehydration. The bounded expiry task defaults to dry-run and records only
  operation metadata in that mode.
* Source records distinguish `unverified`, `current`, `pending_compliance`,
  `unavailable`, `expired`, and `deleted`. Only successfully verified,
  unexpired content whose configured reconciliation deadline has not passed is
  returned; overdue or other states have source fields masked. Responses and
  the frontend operator proxy are `no-store`; the dashboard removes cached
  social queries after a takedown.
* Confirmed removal, expiry, and geographic-scrub operations erase source
  text, IDs/URLs, matched terms, timestamps, location/coordinates, ward
  assignment, media references, provenance, and attached derived artifacts as
  applicable. Derived artifacts are linked to their source row with cascade
  cleanup. Deleted source IDs are represented only by keyed digests where the
  stable HMAC key is configured. If a record must be redacted without a key,
  the provider is persistently collection-blocked by its append-only audit
  marker; configuring a key later does not silently reopen that provider.
  Operators must keep the HMAC key stable and must not rotate it without a
  reviewed tombstone migration.
* Reconciliation uses provider exact-ID lookup only when lifecycle access and
  policy are configured. Rate limits, authentication failures, timeouts, and
  server errors remain retryable and do not imply deletion. A provider
  not-found/gone response is treated as unavailable, not proof of why the
  source disappeared. Rehydration refreshes allowed fields and does not extend
  expiry.
* Operator-authenticated takedown, provider-event intake, and audit endpoints
  use the existing operator dependency. The frontend mutation proxy keeps its
  same-origin check. Provider-event intake is an operator endpoint, **not** a
  provider-authenticated webhook; no official Reddit notification or X
  compliance-stream consumer is configured. X reconciliation is not a
  substitute for an unapproved compliance feed or approved batch process.
* Compliance operation rows contain safe operation metadata and digested
  event IDs, not source text or provider payloads. Database triggers reject
  UPDATE, DELETE, and TRUNCATE. Failures are retried with bounded backoff and
  safe error categories.

### Migration and operations

Revision `0007_social_data_lifecycle` is an additive migration over
`0006_social_media_collection`. It adds lifecycle columns and indexes,
derived-artifact, tombstone, and append-only compliance-operation tables, and
the policy-blocked collection-run status. Existing social, citizen-report,
and flood-event rows are not copied, rewritten, or deleted by the migration.
The development database remains at revision `0006`; migration `0007` was not
applied in this phase.

The expiry, source-reconciliation, and takedown-retry tasks are explicitly
routed to `social_ingest`; they are not added to Beat. The separate social
worker command remains:

```sh
celery -A backend.tasks.celery_app:celery_app worker -Q social_ingest --concurrency=1
```

No social worker or Beat was started. `SOCIAL_COLLECTION_ENABLED` and
`SOCIAL_LIFECYCLE_ENABLED` remain `false`; lifecycle dry-run remains enabled.
Provider policy approval, retention periods, field permissions, access
entitlements, notification integration, and migration application remain
deployment prerequisites. No posts were collected. No NLP or computer-vision
processing was added. Weather workers, Beat, queue routing, and the 600-second
weather schedule were not changed.

The earlier npm audit section above is historical. The current frontend
manifest/lockfile uses Next.js 15.5.29 and PostCSS 8.5.23; the current
production-only npm audit reports zero advisories.
