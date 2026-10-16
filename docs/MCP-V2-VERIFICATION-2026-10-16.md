# MCP v2 verification, October 16, 2026

Application: `https://flux.by-pete.com`. Database: the existing FLUX ZODA project. Operational PZLO was not changed.

## Results

| Check | Result | Evidence scope |
| --- | --- | --- |
| Python unit suite | 193 passed | Validation, governance, draft semantics, sandbox and existing runtime regressions |
| Local PostgreSQL integration suite | 34 passed | Real PGlite transactions with synthetic identity/ACL contracts |
| Frontend | TypeScript and Vite build passed | Existing chunk-size warning remains |
| Release build | Unit suite passed in Docker | Deployment helper rebuilt and restarted the service |
| HTTPS readiness and MCP | Passed | `/readyz`, initialized MCP reports version 2.0.0 |
| Atomic review | Passed over authenticated HTTPS | Keyed schema/instruction/workflow proposal, idempotent replay, one browser Apply and contract approval |
| Deterministic fixtures | Passed over HTTPS | Synthetic MAP fixture, zero cost, no external adapters |
| Runtime observation | Passed over HTTPS | Stored synthetic TEST job read, unknown run denied, content bytes removed |
| Protected model choice | Passed over HTTPS | Stored as proposed; fixture transfer rejected until browser confirmation |
| Secret request and browser vault | Passed over HTTPS | Metadata proposal plus encrypted dummy credential storage and separate TEST design approval; no authentication attempted |
| Seven-agent build | Passed locally | One change set, one Apply, seven fixture results, two mocked model calls and explicit synthetic external results |
| Record reads | Passed locally | Exact record type/package linkage, current ACLs, file ID retained, bytes and signed location removed |
| PRODUCTION business workflow acceptance | Not established | No live mailbox, Epicor or Teams action or live model response tested |

The HTTPS checks used a disposable tenant and account. The synthetic runtime workflow remained paused. Test access, mutable fixtures and accounts were removed after verification; immutable request/history and access audit remain. Existing user proposals were not applied. No real business record was created, sent or changed. The only credential entered was a deliberately nonworking synthetic test value, removed during cleanup.

## Database release

- `20261016174624_flux_mcp_v2_observation_and_review.sql`
- `20261016175149_flux_mcp_v2_connection_environments.sql`

Both follow `20261016163110_flux_builder_catalog_locks.sql`. The functions use explicit empty search paths, resolve identity server-side, and enforce company/facility and current workflow ACLs. Private helper execution is revoked from public, anon and authenticated roles. The public observation RPC deliberately permits invocation by anon/authenticated roles because FLUX resolves its own password/OAuth session inside the function. Anonymous invocation without valid FLUX identity remains denied.

The Supabase security advisor flags that deliberate SECURITY DEFINER RPC exposure. See the [anonymous function guidance](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable) and [authenticated function guidance](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable). Other project-wide findings include disabled RLS on unrelated tables, security-definer views, mutable search paths, auth settings and an available PostgreSQL security update. This release does not claim the shared project has a clean security audit. Relevant remediation guidance covers [RLS](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public), [views](https://supabase.com/docs/guides/database/database-linter?lint=0010_security_definer_view), [search paths](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable), [password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection) and [database updates](https://supabase.com/docs/guides/platform/upgrading).

A restricted server-side application archive and the prior builder function definition were saved before migration/release. Rollback requires restoring the prior app and builder RPC together; retain immutable audit and synthetic-test history. The extra environment column is additive and need not be dropped to restore the earlier app.

## Remaining limits

- The full requested PO workflow cannot honestly have zero blockers until an owner supplies missing choices, exact variance policy and approved working connections. The brief has seven agents and needs a Teams connection in addition to mailbox and ERP read access.
- Only configured Sonnet model fixtures are supported. Live model billing, provider refusal and timeout behavior were not exercised against a real provider in this release. Unknown usage fails closed and holds the reservation. Successful reservations remain as historical records alongside the final receipt.
- External fixture responses are explicit synthetic stubs. A passing suite does not certify a parser, mailbox, ERP, Teams or write adapter. Existing package publication and certification gates remain.
- Rich comparisons run in the sandbox/fixture evaluator. The package interpreter still supports its existing certified rule subset.
- Runtime reads cover scoped TEST jobs and artifacts tied to the exact current mail package. `read_record` covers declared mail output records. Unassigned historical imports and older package results without current linkage are excluded.
- Secret entry encrypts values and approves design access. It does not verify authentication or activate access. A failure between vault save and connection approval needs owner reconciliation through Resources.
- Template parameter slots cover company, department and source-system fields. Mailbox-value slots and template instantiation are unfinished.
- Builder session documents have a 2 MB limit. Summary reads reduce payloads but do not compact accumulated stored proposals.
- The earlier account-specific Bunting AI-connections HTTP 500 was not reverified as fixed. The disposable account's API and review flow passed.

See [MCP v2 usage](MCP-V2.md) for tool arguments, fixture semantics and review boundaries.
