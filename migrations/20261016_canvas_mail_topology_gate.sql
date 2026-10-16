create or replace function flux_private.mail_plan_gate(p flux_private.mail_pipelines) returns boolean language plpgsql stable security definer set search_path='' as $$
declare step jsonb;canvas jsonb;first_id text;next_id text;i integer;
begin
 if p.tested_hash is distinct from p.definition_hash or not exists(select 1 from public.flux_memberships where client_id=p.client_id and user_id=p.created_by and role='owner') then return false;end if;
 select body into canvas from public.flux_app_objects where client_id=p.client_id and path like 'workflows/%' and body->>'id'=p.workflow_id order by created_at desc limit 1;
 if canvas is null or jsonb_array_length(canvas->'nodes')<>3 or jsonb_array_length(canvas->'edges')<>2 or not flux_private.company_allowed(p.client_id,p.company_code,p.created_by) then return false;end if;
 for step in select value from jsonb_array_elements(p.definition->'steps') loop
  if not exists(select 1 from flux_private.agent_controls c where c.client_id=p.client_id and c.agent_id=step->>'agent_id' and c.enabled and c.guided_hash=step->>'guided_hash') or not exists(select 1 from jsonb_array_elements(canvas->'nodes')n where n->'data'->'guided'=step->'guided') then return false;end if;
 end loop;
 for i in 0..1 loop
  select n->>'id' into first_id from jsonb_array_elements(canvas->'nodes')n where n->'data'->'guided'->>'id'=p.definition->'steps'->i->>'agent_id';
  select n->>'id' into next_id from jsonb_array_elements(canvas->'nodes')n where n->'data'->'guided'->>'id'=p.definition->'steps'->(i+1)->>'agent_id';
  if not exists(select 1 from jsonb_array_elements(canvas->'edges')e where e->>'source'=first_id and e->>'target'=next_id and e->>'sourceHandle'='COMPLETED' and e->'data'->>'runtime_handoff'='true') then return false;end if;
 end loop;
 return true;
end $$;
