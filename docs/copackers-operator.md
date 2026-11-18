# CoPackers Near Me operator in AG3NTS

The n0v8v LLC workspace (client `n0v8v-llc`, company `N0V8V`) shows **CoPackers Near Me Business Operator** in its Agent Library. Opening the card opens the independent operator's [business status](https://copackers-operator.by-pete.com/status).

The operator runs in its own Docker service on PETE. AG3NTS observes it through a fixed local status URL. The card reports whether the external runtime is reachable. Reachability is not a claim that listings are verified, revenue has been collected, or every scheduled task succeeded. The business status reports those separately.

The installation does not activate a native Studio workflow, select credentials, create approval receipts, or alter any Bunting workspace. The card is a server-installed external reference scoped by the authenticated client and company. Its read-only status endpoint returns 404 outside the n0v8v company. Unauthenticated HTTP access remains protected by the existing sign-in boundary.

## Source

- `app/copackers_operator.py`: installed definition, authenticated company scope and fixed-target status observation.
- `app/main.py`: adds the installed reference to the current Agent Library response.
- `web/src/ExternalDirectoryStatus.tsx`: read-only external runtime label and business status link.
- `web/src/AgentPower.tsx` and `AgentLibrary.tsx`: render the external observation instead of a native power switch or draft builder.
- `tests/test_copackers_operator.py`: client/company isolation, fixed target, malformed source and no native authority.

## Deployment and validation

The existing deployment remains `/home/pete-dev/flux-studio` on PETE. Build its frontend with `npm --prefix web run build`; publish with the existing `/usr/local/sbin/flux-studio-admin update` helper. Source backups for this addition are under `copackers-observation-backup-20261118` on that server. Restoring the three backed-up files and removing this module/router restores the preceding observation behavior; it does not stop the independent operator.

On November 18, 2026, all 229 existing and added unit tests passed, TypeScript/Vite compiled successfully, the Docker release became healthy, public `/readyz` returned HTTP 200, and an unauthenticated request for the new status endpoint returned HTTP 401. A signed-in browser rendering was not observed because the available browser inventory tool timed out. The deployed module was checked separately against the live operator endpoint.

The independent operator's source, data, budget settings, lead intake, payment ledger and recovery runbook belong to that service. AG3NTS does not infer money received from traffic, listing totals, tasks or inferred demand.
