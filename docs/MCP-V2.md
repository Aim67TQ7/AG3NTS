# FLUX MCP v2

The MCP can propose a related workflow design in one change set, show the human its diff, and read permitted stored runtime results. Applying a proposal leaves execution Off. Resource approval, package publication and activation remain separate decisions.

## Build and review

1. Read `builder_context`, optionally with `detail: "summary"`. It includes the completeness matrix, permitted resources, design connections, credential kinds and templates.
2. Use `propose_change_set` with up to 30 operations. Give operations unique `key` values. Later operations can use `$schema:key`, `$rule:key`, `$instructions:key`, `$secret_request:key`, `$template:key`, `$workflow:key` and `$draft:workflow-key:node-key`. `$result:key` resolves the whole earlier result. References must point backward.
3. Read `read_change_set` by `change_set_id` or `proposal_id`. Findings have stable IDs and a node grouping. Structural errors reject the proposal; incomplete design produces publication blockers.
4. Review the diff in AI connections. Proposed choices appear in a separate highlighted list with their reasons. Explicit checkboxes confirm proposed authority, model and TEST choices and approve schema, rule and instruction contracts. One Apply saves all members in one database transaction, or saves none.
5. Run `run_fixture_suite` using a new `request_id`, the workflow ID and current `expected_hash`. Model fixtures additionally require `max_cost_usd`.

`list_proposals` and `read_proposal` expose this actor's proposals in the selected company. An agent response returns its own `proposal_id` and a separate `workflow_proposal_id`. `read_change_set` also accepts individual proposal IDs.

Validation resolves same-actor pending draft revisions first, then current permitted saved agent definitions. It preserves the saved canvas and returns `snapshot_content_hash`, `resolved_content_hash` and resolved revision metadata. Mutation preconditions use the saved `content_hash`. Runtime packages retain their version pins.

Use `detail: "summary"` on workflow, agent, resource and change-set reads to omit editor history, explanations and repeated dependency bodies. `detail: "full"` retains the review material. Existing calls default to full, except proposal inspection and runtime listing, which use compact metadata by default.

## Instructions, mapping, rules and fixtures

`propose_instructions` accepts versioned text plus `model_contract` with `output_schema`, `max_tokens`, `refusal_behavior` and `prompt_version`. The output pin must match the model agent's output schema. `propose_mapping` attaches output-field to input-path mappings. Agents can carry a class list and a message template.

Rule checks require `op`. Supported operations are `present`, `equals`, `equals_field`, `within_tolerance`, `percent_tolerance`, `date_within_days` and `for_each`. Paths support dotted fields and array indices. A `for_each` check names `path`, `baseline_path`, `match_by` and nested `checks`. Matching is type-sensitive and requires exactly one baseline match. Missing values, duplicate source keys, malformed dates and invalid numeric values fail closed. Tolerances must be explicit. FLUX does not invent Purchasing policy.

```json
{
  "op": "for_each",
  "path": "ack.lines",
  "baseline_path": "po.lines",
  "match_by": "line_number",
  "checks": [
    {"op": "equals_field", "field": "quantity", "baseline_field": "quantity"},
    {"op": "equals_field", "field": "unit_price", "baseline_field": "unit_price"}
  ]
}
```

This example checks exact equality for synthetic demonstration. It is not an approved variance policy. Rich rules execute in the sandbox and fixture runner. The existing package interpreter still certifies only its supported operations; approval of a richer rule does not certify its runtime execution.

Fixtures have a name, input and expected outcome/output fields. `propose_fixtures` updates the draft and invalidates prior proof. MAP, RULE and ROUTE fixtures execute locally. Other non-model capabilities require an explicit `adapter_result` in the fixture. That is a synthetic expected adapter response, not evidence that a mailbox, parser, ERP, Teams or write adapter works.

