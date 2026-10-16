# FLUX Studio iteration 2 verification

October 14, 2026 | Delivered design-only canvas iteration

## Implemented

React/TypeScript and React Flow replace the authoring form. The left navigation collapses to a 56px rail; the right 280px capability gutter has independent scrolling/collapse and becomes a bottom sheet at narrow widths. All nine capabilities and deployed Agent 01–04 references can be placed on the canvas. Positions persist without becoming execution state.

Dropping/tapping a capability immediately creates a recoverable draft and opens Explain the process. Sonnet drafts single responsibilities or a proposed split. The eight-step guide uses catalog dropdowns, with the two specified custom identity exceptions. Drafted choices retain explanations and provenance; user changes clear Drafted chips and retain an edit history. Human-only fields are stripped independently on the server. Blockers appear on the relevant step and review summary. Save, Validate and Publish remain separate; guided publication never activates execution.

The supplied guide matches the attachment exactly. Guide/catalog version is 1.0.0; hashes and dynamic catalog snapshots are recorded. Sonnet's server-only model ID is configured as claude-sonnet-5, verified through the provider API. Its provider transport is structured; Studio normalizes the compact provider encoding into the requested public fields object with nulls. Requests are limited to two attempts and a 60-second deadline, with a configured $0.25 total ceiling. Actual usage/cost and unknown interrupted usage are distinguished. Draft audits are studio_draft design activity, not agent executions.

Agent references point at the existing deployed identities and read-only source contracts. The email template replays exact committed records by shared message ID. A real handoff is observed without triggering capture or reading. Unknown portable contracts stay Unverified and keep edges amber. Proven required-field/type/enum/nullability compatibility can turn an edge green.

## Tested

- TypeScript and production frontend build passed; packages are pinned with a lockfile.
- 26 core/catalog/sanitizer tests passed, including every cross-field rule, locked-field injection, invalid options, nullable compatibility, incomplete responses, compact provider encoding and model-unavailable audit.
- 11 deployed design-only HTTP acceptance checks passed: published resource lookup, save/reopen, design validation/publication, execution denial, six-file export, committed-record replay, durable canvas storage, amber unknown edges, green proven nullable edges and unchanged shadow dispatch.
- Actual Sonnet calls returned DOC → READ → RULE for the specified acknowledgment example. A single-job description returned split=false with about 89% of unlocked choices filled. Injected authority instructions did not produce an authority value.
- A real browser drafting call streamed progress, proposed the same three-job split, and Add all 3 created the wired nodes.
- All nine capability cards passed tap-to-add and native desktop drag/drop checks. The dialog opened after each. Two automation-coordinate/scroll attempts were corrected using the visible geometry; these were browser-test targeting issues, not successful drops counted as failures.
- Both collapse settings survived reload. A saved split canvas reopened with Drafted chips and the human-edited trigger retained. The edited field showed Chosen by you instead of Drafted.
- A 400px viewport showed the bottom-sheet layout and tap-to-add. Viewport was reset afterward.
- Drafting was temporarily disabled for a real failure-path test. The dialog showed the unavailable message and Fill it in myself. A synthetic manual MAP design was completed entirely through the dropdown guide (plus the two allowed identity inputs), saved, validated and published. Sonnet drafting was restored. Its execution kind remains guided-design and dispatch_enabled=false.
- Existing Agents 01–04 still use their original images and October 13 container start times. Before/after FLUX monitoring worked and Agent 04 continued reporting shadow mode, dispatch_enabled=false.

All created acceptance definitions and decisions are explicitly synthetic. No new canvas agent ran against live data, no ERP write or communication occurred, and no existing pipeline behavior was changed.

## Still unverified or outside scope

Full portable schemas for Agents 01–03 are not available as verified canonical contracts. Existing source/table behavior and historical keys are observed; these do not prove full schema compatibility. Agent 04's repository contract is readable by reference.

The users/roles API currently exposes the authenticated private operator; it is not connected to a shared employee directory. Resource registries contain a small existing set; real business schemas, approved rules and procedures must be supplied and approved before relevant designs can be published.

Publication validates design contracts/governance and preserves fixtures as not executed. Runtime certification, activation, new-agent live execution, ERP writes, communications, loops and additional runtime adapters are outside this iteration. No new agent production run is claimed.
