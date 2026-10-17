# Operis interface

The builder creates one agent with one responsibility. Workflow planning is a separate experience.

## Builder

Six focused steps: When, Input, Job, Result, Failure, Check. Each step asks one question and presents only its relevant primary controls. Access authority and required approval remain explicit. Technical choices remain available in expandable settings; unresolved decisions and business questions remain visible in review. Changing a mailbox never grants access. Saving a draft never enables execution.

Name and workspace identity belong in agent details and review, rather than repeating on each step. Technical record IDs belong in details. Capability and authority choices are filtered to the selected agent's job, preserving existing selected values for review.

## Consistency

Current names resolve by agent ID from the latest saved version. Historical names remain in execution evidence and installed version details. Presentation does not rename or republish stored definitions.

Design status and runtime state are separate. Runtime vocabulary: Running, Held, Off, Stopped, Checking, Unavailable, Unverified. Draft describes a design with no installed runtime, after runtime lookup succeeds. A pending status lookup must not display a draft/off assertion or a partial total as a confirmed count.

Dashboard workflow totals count workflows, not review items. Archived browser-cached canvases must not reopen as active workspace drafts.

## Layout and accessibility

Three layout thresholds: 640px, 960px, 1280px. Below 960px navigation becomes a horizontal labeled strip and workflows become a read-only list. Desktop also offers a list view. The approved canvas hub assets, geometry and edge attachment remain intact. A zoom notice identifies overview scaling.

Body text uses a 14px floor; true captions may use 12px. Inputs use 16px in the focused builder. Main actions target 44px; builder step tabs use 48px. Keyboard focus has a visible outline. Tables scroll within their own region rather than forcing horizontal page overflow. Resource archive actions are distinct from locking and remain recoverable.

Page selection is represented by `?view=...`; saved canvases also carry `workflow=...`. Legacy email-result links remain supported. Back/Forward uses the browser history. Loading, failure and empty states should explain the current situation. Workspace loading has a progress message, timeout and retry; page render failures have a recovery view.

## Validation

Run `pnpm --dir web run build`, `node scripts/check-web-design.cjs` with the bundled Node runtime, and the Python unit suite. Browser checks should cover 390px, 548px and 1440px. Use a separate verification tab and navigate installed agents without editing, saving, activating, or processing real email.