Model fixtures require browser-confirmed model selection, server enablement, configured Sonnet credentials, verified token prices and an explicit suite budget. Enable with `STUDIO_FIXTURE_MODELS_ENABLED=true`; otherwise `STUDIO_DRAFT_ENABLED` is the legacy fallback. Set an explicit false value to disable fixtures independently. JEV and Opus fixture execution remain unsupported. The runner reserves budget before provider calls, bounds output tokens, records reported usage and preserves a held reservation if usage is unknown. Replaying a completed request does not call the provider again. Receipts report `usage_complete`, known cost, node fingerprints and fixture results. A new prompt, model, setting, mapping or fixture set invalidates the proof. Failed/incomplete model output blocks the suite. Model refusal is treated as a failed fixture and requires review.

For v2 model drafts, Teach publication checks the stored passing fixture receipt for the current contract. Package tests and adapter certification still apply independently. The fixture runner cannot publish or activate an agent.

## Secrets and connections

`list_secret_kinds` returns required field names and scope vocabulary, never values. Registered kinds include Graph app/delegated, Epicor REST/BAQ, SharePoint, SMTP, API key, webhook HMAC and Teams app credentials. Use the advertised field names and scopes rather than the illustrative brief's aliases.

`propose_secret_request` accepts `key` or `resource_id`, purpose, kind, systems, scopes, environment, accountable role, rotation interval, node references and required field names. It rejects values and reuses requests with the same kind, environment and scope set. Separate read and write requests. READ agents cannot claim send/write permissions.

A browser company owner applies the request and fills its vault form. The values go directly to encrypted credential storage. The MCP receives the connection ID and safe fulfillment metadata. Approval records design access; authentication and runtime authorization remain unverified. TEST and PROD connections have separate environment metadata. PROD requests require `test_workflow_id`, `test_workflow_hash` and passing fixture proof on every current TEST node. Requesting PROD credentials does not create a PROD draft or enable execution. Direct MCP agent proposals remain TEST-only.

Graph and Epicor REST forms reuse the existing credential validators. Other registered kinds are encrypted metadata/credential contracts; their adapters still require independent verification. Credential storage, connection approval and fulfillment metadata are separate operations. If a failure occurs between them, an owner must reconcile the partial credential through Resources before retrying. No credential values appear in proposals, audit or runtime reads.

`list_connections` distinguishes approved design connections from external runtime bindings. Existing Maggie mail packages appear as `external_runtime_package`, with their gate status and last-seen metadata. They do not become reusable design connections automatically.

## Runtime observation and archival

`list_runs(workflow_id, since?, outcome?, cursor?, detail?)`, `read_run(run_id, detail?)` and `read_record(record_type, id, detail?)` resolve verified tenant, company, facility and current workflow ACLs. Lists have 50-item keyset pagination. IDs use `job:` and `mail:` prefixes for runs. Record reads use the unprefixed record ID and exact declared record type.

Current sources are scoped TEST runtime jobs and artifacts linked to the exact company-scoped mail package and definition hash. Historical unassigned imports and old package results without that linkage are excluded. Generic jobs expose results through `read_run`; `read_record` currently covers declared mail result records. Reads return permitted result JSON, metrics, errors and file IDs. They omit attachment bytes, credential fields and signed download locations. Each observation emits an audit event.

`archive_workflow` proposes a recoverable archive for browser review. Apply checks the latest workflow hash and edit permission again and refuses active runtime packages. It records an archive event and preserves snapshots, shared agents and audit history. There is no permanent-delete MCP tool.

`propose_template` saves a validated Off workflow design without credential bindings. This release permits parameter slots for existing node company, department and source-system fields. Mailbox-value parameterization and template instantiation are not implemented.

## Acceptance boundary

The supplied PO-acknowledgement brief names seven agents, although it says six. Teams delivery needs an approved Teams connection or a third request in addition to mailbox and Epicor read access.

The regression test builds all seven capabilities, three schemas, two instruction sets, a rule, fixtures, three secret requests and routed edges in one proposal, applies once and runs all fixtures. It uses synthetic external results and mocked model calls. It intentionally retains missing governance and connection blockers. It does not establish a zero-blocker production workflow or perform real PO matching or Teams delivery.

Builder session documents remain bounded at 2 MB and change sets retain their reviewed base state. Long-lived sessions with many proposals can reach that limit. Summary reads reduce response size, not stored session size.
