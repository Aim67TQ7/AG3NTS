# PETE private deployment — 2026-10-14

FLUX Studio 0.2.1 runs on PETE (srv1372645, 187.77.28.22) in `/home/pete-dev/flux-studio`, using Python 3.12 and the pinned requirements. It listens only on `127.0.0.1:8496`. The owner SSH tunnel exposes it on this Mac at http://127.0.0.1:8497/. The earlier localhost:8496 tunnel still points to the historical Bunting Studio instance; use port 8497 for this deployment.

PZLO is the only data project: `https://qzwxisdfwswsrbzvpzlo.supabase.co`. Studio definitions, canvas revisions and audit receipts persist in its private `flux-studio` Storage bucket. Existing agent history and lineage come from PZLO PostgREST tables. This deployment does not create relational Studio registry tables. Server credentials were transferred directly over SSH from the existing Bunting-managed environment with the user's explicit authorization, without local staging, client exposure or secret output. PETE's `.env` is mode 0600 within the mode 0700 application directory.

`deploy/supervise.sh` holds a process lock and launches through `deploy/launch.py`. Owner cron starts it at reboot and checks once per minute; a running process retains the lock and duplicate launches exit. Cron is active. A host reboot was not performed. No Docker or existing PETE service was changed because pete-dev lacks noninteractive privileged access.

Bunting's added `flux-studio-pete-monitor.service` maintains authenticated SSH reverse forwarding for the four health endpoints to PETE loopback only. Its separate key permits only the four specified loopback listeners and disables command execution, PTY, agent and X11 forwarding. App monitoring uses GET requests. Agent 04's repository contract is a reference snapshot on PETE; no implementation was copied or started. Existing Agents 01–04 retain their original images; Agent 04 remains shadow with dispatch disabled.

## Draft correction and evidence

The user-visible failure had an empty error and 55,865 ms duration, with interrupted provider usage. Nonstreaming HTTP waited for the entire generated response, causing an idle read timeout. Drafting now consumes provider SSE internally, buffers the final structured result before applying any fields, emits periodic received-character progress, and returns phase-specific timeout/disconnection errors. Prompts request short explanations to reduce response time. The 60-second overall drafting limit and $0.25 ceiling remain enforced. Incomplete streams do not apply suggestions; unknown final usage stays unknown. Deterministic provider 400 errors are audited without retrying the identical request. Catalog loading has a 10-second bound and its failures are audited.

This follows the provider's documented streaming event and cumulative-usage protocol: https://platform.claude.com/docs/en/build-with-claude/streaming . Current Supabase changelog was checked; its announced CBC TLS deprecation does not require API changes for this Python 3.12 client: https://supabase.com/changelog/cbc-tls-ciphers-deprecated .

- 30 unit tests passed on PETE, including complete-stream usage, interrupted-stream rejection, provider rejection handling and empty timeout recovery.
- Real single DOC draft: 13,811 ms; $0.033934; complete usage. Receipt `dd44fafb-5c6e-4355-812b-80e4b159d856`.
- Real split draft: DOC → READ → RULE; 30,206 ms; $0.058984; complete usage. Receipt `7f0ca14f-653e-47a9-a54e-1fc0e9dcaa89`.
- Browser request completed and populated a DOC guide; screenshot `pete-draft-proof.png`. All examples were synthetic design descriptions; no business agent was triggered.
- Bucket connectivity, all four agent health endpoints, their PZLO history queries, Agent 04 dispatch=false and client bundle secret exclusion verified.
- Durable deployment audit was committed and read back by matching content hash. Receipt `53212549-287a-45ba-80be-811b3c2d567f`.
- Unapproved Host request rejected with 403.

## Remaining access and runtime scope

The user authorized enabling deployment access for pete-dev. Root SSH using its existing key is denied, sudo requires a password, and Hostinger is signed out. The Hostinger sign-in tab is left open for the user. Public HTTPS and integration with PETE's existing browser authentication are pending privileged access. No public URL is claimed.

Canvas definitions remain designs. Publishing a design does not deploy an executable business agent or grant operational authority. Existing pipeline agents are monitored only. Legacy P0 deterministic execution remains bounded to supplied data.

## Operations

Reconnect the owner tunnel with `ssh -fNT -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:8497:127.0.0.1:8496 pete` if no listener already occupies local port 8497. Read PETE's `/home/pete-dev/flux-studio/server.log` for process errors; audit records live in PZLO. Do not put secrets in the client or copy `.env` into packaged source.

To stop the private app, remove only the two cron entries that invoke `/home/pete-dev/flux-studio/deploy/supervise.sh`, then terminate only its matching uvicorn process. Disable Bunting's new `flux-studio-pete-monitor.service` if monitoring is being removed. Do not alter existing agent services or delete durable FLUX records. Preserve the previous Bunting deployment for rollback until the PETE HTTPS path is verified.

