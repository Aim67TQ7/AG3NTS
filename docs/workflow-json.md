# Portable workflow JSON v1

Open a workflow, choose **Workflow JSON**, then **Export current workflow**. The editor supports JSON files, validation, download, and import as a new TEST draft. Editing JSON never changes the current workflow until an explicit import creates a new one.

`format: operis.workflow` and `schema_version: 1.0.0` identify the format. The JSON Schema is in `workflow-package.schema.json`.

A package contains `workflow.name`, `workflow.steps`, `workflow.connections`, and `resources`. Each step defines capability, name, responsibility, the six functions (trigger, input, execute, output, error, verify), configuration, JSON input/output contracts, record bindings, resource slots, and optional canvas position. An `adapter_hint` describes an existing adapter; it grants no authority.

Connections identify source step/outcome, destination input, durable-record delivery, record type, and status. Validation checks IDs, references, cycles, contract compatibility, size, version, and credential exclusion. Missing schemas, disconnected steps, and unresolved resource slots remain visible setup items. Definition validation is distinct from runtime readiness or proof of business execution.

Resources carry portable content for permitted schemas, rules, instructions, templates and assets. Credentials carry named slots only. Encryption payloads, selection receipts, keys and credential-bearing URLs are excluded. Do not put secrets in arbitrary prose or business data; automated secret-pattern detection cannot identify every possible secret string.

Import creates a fresh canvas and agent IDs in the destination client/company, forces TEST, clears credential selections and installed runtime bindings, and retains the package's resource definitions with the draft. It does not publish resources, certify adapters, restore approvals, start listeners, dispatch records, or activate workflows. Map/approve resources through the existing resource controls, review all six functions, build and test before separately authorizing execution. The current general runtime still requires its supported adapters and unambiguous handoff contracts; a JSON package alone does not expand runtime support.

Only configured agent cards are portable. Historical execution records, attachments, and provider data stay in their source stores. File and record references belong in the JSON; their contents are not automatically copied.
