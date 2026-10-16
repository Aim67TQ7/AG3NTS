# FLUX record bindings — Studio 0.4.0

Cards read a curated record type/status and publish a durable record type/status per outcome. The diagram derives card → record → card links; it is not execution state. Direct wiring is disabled. Drop a record on a card to bind its input; drop on Reads from or Writes to in the guide to choose the binding direction.

## Storage and scope

`studio_record_types` is the administrator-managed registry. Handoff types and read-only sources share this curated registry; source adapters are deployment-managed. The panel never enumerates the raw public schema.

`studio_records` is shared append-only storage. Each result has a new ID, tenant/company/facility, environment, record type/status, payload, evidence, producer agent/run, input record ID, registry/definition hashes and idempotency key. A status transition appends a successor; old evidence is not updated. Service access is SELECT/INSERT only. Browser roles have no grants. Registry access is server-side SELECT/INSERT/UPDATE, with audited compare-and-set updates.

Current server-authorized private scope: Bunting Magnetics | BMC | 500. Public installations require verified tenant membership and matching configured scope. No arbitrary caller-selected tenant/company/source table is accepted.

## Publication gates

- Published registry and approved compatible schemas; exact registry hash pinned in each binding.
- Every handoff input has another producer; READ source inputs use a curated certified source.
- Every output status has a consumer or explicit terminal declaration.
- Sources cannot be write targets; only READ cards bind source inputs.
- Approval statuses can be produced only by a human-approval COMMS step on COMPLETED.
- WRITE reads an approval status, retains its own approval gate and requires verified runtime approval evidence bound to the exact input/proposal/definition/scope.
- Legacy unbound packages cannot publish; rebind and rebuild.

Existing drafts remain immutable. The Inside Sales conversion preserves the prior version and keeps the existing deployed Agent 01 reference as monitoring metadata; it does not become another runnable build card.

## Shared harness

Packages export `bindings` and the tenant stamp in config.yaml. `BoundRunner.poll_once` supports bounded TEST handoff polling with cursor pagination, durable execution results, input/definition idempotency, schema validation and append-only result publishing. It accepts host-certified context/adapters and approval verification; it starts no scheduler by import or UI navigation. Source ingestion requires its own certified connector; raw source-table polling is refused. Registry revision drift and cross-scope records fail closed.

Polling uses immutable events. Terminal outcomes stop; reprocessing uses a deliberate new record/revision. Do not configure uncontrolled same-status feedback. A host coordinator must persist cursors, enforce certified package activation and route reconciliation. No production runtime or background dispatch was enabled in this release.

## Verified and still blocked

- 79 local and VPS-image tests passed, including record validation, tenant denial, source-write denial, stale registry denial, approval fail-closed and idempotent polling/publishing.
- FLUX transaction test inserted a synthetic handoff and rejected an invalid status, then rolled the transaction back. No test records remain.
- Database grants deny anonymous reads, authenticated inserts and service mutations of existing handoffs.
- Eight handoff types and seven source references were seeded as DRAFT. None claims an approved schema or working connector.
- Existing agents remain unchanged; Studio is a design surface. Actual record polling requires a separately activated tested package and certified host coordinator/adapters.
- Source adapters, Graph/HubSpot access, native document intake and business-specific schemas/approval policy remain certification dependencies.

Supabase access controls were checked against [official RLS documentation](https://supabase.com/docs/guides/database/postgres/row-level-security).
