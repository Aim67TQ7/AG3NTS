# FLUX MCP build sessions

This change was deployed to PETE at https://flux.by-pete.com on 2026-10-16, together with the workflow governance extension. The ZODA migration has been applied. See WORKFLOW-GOVERNANCE.md and the deployment verification report for current evidence. All MCP writes are design proposals. Browser Apply saves Off draft canvases or draft Resources entries. Existing Resources approval, Teach/Build, package review, publication and activation gates remain required.

## Tools

| Tool | Behavior |
|---|---|
| `read_agent_draft(draft_id)` | Reads legacy MCP proposals, visible guided Agent Library definitions, canvas-embedded guided drafts, and current build-session proposals. Returns the saved body, revision, content hash, review state and fresh validation. |
| `update_agent_draft(request_id,draft_id,expected_hash,fields)` | Patches exact catalog fields; unrelated fields and existing human provenance survive. Updates every session canvas containing the draft atomically. Changes invalidate previous review. A standalone Agent Library edit is proposed on an Off review canvas; it does not replace or republish the original definition. |
| `submit_agent_draft(request_id,agent)` | Backward-compatible tool name and value/why field shape. Now rejects invalid/human-only choices explicitly and creates a reviewable single-agent workflow proposal. Omitted choices become null. |
| `propose_connected_workflow(request_id,name,nodes,edges,workflow_id?,expected_hash?)` | One atomic proposal for a bounded graph. Each node has a unique `key` and either an `agent` or an owned `draft_id`. Edges name node keys or existing workflow node IDs and declare `on_outcome`. Existing workflow changes require its current hash. |
| `propose_connections(request_id,workflow_id,expected_hash,edges)` | Adds edges atomically. Checks membership, declared outcomes, acyclicity, one target per source/outcome, and conservative schema compatibility. Duplicate edges are deduplicated. |
| `propose_schema(request_id,resource_id,version,label,schema)` | Validates the existing object JSON Schema contract, including its prohibition on external/recursive references. Returns `schema:tenant.id@version`. |
| `propose_rule(request_id,resource_id,version,label,rule)` | Structured checks: `present(field)`, `equals(field,value)`, or `within_tolerance(field,baseline_field,absolute_tolerance)`. No expressions or executable code. Tolerance must be finite and nonnegative. Tolerance artifacts remain blocked for runtime use until a supported runtime is separately certified. |
| `propose_discovery_waiver(request_id,reason,assumptions,credential_requirements,accountable_roles)` | Proposes an explicit client/company waiver. Only the authenticated client owner can authorize it in the browser. Records owner and database timestamp; does not create discovery answers or hashes. |
| `submit_workflow_plan(request_id,source,plan)` | Adds workflow-hash and approved-waiver sources; the original discovery_revision/discovery_hash input remains accepted. Plans remain design artifacts and accepted plans appear in AI connections even without a discovery assignment. |
| `read_workflow(workflow_id)` | Preserves the native canvas fields and adds proposal revision/hash, node-level validation, connection findings and durable-record-binding blockers. |
| `get_catalog()` | Stable catalog, SHA-256 cache key, option definitions and rule metadata. There are **23** catalog rules, not the reported 24. Owner/company choices are resolved from verified context; resource pins come from the resource tools. |
| `list_resources(kind?,status?,offset?,limit?)` | Compact canonical IDs, versions, labels, status and content hashes; maximum page size 100. Excludes credentials and encrypted payloads. |
| `read_resource(id)` | Full non-secret artifact content at an exact immutable pin, with its canonical content hash and approval status. |
| `builder_context()` | Legacy combined context remains available with verified identity, dynamic catalog, deduplicated resource metadata and schema bodies. Prefer the split tools for subsequent calls. |

Existing discovery, profile and preference tools remain available. `tool-catalog.json` in the deliverable contains the complete machine-readable input schemas.

## Agent fields, validation and identities

A draft has one capability and one responsibility, with Trigger, Input, Execute, Output, Error / Failure, and Verify fields. Supply three name options and three responsibility options. `fields` maps exact catalog paths to a string/null or `{ "value": ..., "why": ... }`. Arbitrary `source` or provenance properties are rejected.

The server derives `identity.owner` from the OAuth connection. A matching owner ID may be supplied; a different owner is rejected. Company is connection-scoped and environment is TEST. Authority, approval and model-access decisions remain human-controlled; matching previously saved human choices can survive an edit. Missing choices can be saved but remain blocked.

`studio.blockers` remains the authoritative catalog-rule implementation. The response adds actionable findings shaped as `{rule_id,field_paths,message,blocks_publish}` plus dependency and durable-handoff findings. This is design validation, not runtime certification. A syntactically valid incomplete proposal is saved with `blocks_publish: true`. Unknown paths/options, invalid types, malformed contracts, unauthorized identity and known-incompatible graph connections are rejected before persistence.

