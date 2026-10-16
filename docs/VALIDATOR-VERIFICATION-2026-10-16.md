# FLUX MCP validator release — October 16, 2026

Deployed to https://flux.by-pete.com using flux-studio-admin update. The replacement container passed 185 tests during its build and reported healthy. An additional 24 PostgreSQL integration tests passed locally, including every catalog option/capability combination against the generated SQL lock policy and an attempted direct database bypass of protected model access.

## Changes

- Identical content hashes pass compatibility before structural proof. Both graph paths share this implementation.
- Record-type/schema collisions report record-type-schema-conflict on the conflicting node's output.record_type. Findings include both pins and content hashes.
- Server proposal, sanitization, validation and build checks evaluate catalog locked/conditional_locked metadata with capability conditions. Planner accepted defaults use the same predicate.
- Protected proposals remain rejected, with all protected choices returned in locked_fields together. Human provenance remains required. This implements the permitted aggregate-error alternative, not a new proposed-choice confirmation UI.
- Connection errors include caller keys, saved edge IDs, schema pins/hashes and same-actor pending-proposal diagnostics. Workflow reads and validation expose pending_proposals. Existing pending changes are not silently merged. MCP initialize documents that behavior. This implements the permitted minimum diagnostic alternative.
- Resource-ID errors say slug only, no tenant prefix. Matching verified owner and TEST values remain accepted; owner spoofing and PROD proposals remain rejected.
- The live database had another unconditional approval-gate check. Migration 20261016163110_flux_builder_catalog_locks replaces that predicate using a private helper generated from the same catalog. Existing scope, revision, review, audit and atomic-apply checks are retained. Helper execution is revoked from PUBLIC, anon and authenticated.

## Actual canvas replay

Read-only ZODA snapshot: canvas-plan-4804dc27-3ada-47fa-82df-78f05d1242fc, saved revision 0.0.102.

Before: mail-1 falsely fails even when the pending Converter correction is replayed. Parser output and Converter input both resolve to schema:bunting.canvas-mail-parse@1.0.0, hash 957eeb33228d920ae8104203c2d34255b10c134ccbc84e4e959a576c063b9a01. Its optional nullable array lacks an items schema, causing the limited structural prover to fail against itself.

After: mail-1 passes. The unchanged saved Converter correctly receives a separate record-type conflict against the Parser because both publish document.read with different schemas. Substituting the existing pending Converter draft in memory clears both contract findings. No saved workflow or pending human proposal was applied or edited.

## Authenticated HTTPS acceptance

An isolated disposable synthetic tenant/user/company was used to verify:

1. New MCP initialize instructions.
2. REASON approval_gate=none persists, with matching server identity values accepted.
3. One error contains authority, model access and approval gate choices together.
4. Resource slug guidance.
5. Identical nullable-array contracts pass propose_connected_workflow.
6. validate_workflow also accepts those same contracts.
7. Different contracts fail with caller keys, pins, hashes and pending diagnostics.
8. The synthetic browser review endpoint returns HTTP 200 JSON.

No model/provider calls, mailbox reads, ERP actions, publication or runtime activation were performed by acceptance testing. Existing production mail runtime was not changed. Synthetic accounts, grants, proposals and tenant data were removed after testing. Immutable audit/request history is retained as designed.

## Separate observation

The existing Bunting browser AI connections endpoint returned HTTP 500 during verification; the isolated synthetic browser endpoint returned HTTP 200. This is not resolved by the validator patch and is not presented as a successful real-user review-page verification.

## Rollback

Server source backup: /home/pete-dev/flux-release-backups/validator-before-20261016-1135.tar.gz. Restore those six Python files and rebuild with the existing helper to roll back the application. Database rollback requires restoring the original protected-field loop and guard in flux_builder_session before dropping the private helper; retain the original function definition outside Git as a local rollback reference. No business records were changed by this release.

Security advisor scan was run. Existing project-wide findings include cal.kernel_versions RLS, exposed existing security-definer RPCs and auth/platform notices. The new helper has no public execute grant. Existing findings were not changed by this focused release; see https://supabase.com/docs/guides/database/database-linter.
