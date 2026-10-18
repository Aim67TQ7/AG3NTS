# AG3NTS — OφERIS Studio

OφERIS Studio builds and operates agents with explicit responsibilities, durable record handoffs, versioned contracts, audit evidence and human review. This repository contains the full current application source captured from the PETE server on October 16, 2026, including the deployed MCP v2 proposal and runtime-observation changes.

[Live application](https://flux.by-pete.com) · [MCP endpoint](https://flux.by-pete.com/mcp) · [MCP v2 guide](docs/MCP-V2.md) · [Governance](docs/WORKFLOW-GOVERNANCE.md)

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

## MCP v2 release and verification

[Release evidence and limitations](docs/MCP-V2-VERIFICATION-2026-10-16.md)

MCP v2 adds keyed atomic change sets, proposed human-owned choices, proposal inspection, current-draft validation, instruction resources, richer sandbox rules, fixtures, secure browser secret requests, recoverable archival and scoped runtime reads. Identical schema hashes pass edge compatibility, and record-type collisions have separate findings. Drafts remain TEST and Off.

Verification passed 193 unit tests, 34 local PostgreSQL integration tests, the frontend build and authenticated HTTPS checks. The seven-agent regression uses synthetic external results and mocked model responses. Live checks covered atomic browser Apply, deterministic fixtures, stored synthetic runtime result reads and redaction. No business action or provider call was made by the acceptance checks.

Model fixture execution supports configured Sonnet only and needs explicit human confirmation, server enablement, verified prices and a call budget. Rich rule approval does not certify the existing runtime interpreter. Mailbox, ERP, Teams and write adapters still need real connectivity and package certification. Runtime record reads cover declared mail output records; unassigned historical imports are excluded. Templates currently support catalog-field slots, not mailbox-value slots or instantiation. Existing long-lived builder sessions can reach the 2 MB document limit.

ZODA migrations `20261016174624_flux_mcp_v2_observation_and_review.sql` and `20261016175149_flux_mcp_v2_connection_environments.sql` follow the earlier catalog-lock migration. Review migration history before applying elsewhere. The existing Bunting AI-connections HTTP 500 was observed before v2; the synthetic endpoint passed v2 checks, but that account-specific failure has not been reverified as fixed.

## Data and credentials

Environment files, credentials, captured mail/attachments, runtime records, local databases, private mounted references and temporary tokens are excluded. Keep them in their authorized stores. Credential resources are selected by reference; saving one does not establish connectivity or grant mailbox permissions.

### Agent capability library

The Agent Library uses compact cards: catalog-colored capability badge, agent name, Input → Execute → Output symbols and runtime state. Resources, descriptions and configuration summaries belong in the editor. Secondary actions are behind the actions menu. The same AgentIdentity component labels agents in the dashboard, canvas, monitor, execution history and review queue. Search, saved templates, opening agents, and saving templates remain available. Runtime switches retain their existing server-backed status and permissions; the library does not infer execution counts, success rates, or costs from configuration. Header counts reflect saved agents, capability types, and saved templates.

VPS credential imports use an owner-bound, expiring encrypted staging bundle. Only the named Bunting administrator can review and consume it through Resources. The import calls the normal client vault save path, retains source provenance, verifies encrypted read-back, and records an audit event. Imported credentials are restricted to admins; BMC/MAI entries use their company scope, while connections without a configured company remain private. Imported connections are unverified and do not create agent selections, execution grants, provider requests, or workflow activation. The staging key and bundle are removed after import.

Saved agents support recoverable Archive/Restore controls in the Agent Library. Archives hide all versions from active pickers and block new workflow compilation using those agents; Show archived exposes restoration. Installed mail-runtime agents and agents in active TEST workflows are protected. Definitions and audit history are retained.

### Portable workflow JSON

Workflows → Workflow JSON supports versioned definition export, file loading, editing, validation, download, and import as a new TEST draft. Packages include six-function settings, JSON contracts, durable-record handoffs and portable resource slots. Credential values, selections and runtime authority are excluded. See [the workflow JSON guide](docs/workflow-json.md) and [JSON Schema](docs/workflow-package.schema.json). Import requires resource mapping, review and testing before separate activation.

Agent Library → Templates → **Email to JSON** starts a new workflow with one mailbox address. The template includes retrieval, attachment parsing, JSON conversion, schemas, six-function settings and two handoffs. Each use creates an independent TEST draft with fresh IDs and no credential selections or installed runtime bindings. Mailbox permission and runtime access must be checked before separately enabling it; changing an address does not extend provider permissions.

Email Retriever is a single-agent template under Agent templates: enter one mailbox address to save one TEST draft that captures email and attachment references. Draft creation grants no mailbox access, selects no credentials and does not activate execution. Attachment parsing and JSON conversion belong to separate agents. The three-agent Email to JSON template is available separately under Workflow templates.

### Operis proxy firewall recovery

The public app binds to `172.18.0.1:8498`; only the `hub-caddy` proxy may reach that port. A stale UFW source address caused a public 502 after the October 17 host restart: Caddy was at `172.18.0.11` while its allow rule still named `172.18.0.3`. Direct app health passed because the blocked path was container-to-host.

The root-installed `deploy/operis-proxy-firewall-sync.py` checks the running `hub-caddy` identity and `hub-net` private address, aligns only the tagged Operis/FLUX Caddy-only rule, verifies `/readyz` from inside Caddy, then removes obsolete tagged source rules. It does not open the port publicly, change Caddy routes, or activate workflows. `deploy/operis-proxy-firewall-sync.service` and `.timer` run this at boot and every minute so proxy recreation cannot leave a permanently stale address. Install the script as root-owned `/usr/local/sbin/operis-proxy-firewall-sync` and the unit files under `/etc/systemd/system`, then enable/start the timer and start the service. This is a host operation, not part of the Studio container build.

Validation: `python -m unittest discover -s deploy -p test_proxy_firewall.py -q`; check `systemctl show operis-proxy-firewall-sync.service -p Result -p ExecMainStatus`, timer status, public `/readyz`, and a rendered authenticated page. Root-only recovery backups are under `/root/operis-recovery-20261017`. Disable the timer to stop reconciliation; the current narrow working allow rule remains in place. A full host reboot was not performed during recovery.
