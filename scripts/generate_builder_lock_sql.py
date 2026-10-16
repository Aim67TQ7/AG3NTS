"""Generate the database lock predicate from the same catalog used by the builder."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def migration_sql():
 cat=json.loads((ROOT/'catalog/agent-options.json').read_text());policy=json.dumps({k:cat[k] for k in ('locked','conditional_locked')},separators=(',',':'))
 return '''-- Generated from catalog/agent-options.json; do not maintain a separate lock table.
create or replace function flux_private.builder_decision_locked(field_name text, capability text, field_value text)
returns boolean language sql immutable set search_path='' as $policy$
 select (p->'locked' ? field_name) or exists (
  select 1 from jsonb_array_elements(p->'conditional_locked') r
  where r->>'field'=field_name
   and (not (r ? 'capabilities') or r->'capabilities' ? capability)
   and (not (r ? 'unless_value') or field_value is distinct from r->>'unless_value')
 ) from (select $catalog$'''+policy+'''$catalog$::jsonb p) policy;
$policy$;
revoke all on function flux_private.builder_decision_locked(text,text,text) from public,anon,authenticated;
-- Preserve all current isolation, revision, audit and atomic-apply logic.
do $patch$
declare definition text; old_loop text := $old$for field_name in select unnest(array['execute.authority','verify.approval_gate','execute.model_access']) loop$old$;
 old_guard text := $old$if v is not null and not (field_name='execute.model_access' and v='off') and$old$;
begin
 definition:=pg_get_functiondef('public.flux_builder_session(text,jsonb)'::regprocedure);
 if position(old_loop in definition)=0 or position(old_guard in definition)=0 then raise exception 'Builder lock source changed; inspect before applying'; end if;
 definition:=replace(definition,old_loop,$new$for field_name in select jsonb_object_keys(r->'body'->'fields') except select unnest(array['identity.owner','identity.environment']) loop$new$);
 definition:=replace(definition,old_guard,$new$if v is not null and flux_private.builder_decision_locked(field_name,r->'body'->>'capability',v) and$new$);
 execute definition;
end $patch$;
'''
if __name__=='__main__':print(migration_sql(),end='')
