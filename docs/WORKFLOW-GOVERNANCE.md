# Workflow governance release

The five requested improvements extend the earlier local MCP build-session implementation. The attached Agent Designer and app-improvement documents were treated as reference material. This release does not automatically approve generated schemas, add a full Agent Designer, enable business agents, or execute live connections.

## Whole-workflow validation

`validate_workflow(workflow_id)` and `read_workflow` report node/edge schema mismatches, absent required input guarantees, unreachable nodes, non-entry nodes without producers, cycles, ambiguous routing and declared outcomes lacking a destination. Nodes reachable through matching durable FLUX record/status bindings count as connected even without a visual wire.

`propose_connected_workflow` and `propose_connections` accept `entry_nodes` and `terminal_outcomes`. Entry identifiers resolve node keys to saved IDs. If no entry list exists, the first node is the inferred entry. Every declared outcome needs an edge or an explicit `{node, outcome, destination: "terminal" | "human_review"}` declaration. This allows legitimate terminal/review outcomes while detecting dropped work. Durable record bindings and existing approval/runtime checks remain separate publication prerequisites.

## Atomic related proposals

`propose_change_set(request_id,title,operations)` supports `update_agent_draft`, `propose_schema`, `propose_rule`, `propose_connected_workflow` and `propose_connections`. Each operation has `tool` and `arguments`; request UUIDs are derived from the outer UUID. References use stable canonical resource pins. Existing-object operations must all name the original base hash; the server applies them sequentially to an isolated candidate and produces one proposed revision per object.

The response and `read_change_set(change_set_id)` include the complete JSON-pointer before/after diff, members, dependencies and validation. AI connections shows the complete diff and offers “Apply entire change set (Off).” Staging changes no member draft or native object. Browser Apply verifies the base and saves all draft schemas/rules, edits and connected canvases in one PostgreSQL transaction. A late immutable-version or permission failure rolls back every member and its review state. Human Resources approval still follows saving the draft artifacts. Stale sets require a new proposal; request retries never duplicate the set.

## Sample sandbox

`sandbox_validate(draft_id,expected_hash,samples)` takes named JSON example documents and expected `{schema_valid,rule_passed}` booleans. It validates the draft input schema and its structured rules, including explicit absolute decimal tolerance. The response shows each expected/actual result, field-level schema errors and rule checks.

The checker runs in a separate isolated Python process: no adapter imports, no inherited credential environment, disabled sockets/DNS, CPU/wall-clock limits, file-size limit and Linux address-space limit. Samples are bounded by the MCP request limit and 20 cases. Samples/results are not stored in mutation history; existing MCP tool audit stores the result hash. This checks data contracts and rules; it does not OCR a binary document, transform outputs, certify a live adapter, issue approvals or authorize publication. It never posts to Epicor, sends mail, or triggers the operational runtime.

## Navigable blockers

Each finding contains rule ID, exact workflow/node/draft/edge location, affected fields and dependency metadata. Dependencies carry the canonical resource ID, status, hash, proposal ID, review URL and an executable read-tool description. Pending artifacts inside a staged change set link to `read_change_set`; after Apply, they link to `read_resource`. Missing artifacts name `propose_schema` or `propose_rule` as the resolution action. The review UI renders dependency links using safe same-site proposal anchors.

## Connection references and secrets

Agent definitions optionally declare `connection_requirements: [{connection_id,capabilities:[...]}]`; `update_agent_draft` can change this declaration together with a nonempty field patch. `list_connections()` exposes only approved, currently permitted IDs, systems, declared capabilities, owner attribution and status. It never returns credential paths, bodies or encrypted payloads. Missing IDs/capabilities produce `connection-permission-required` findings with explicit `missing_permissions`. Revocation removes visibility and revalidation immediately identifies the missing permission.

A company owner can POST `/api/ai-connections/approve-connection` with `request_id`, UUID `id`, existing `credential_id`, `credential_version`, `system`, and capability identifiers; `/revoke-connection` takes `request_id` and `id`. These require an authenticated browser session, normal Origin/CSRF checks and owner membership. Database checks require access to the existing credential and approved company scope. Capability vocabulary: mail.read/send, files.read/write, epicor.read/write, records.read/write. Approval is explicitly `owner_declared_design_access`; it does not claim provider verification or bind/activate a runtime adapter. An empty registry means no approved connection is available; no connection or capability is invented.

Drafts, change sets and samples reject secret-bearing keys and recognized token strings before persistence. MCP responses are checked before transport. The database independently rejects secret-bearing builder documents before append-only history writes. OAuth transport tokens remain in the established authentication channel and are not part of saved design content.

## Verification

Run the regression suite, `python -m unittest tests.integration.test_mcp_builder -v`, `node web/scripts/test-mcp-handoffs.mjs`, and the web build. New integration coverage includes whole-graph failures, navigable resource dependencies, unchanged members during staging, atomic Apply, forced late-write rollback, stale sets, sandbox expected/actual cases, permission metadata, revocation and secret exclusion. Local PostgreSQL uses synthetic authentication/ACL fixtures; deployed auth and native governance need separate verification.
