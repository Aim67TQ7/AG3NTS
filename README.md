# AG3NTS — FLUX Studio

FLUX Studio builds and operates agents with explicit responsibilities, durable FLUX handoffs, versioned contracts, audit evidence and human review. This repository contains the full current application source captured from the PETE server on October 16, 2026, including that day's deployed MCP/validator fixes.

[Live application](https://flux.by-pete.com) · [MCP endpoint](https://flux.by-pete.com/mcp) · [MCP guide](docs/MCP-BUILD-SESSIONS.md) · [Governance](docs/WORKFLOW-GOVERNANCE.md)

## Features

- React/TypeScript workflow canvas, nine agent capabilities and guided agent builder.
- Versioned resources, schema contracts, outcome routing and immutable drafts.
- Company-scoped accounts, credential references, human review and audited power controls.
- OAuth MCP builder for proposing agents, workflows, resources and related change sets.
- FastAPI backend, bounded runtime, execution history and existing canvas-mail adapters.

One agent owns one responsibility. Agents exchange durable records. Applying a proposal, approving a resource, publishing a definition and activating execution are separate actions. A healthy service or saved draft does not prove a business integration works.

The unfinished local Agent Designer/workflow-designer branch is not included in this server-source snapshot. Older verification documents describe historical states.

## Source layout

| Directory | Contents |
| --- | --- |
| `app/` | API, authentication, builder, MCP, validation, runtime and reviews |
| `web/` | Frontend source, static pages, dependency lockfile and image assets |
| `catalog/`, `guides/` | Capabilities, options, governance rules and builder guidance |
| `flux_harness/` | Bounded execution contracts and harness |
| `migrations/` | Available incremental database migrations |
| `deploy/` | PETE deployment examples and mail bridge |
| `tests/` | Unit, acceptance and PostgreSQL integration tests |
| `examples/`, `scripts/` | MCP example and catalog-to-SQL lock-policy generator |

## Build and test

Requires Python 3.12, Node.js and pnpm:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pnpm --dir web install --frozen-lockfile
pnpm --dir web run build
python -m unittest discover -s tests -q
pnpm --dir tests/postgres install --frozen-lockfile
python -m unittest discover -s tests/integration -q
```

Integration tests use an isolated local PGlite database and synthetic fixtures. They require no production mail or ERP access. Set `FLUX_TEST_NODE` to your Node executable when necessary. Build `web/dist` before starting the API or building Docker; generated assets and installed dependencies are excluded from Git.

## Configuration and startup

Copy `.env.example` to `.env` and load it into the process environment using your launcher or secret manager. Uvicorn does not load this file automatically. With dependencies installed, frontend built and environment loaded:

```sh
uvicorn app.main:app --host 127.0.0.1 --port 8496
```

`FLUX_FRESH=1` selects the ZODA adapter in `app/fresh.py`, which contains the current project endpoint and its publishable key. Authentication, company membership and server/database checks still determine access. `STUDIO_PUBLIC_HOST` must match the hostname. Authentication and origin checks assume HTTPS; starting this process does not provision an authenticated development workspace.

AI drafting is optional. Configure a provider key securely, an approved model and verified prices before enabling it. Legacy `PZLO_*` environment names remain in compatibility code; they are not instructions to connect this release to operational PZLO.

This is a full application-source snapshot, not a database backup or fresh-project installer. It depends on existing ZODA schemas, authentication/RPCs, private storage, tenant/company records and permitted connections. Included migrations are incremental, not the entire original database bootstrap. Mail adapters also depend on separately configured services and credentials.

## Deployment

```sh
docker build -t flux-studio:local .
```

Docker runs the unit suite and expects the built frontend. Review deployment examples for hostnames, ports, paths, networks, secret mounts and external references before using them elsewhere.

The existing PETE release uses `/home/pete-dev/flux-studio`:

```sh
sudo -n /usr/local/sbin/flux-studio-admin status
sudo -n /usr/local/sbin/flux-studio-admin update
```

The helper rebuilds and waits for service health. `/readyz` confirms readiness, not mailbox delivery, parsing or ERP behavior. Saving this repository does not deploy or alter runtime workflow state.

## Validator release and verification

[October 16 verification report](docs/VALIDATOR-VERIFICATION-2026-10-16.md)

Identical schema hashes now pass compatibility. Record-type collisions have separate node findings. Python and the generated private SQL predicate use the catalog's capability-aware lock metadata. Protected choices remain human-owned, with all protected fields listed together in errors. Connection diagnostics include caller keys, schema pins/hashes and pending proposals; pending changes are not silently merged.

The deployed build passed 185 unit tests. Another 24 local PostgreSQL integration tests and authenticated HTTPS MCP acceptance checks passed. Read-only replay of the affected canvas confirmed the edge fix. Existing user proposals were not applied. The Bunting AI-connections review page separately returned HTTP 500 while the synthetic review endpoint passed; this remains documented and unresolved.

Migration `20261016163110_flux_builder_catalog_locks.sql` is already applied to ZODA. Review migration history before applying it elsewhere. Generate policy SQL with `scripts/generate_builder_lock_sql.py` when catalog locks change; integration tests compare every option across all capabilities against the database predicate.

## Data and credentials

Environment files, credentials, captured mail/attachments, runtime records, local databases, private mounted references and temporary tokens are excluded. Keep them in their authorized stores. Credential resources are selected by reference; saving one does not establish connectivity or grant mailbox permissions.
