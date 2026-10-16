# FLUX workflow runtime — October 15, 2026

## Shipped

The public ZODA-backed app has a VPS Python worker, durable workflow states, a leased job queue, immutable step results and runtime audit events. Workflows, Build Agent, FLUX Monitor and Execution History expose Test once, Activate, Run now, Pause and Stop. Input fields follow the first agent's schema; structured inputs also have an advanced editor. Results display one row per executed agent.

The worker starts with the app and resumes claiming durable queued/scheduled work after restart. Its independent heartbeat is shown from database telemetry, not a static health label. A narrowly scoped worker key is stored outside the image under PETE's mounted references directory with owner-only permissions; only its hash is registered in ZODA. The container remains unprivileged and read-only. Runtime keys/references are excluded from the Docker build context. No Bunting operational service was changed.

## Live evidence

- Test job `a8a4d840-269b-4aae-a77c-7cfbbc01f379` completed two real Python harness steps on synthetic input `{amount: 42}`: MAP saved `{total: 42}`, then RULE saved a passed check.
- Active run `a7305dee-0547-4c44-beb5-75e6ebff4c99` completed the same pinned workflow through Run now.
- A one-minute schedule produced completed durable runs after container recreation, including `ed8e2144-e277-472a-961e-fd1f146c3be7` and `1822e1b2-06fb-4738-90ea-4c01ca9cdc9e`.
- Pause rejected new work. Stop rejected new work and cancelled further processing. The sample schedule was stopped after verification.
- Invalid synthetic input stops after the first agent with REVIEW_REQUIRED and appears in Human Review; no downstream agent runs.
- A rolled-back database fixture verified worker-only decryption of an encrypted credential with tenant/version/hash and use-role checks. No real connection credential was used in that test.
- 98 local and image-build tests passed. Additional live read-back checks covered actual queue execution, active jobs, scheduling, restart persistence, pause and stop.

These are real executions of synthetic test data. No mailbox was read, no model parsed a real document, no ERP record was written and no message was sent.

## Supported execution

- MAP: approved deterministic field mapping.
- RULE: approved equality/presence rules; discrepancies stop for review.
- ROUTE: terminal route-record output. Branch dispatch is blocked.
- READ: read-only Epicor JSON GET transport using one manually selected encrypted connection. It requires an HTTPS base URL, company code, API key, optional basic authentication and comma-separated allowed path prefixes. The request URL must include the configured company. Redirects and private/internal addresses are blocked; response size is bounded. Real Epicor connectivity remains unverified until a client supplies and tests its connection.

Graph ingestion, DOC, CLASS, REASON, external business writes and communication sending do not yet have approved execution adapters. They fail readiness checks rather than appearing active. This release does not make the full supplier-confirmation workflow operational.

The worker executes the reviewed structured job specification through the same `flux_harness` used by generated Python wrappers. It does not execute arbitrary uploaded Python or shell commands.

## Admission and authority

A normal workflow needs tested, hash-pinned build artifacts matching its exact saved card versions, unchanged interview/fixtures, confirmed package README, TEST scope and compatible input/output schemas. Credential selections bind the agent, selecting user, client, resource hash and version. Worker-side checks revalidate artifacts, review receipts and credential selections.

Execution order follows declared durable record bindings, or matching output-record and trigger-source types, never visual card positions. Cycles, ambiguous writers, disconnected cards, joins and unsupported direct communication are blocked. Each step's result is saved in FLUX before the next begins.

Activation is Admin-only and requires a completed test of the exact definition hash. Builders can test; viewers cannot execute. Current owner membership is checked before claiming and between steps. Archived credentials or revoked use roles block resolution. The worker never returns decrypted credentials to the app, the AI or result rows.

Pause prevents new work and checkpoints after an in-flight step. Stop prevents the next step and cancels queued work; an already-running HTTP request may finish. An expired lease after an interrupted run becomes REVIEW_REQUIRED instead of silently replaying uncertain work. Scheduled work is bounded to one pending/running run per workflow. No external write adapter exists in this release.

## Operating a workflow

1. Configure the actual company/facility under Client & users.
2. Save and approve schemas, instructions and rules. Save connection credentials in Resources and manually select the appropriate credential on each agent that needs one.
3. Teach/build each agent, review its fixture results and confirm its package README. Save the canvas with explicit handoff contracts.
4. In FLUX Monitor → Runs, select the saved workflow and provide an input record.
5. Select Test once and inspect the agent result rows. Resolve blockers or review outcomes before continuing.
6. Choose manual input or an interval and select Activate. Use Run now for an active manual workflow, or let the selected schedule submit the configured input.
7. Use Pause/Stop and inspect actual run history/audit as needed.

The built-in sample is explicitly synthetic and requires no credential, company assumption, provider call or external integration.