## HTTPS preparation — version 0.2.2

The authenticated Hostinger root console verified srv1372645 and UID 0. Live `hub-caddy` uses `docker-proxy`, with automatic label-based routes. Both flux.by-pete.com and studio.by-pete.com currently resolve to PETE. The historical pete.by-pete.com sign-in service is not currently deployed, so it cannot serve as an authentication upstream.

Prepared target: https://flux.by-pete.com. Studio reuses the existing PETE passcode scrypt hash mounted read-only, rather than creating or changing a credential. Hashed sessions and revocations persist in PZLO's private bucket; cookies are Secure, HttpOnly and SameSite=Strict with an 8-hour expiry. Sign-in attempts are durably rate-limited before hash verification (10 attempts per 10 minutes and 50 per UTC day). Credentials and raw session tokens are excluded from audit and durable records. The public process rejects localhost/forged Host bypasses and requires exact public Origin for writes. Anonymous API/state/catalog/health access returns 401; the login page is available. `/readyz` exposes only a status for infrastructure health checks. Public sign-out is offered in the UI.

37 tests passed, including revoked/expired/forged session rejection, durable rate limiting, actual synthetic scrypt verification and cookie/audit properties. TypeScript and production build passed. ASGI checks: unauthenticated home 303, state/catalog/health 401, login 200, cross-origin login 403, forged localhost Host 403.

Prepared root-owned helper allows only FLUX Studio update/status/restart, without general Docker/sudo permission. Its compose file is root-owned and fixes the host network, read-only container, unprivileged user, bounded resources, mounts, label and command. Public Studio listens only on the internal Docker bridge host address 172.18.0.1:8498, where it can also observe the private agent monitoring tunnels. Public exposure and helper installation await the browser policy's required action-time confirmation.

## HTTPS deployed — 2026-10-14

The user confirmed both public publication and installation of the limited helper. FLUX Studio 0.2.2 is now deployed at **https://flux.by-pete.com**, as the healthy `flux-studio-public` Docker container. `pete-dev` can invoke the root-owned fixed helper for update/status/restart; a direct `sudo -n docker ps` remains denied.

The live proxy route is supplied through the Studio container's Docker labels. Caddy issued a valid certificate, verified through HTTPS requests without certificate bypass. A persistent UFW rule allows only the current Caddy source `172.18.0.3` to the internal listener `172.18.0.1:8498`; no Internet listener was opened on port 8498. If Caddy is recreated with a different address, update that exact-source rule after verifying its new identity.

Live checks: login 200, anonymous API 401, readiness 200/status ok, cross-origin sign-in 403. All 37 tests also passed inside the deployed container with its installed dependencies. Its own FLUX connection and all four existing-agent monitors passed; Agent 04 dispatch remains disabled. A deployment receipt was committed and read back: `20d2912d-556c-4ef5-90a7-cf20fbfef5f4`.

A real human public sign-in and subsequent authenticated public browser drafting session are pending; the login tab was left open for the owner. Do not claim those checks from readiness or private-instance tests. Existing passcode was neither retrieved in cleartext nor changed.

The first Compose launch was rejected before starting the service because an inline tmpfs list split at a comma; quoting the declaration corrected it. The first proxy requests returned 502 because the existing host firewall blocked the internal upstream; the narrowly scoped persistent UFW rule corrected it.

After Caddy regenerated its configuration, semantic comparison confirmed all three original host routes and their handlers/upstreams remained unchanged, with only the fourth Studio route added. Generated route-group labels were normalized for this comparison because adding a host renumbered those labels. No existing service route was replaced.

## Authenticated public browser verified

The owner successfully signed in at https://flux.by-pete.com with the existing PETE passcode. The authenticated browser rendered all four agent monitors (Agents 01–03 ok; Agent 04 healthy, dispatch OFF/shadow). A separate synthetic verification canvas was created without modifying the existing PO acknowledgment canvas.

A real public-browser DOC draft completed and populated the guide in 11,938 ms, costing $0.032382, with complete provider usage. Its durable FLUX audit receipt is `86e4218b-78ab-402d-a129-0f69cec1c5ee`, actor `PETE owner`. Receipt status was read back as completed. Screenshot: `pete-authenticated-draft-proof.png`. Missing company, department, environment, owner and business contracts remain explicit user decisions. This was design-only and triggered no operational agent, business write or communication.

This supersedes the earlier pending public sign-in/drafting limitation. The passcode is not written into source, reports, memory or audit. The signed-in app is left open for the owner.