Errors are JSON in MCP text content with `isError: true`: `{ "error": { "code": "invalid_option", "field_path": "output.record_type", "submitted_value": "bogus", "allowed_values": [...] } }`. Secret-looking input is rejected before values can be echoed. Conflicts use `code: conflict`; re-read and reconcile before issuing a new request UUID.

## Persistence and review

Each user/client/company has a private versioned design document. The transaction takes a per-scope advisory lock, checks its revision, checks the client UUID/request hash, writes all changes together, and stores the exact response for retries. Reusing a UUID with different content conflicts. Legacy and new proposals share the UUID namespace. New resource content at an existing version conflicts; identical content deduplicates using the content hash, not the library-envelope hash.

The private append-only history includes actor, request UUID, document revision, changed records and fields, validation, hashes, action and database timestamp. Review adds actor/time; native inserts also pass through the existing governance guard/audit triggers. Private tables have RLS enabled and no direct anon/authenticated grants. The RPC resolves the existing MCP grant or authenticated browser session and verifies current client membership/company access. It filters native reads through existing object permissions. MCP tokens cannot call browser review.

One connected workflow is one inbox proposal and one native canvas insert on Apply. Positions start at x=100, y=120 and advance by 360. Stable UUIDs identify drafts, nodes, edges and review proposals. Semantic edges are saved with outcome handles and `dispatch_enabled: false`; the canvas projection maps the visual source handle to `output` without changing saved outcomes. These proposed lines do not supply durable record bindings or authorize direct agent calls.

Resources follow proposed -> browser Apply -> draft Resource -> existing human Approve -> canonical approved artifact. Apply does not approve a resource. Canonical resource hashes always cover artifact content; library metadata envelopes keep their existing separate hashes. Publication remains blocked until the exact canonical resource version is approved. Review/canvas hashes and canonical resource content hashes serve different objects; use each response's hash for that object's operation.

Waiver source: `{ "kind": "waiver", "waiver_id": "waiver-...", "content_hash": "..." }`.
Workflow source: `{ "kind": "workflow", "workflow_id": "canvas-...", "content_hash": "..." }`.
Discovery source: `{ "kind": "discovery", "revision": 1, "content_hash": "..." }`.
For workflow/waiver plans, `discovery_question_ids` may be empty. No fake discovery revision is required.

## Local checks

Use the app's existing Python dependencies. Put Node on PATH and install pnpm if needed:

```sh
pnpm --dir tests/postgres install --frozen-lockfile
pnpm --dir web install --frozen-lockfile
python -m unittest discover -s tests -p 'test_*.py'
python -m unittest tests.integration.test_mcp_builder -v
node web/scripts/test-mcp-handoffs.mjs
pnpm --dir web run build
```

The PostgreSQL integration harness uses pinned PGlite 0.5.10, an actual PostgreSQL engine running locally. It executes the migration and transaction/RLS/immutability logic. Existing OAuth grant resolution, company permissions and object ACL helpers are synthetic contracts in `tests/integration/builder_bootstrap.sql`. No production data, credentials or external actions are used. These tests do not certify live OAuth, real deployment, or real resource approval. Existing regression tests separately cover the application auth/review/runtime behavior.

## Release procedure

1. Review `migrations/20261016_mcp_build_sessions.sql` against the current ZODA schema and existing auth, object and audit guards. Back up the current application release and schema. This migration was applied to ZODA on 2026-10-16.
2. Apply the migration to an isolated/staging copy first. Exercise actual OAuth, native governance triggers, concurrent connections, current membership revocation, browser review and Resources approval with synthetic records.
3. Rebase the source overlay/patch onto the current release. The baseline here was a read-only snapshot of `/home/pete-dev/flux-studio` on `pete`; the older local project checkout has unrelated unfinished Designer changes and was not overwritten. Reconcile any drift using the baseline hashes.
4. With deployment authorization, migrate ZODA before releasing the app code, build the web assets and use the existing managed deployment procedure. The owner authorized VPS deployment; Git was explicitly skipped.
5. Reconnect/refresh the MCP client's cached tools. Verify a real client login, a connected canvas and browser review. Publication/activation require their existing separate authorization and review gates.

For rollback, restore the previous application release and leave the private history intact. Do not delete audit or request records to roll back. New native drafts can remain Off and be archived through the normal UI. The down migration is deliberately omitted to preserve audit evidence.

## End-to-end example

`examples/mcp_build_session.py` contains a complete proposal-only client. It proposes an object schema and explicit tolerance rule, creates a seven-step connected workflow, patches the Retriever's `output.record_type` and `execute.rule`, then reads the agent, workflow and resource list. It asserts seven nodes/six edges and the pending-dependency blocker. The recorded local synthetic result is `example-result.json` in the deliverable.

HTTP mode requires an explicit endpoint and an existing OAuth access token in `FLUX_MCP_TOKEN`; the script does not perform OAuth or print the token. Use a stable `--session-id UUID` for retries. Do not point the example at production until the change is authorized and deployed.