## Workspace simplification - 2026-10-15

- Workflows is the build canvas with a side palette of nine agent types and a saved-agent selector. Planning and secondary controls are collapsed. Run controls live in FLUX Monitor.
- Monitor has Runs, Input records and Results tabs. Inputs are the client-scoped submitted runtime job inputs, paged 25 at a time, rather than an operational mailbox or ERP intake feed. Existing synthetic input read-back was verified in the authenticated live UI.
- Client, Company and Users are compact cards with dropdowns. Company creation and user grants are collapsed. Existing account APIs, client switching and authorization remain in force. No access grants were changed during verification.
- Explain the process accepts one PDF, PNG, JPEG or WebP example up to 5 MB plus a description of the items to extract. Selection stays in browser memory until Draft is clicked. The server rejects absent consent, unsupported/mismatched formats, invalid base64, missing extraction notes and oversized files before contacting the provider.
- Consented examples use native document/image message blocks and are included in token counting. Audit retains example hashes, size, type and consent, not source bytes or extraction-note text. Derived draft content may include information from the example. Files are untrusted source material, not authority to add actions or permissions.
- 107 automated tests passed, including mocked PDF/image transport and hash-only audit evidence, rejection checks and client-scoped input paging. The live browser upload test was blocked by the ChatGPT Chrome extension's missing file-URL access permission; no file was sent to Anthropic in this verification. A real file-to-provider draft remains unverified.


## Dashboard, human decisions and Graph setup - 2026-10-15

- Authenticated root now lands on Dashboard. Saved workflows appear in a left column; review cards are the primary workspace. Public `/` and `/overview` contain static product information and a Sign in link to `/auth/login`; anonymous workspace API requests remain HTTP 401. Verified with unauthenticated HTTP requests and the live auth-link browser flow.
- Approve, Return with feedback, Reject and Escalate create an immutable `agent.review_feedback` record under client-scoped `runtime-reviews/`, plus requested/recorded audit events. Decisions bind the original input/result/definition evidence hash and the failing step's agent/build/package identity. Admin or Builder role is required. Original runtime jobs are unchanged and no decision automatically resumes execution or authorizes an external action.
- A feedback receipt can open the matching agent from that workflow's latest saved canvas. If that agent version is unavailable, the UI reports that rather than adding a card to an unrelated canvas.
- Live verification recorded feedback on the existing synthetic runtime sample only (run `84b2e08f-e79a-416d-afa2-f688485aa1f6`). The item left the pending queue and remained closed after page reload with test items shown. No ERP, mailbox or provider action occurred.
- Graph credentials now capture tenant ID, app/client ID, client-secret value, optional expiry, mailbox and folder. Fixed Microsoft authority/Graph endpoints and `.default` scope are set server-side; mailbox target is explicit. All configuration is encrypted by the existing client vault. Mail.Read consent and mailbox access remain unverified; the Graph read-test/execution adapter is not connected. FLUX login does not grant Microsoft mailbox access.
- 117 automated tests passed locally and in the deployed image, including human-decision scope, evidence changes, duplicate closure, no auto-resume, public information vs protected APIs, and Graph configuration validation.
- Corrected the sample-drafting request boundary to allow a bounded base64-encoded 5 MB example only on the drafting endpoint; other mutation requests retain the 1 MiB cap.

## Agent switches - October 15, 2026

- Saved-agent library, canvas cards, and focused builder show a persistent server-backed power switch. Green glow means this exact agent version belongs to an active TEST workflow with a recent worker heartbeat. Red means off. Amber means armed/held or the worker is unavailable. A status fetch failure remains unknown, never green.
- Admin-only changes use a client-scoped private control table, optimistic revision checks, and durable runtime audit events. No direct anonymous/authenticated table grants exist. Switching one agent off holds active workflows containing it. The worker rechecks that agent/version immediately before each non-test step and holds the job rather than skipping the agent. An already-started external request can finish.
- Turning on requires the exact saved canvas, matching built/reviewed package, successful TEST workflow version, healthy worker, and existing operator input/schedule. Unsupported Graph email reads remain off with a specific blocker. Multiple explicitly disabled agents can be armed in sequence; the workflow resumes only when all pins permit it. Tests remain an explicit separate action.
- Live synthetic job de1ab31b-7aa9-4fc7-a02a-d4742b038924 completed both MAP/RULE steps at 2026-10-15 20:25:34 America/Chicago. Output passed=true. No email, attachments, provider, or ERP actions occurred.
- Database tests verified off pauses the workflow and holds the job, an enabled exact version permits the step, and a changed version holds it. Those database test rows and temporary worker identity were rolled back. Anonymous control reads and unauthenticated worker gate calls were denied.
- Email-listener activation remains blocked. Saved mailbox configuration is not evidence of live Microsoft email detection.
