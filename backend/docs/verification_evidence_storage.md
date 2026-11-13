# Operator verification evidence storage

## Current behavior

- Citizen-submitted photos remain under `/tmp/flood_reports` and are served by the
  existing development-only `/uploads` mount.
- Operator verification photos use the separate `EvidenceStorage` abstraction. They
  are never placed under `/tmp/flood_reports` and are never served through `/uploads`.
- Local mode uses mode-`0700` directories and mode-`0600` files under
  `/tmp/flood_verification_evidence` by default. Existing flat local evidence files
  remain readable after upgrading.
- Evidence retrieval is authenticated, checks the report's append-only history for
  the exact evidence reference, and responds with `private, no-store` headers. The
  application logs authenticated retrievals and denied/missing references without
  logging image contents or credentials.

## Production S3 configuration

Set `VERIFICATION_EVIDENCE_STORAGE=s3` and configure
`VERIFICATION_EVIDENCE_S3_BUCKET` to a dedicated bucket that is different from the
general `AWS_S3_BUCKET_NAME`. The adapter uses the AWS credential chain (IAM role
preferred; configured access keys are supported), writes with server-side AES-256
encryption, does not set an object ACL, and exposes no S3 URL. All reads continue
through the authenticated API.

Before enabling it, the infrastructure owner must verify:

1. S3 Block Public Access and bucket-owner-enforced object ownership are enabled.
2. IAM allows the backend role to read/write/delete only
   `verification-evidence/*` in the dedicated bucket, and denies public access.
3. Bucket/server access logging or equivalent CloudTrail data events are enabled
   with access controlled and retained appropriately.
4. A legal/product owner defines the retention period and the bucket lifecycle rule;
   this repository does not invent an expiry period or automatically delete audit
   evidence.
5. The configured bucket is a non-production test bucket for integration tests.

The configured AWS credentials and bucket are present in the current backend
environment, but the dedicated verification bucket is not configured and no
S3 operation was attempted. Durable production storage is therefore **not yet
verified**. Production mode fails closed if local evidence storage is selected.
