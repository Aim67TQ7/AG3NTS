# Operator deployment notes

Owner-private access uses the existing SSH boundary. UI: http://127.0.0.1:8496. Reconnect with `ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:8496:127.0.0.1:8496 hostinger-vps`.

The existing /opt/flux-studio deployment remains in place. Only Studio is rebuilt; Agent 01–04 containers and code are unchanged. Their source paths are mounted read-only for reference discovery. Studio metadata/audit remains in the existing private FLUX Storage bucket; no existing tables or dispatcher were changed.

React/TypeScript uses React Flow, pinned packages and pnpm-lock.yaml. Build with the package scripts in web/. Copy the resulting dist along with app/, guides/, catalog/ and tests/, then use the existing Docker Compose release. Healthcheck confirms FLUX connectivity. A rollback image is tagged flux-studio:iteration1-rollback.

Drafting model ID is read from STUDIO_DRAFT_MODEL; its default is in catalog/studio-config.json. Keys remain only in the existing root-only server environment binding, never source or client bundles. Configured Sonnet 5 prices were checked against the official provider publication, whose URL/date are in that configuration. Each call reserves input and output budget across no more than two attempts and a 60-second deadline. No retry is issued after ambiguous in-flight charging; cancellation/timeout audits retain unknown usage when no receipt was received.

The provider's structured-output compiler limits the number of nullable/object fields. Its internal transport therefore uses a compact array and empty-string sentinel. Studio maps these back into the specified fields object with nulls before exposing a response, validates IDs against the exact catalog snapshot, and strips human-only suggestions independently of the provider schema.

Design publication never activates a guided agent. Its export carries execution kind guided-design, dispatch OFF and fixtures marked not executed. The pre-existing supplied-data interpreters remain available through their original backend routes and tests; the canvas cannot dispatch them or the deployed pipeline.

Tests: `docker exec flux-studio python -m unittest discover -s /srv/tests -v`. Deployed design acceptance uses tests/canvas_acceptance.py. Actual provider tests use tests/draft_live_acceptance.py and synthetic descriptions only; these incur bounded model costs. Preserve stored synthetic evidence rather than deleting it.
