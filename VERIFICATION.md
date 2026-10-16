# Deployment verification

October 13, 2026, America/Chicago.

Running service: flux-studio on the Bunting VPS, private loopback port 8496. Owner access is through SSH, with the UI at http://127.0.0.1:8496. Container health verified against actual FLUX connectivity.

30 checks passed: 12 core unit tests; 14 deployed acceptance checks; 1 deployed review check; 3 resource/security checks. JavaScript syntax check passed. Browser verification created supplier-name-mapper v0.1.0 through the authoring UI and confirmed the saved definition in the library. The four existing deployed identities, health and durable history were observed in the library/monitor. Screenshot: studio-proof.png.

Real synthetic FLUX records were created for MAP/RULE agent definitions, schema/instruction resources, a two-stage workflow, inputs, immutable results, failure results, review outcomes, approvals and control audit. These are explicitly synthetic acceptance records; no live business operation was performed. Duplicate keys returned the original result; conflicting keys and resource hashes were denied and audited. Definitions could not be overwritten. Pause blocked the manual workflow runner, and resume restored it. Export contained exactly six agent definition files.

The earlier execution acceptance-2037deb8-c1bb-40d8-b746-eebe47d47f9a remained readable after multiple service rebuilds/restarts. Existing agents stayed active; Agent 04 health continued to report dispatch_enabled=false.

Verified scope: deterministic P0 MAP/RULE authoring/execution, linear manual workflows, durable results and history, internal review decisions, schema/instruction/rule registration and production Agent 01–04 read-only monitoring. Other runtime classes, full PO confirmation, multi-user identity/company permissions, unattended scheduling and Power Automate adapter conformance remain unimplemented.

October 14 update: this file is the iteration 1 evidence record. The current canvas behavior and verification scope are described in ITERATION-2-VERIFICATION.md. New canvas definitions are design-only.
