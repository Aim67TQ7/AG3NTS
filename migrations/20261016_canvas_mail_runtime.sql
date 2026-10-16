-- Canvas-owned mail execution. Existing imported artifacts remain historical evidence.
create table flux_private.mail_pipelines(source_id text primary key references flux_private.mail_sources(id),client_id text not null,company_code text not null,workflow_id text not null,definition jsonb not null,definition_hash text not null,tested_hash text,tests jsonb,created_by uuid not null,created_at timestamptz not null default now());
create table flux_private.mail_dispatches(source_id text not null,definition_hash text not null,stage text not null,parent_id text not null,finished_at timestamptz not null default now(),primary key(source_id,definition_hash,stage,parent_id));
alter table flux_private.mail_pipelines enable row level security;
alter table flux_private.mail_dispatches enable row level security;
revoke all on flux_private.mail_pipelines,flux_private.mail_dispatches from public,anon,authenticated;
create function flux_private.mail_plan_gate(p flux_private.mail_pipelines) returns boolean language plpgsql stable security definer set search_path='' as $$
declare step jsonb;canvas jsonb;
begin
 if p.tested_hash is distinct from p.definition_hash or not exists(select 1 from public.flux_memberships where client_id=p.client_id and user_id=p.created_by and role='owner') then return false;end if;
 select body into canvas from public.flux_app_objects where client_id=p.client_id and path like 'workflows/%' and body->>'id'=p.workflow_id order by created_at desc limit 1;
 if canvas is null then return false;end if;
 for step in select value from jsonb_array_elements(p.definition->'steps') loop
  if not exists(select 1 from flux_private.agent_controls c where c.client_id=p.client_id and c.agent_id=step->>'agent_id' and c.enabled and c.guided_hash=step->>'guided_hash') or not exists(select 1 from jsonb_array_elements(canvas->'nodes')n where n->'data'->'guided'=step->'guided') then return false;end if;
 end loop;
 return true;
end $$;
create function public.flux_mail_pipeline(action text,args jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
declare who uuid:=flux_private.current_flux_user();s flux_private.mail_sources;p flux_private.mail_pipelines;item jsonb;result jsonb;
begin
 if who is null or not exists(select 1 from public.flux_memberships where user_id=who and client_id=args->>'client_id') then raise exception 'Client access denied';end if;
 select * into s from flux_private.mail_sources where client_id=args->>'client_id';
 if s.id is null then return jsonb_build_object('configured',false);end if;
 select * into p from flux_private.mail_pipelines where source_id=s.id;
 if action='status' then
  if p.source_id is null then return jsonb_build_object('configured',false);end if;
  return jsonb_build_object('configured',true,'workflow_id',p.workflow_id,'definition',p.definition,'definition_hash',p.definition_hash,'tested',p.tested_hash=p.definition_hash,'tests',p.tests,'active',flux_private.mail_plan_gate(p),'worker_ready',s.last_seen>now()-interval '90 seconds','last_seen',s.last_seen,'environment','PRODUCTION_READ_ONLY');
 end if;
 if not exists(select 1 from public.flux_memberships where user_id=who and client_id=s.client_id and role='owner') then raise exception 'Admin permission required';end if;
 if action='install' then
  if p.source_id is not null then raise exception 'Canvas mail runtime is already installed';end if;
  if jsonb_array_length(args->'definition'->'steps')<>3 or args->'definition'->>'mailbox'<>all(s.mailboxes) or args->'definition'->'steps'->0->>'adapter'<>'maggie_capture' or args->'definition'->'steps'->1->>'adapter'<>'document_parse_local' or args->'definition'->'steps'->2->>'adapter'<>'document_json_v1' then raise exception 'Unsupported mail runtime definition';end if;
  if not flux_private.company_allowed(s.client_id,args->>'company_code',who) then raise exception 'Company access denied';end if;
  for item in select value from jsonb_array_elements(args->'objects') loop
   insert into public.flux_app_objects(client_id,path,body) values(s.client_id,item->>'path',item->'body');
  end loop;
  insert into flux_private.mail_pipelines(source_id,client_id,company_code,workflow_id,definition,definition_hash,created_by) values(s.id,s.client_id,args->>'company_code',args->'definition'->>'workflow_id',args->'definition',args->>'definition_hash',who);
  for item in select value from jsonb_array_elements(args->'definition'->'steps') loop
   select public.flux_agent_controls(s.client_id,'set',item->>'agent_id',false,item->>'guided_hash',coalesce((select revision from flux_private.agent_controls where client_id=s.client_id and agent_id=item->>'agent_id'),0)) into result;
  end loop;
  insert into flux_private.mail_access_events(actor,source_id,action) values(who,s.id,'canvas.installed');
  return jsonb_build_object('installed',true);
 elsif action='start' then
  if p.source_id is null or p.tested_hash is distinct from p.definition_hash then raise exception 'Execution package tests must pass first';end if;
  for item in select value from jsonb_array_elements(p.definition->'steps') loop
   perform public.flux_agent_controls(s.client_id,'set',item->>'agent_id',true,item->>'guided_hash',coalesce((select revision from flux_private.agent_controls where client_id=s.client_id and agent_id=item->>'agent_id'),0));
  end loop;
  if not flux_private.mail_plan_gate(p) then raise exception 'Canvas has changed; runtime remains off';end if;
  insert into flux_private.mail_access_events(actor,source_id,action) values(who,s.id,'canvas.started');
  return jsonb_build_object('active',true);
 elsif action='power' then
  if p.source_id is null or p.tested_hash is distinct from p.definition_hash then raise exception 'This exact canvas adapter package has not passed its execution tests';end if;
  if not exists(select 1 from jsonb_array_elements(p.definition->'steps')x where x->>'agent_id'=args->>'agent_id' and x->>'guided_hash'=args->>'guided_hash') then raise exception 'Agent definition does not match the runtime package';end if;
  result:=public.flux_agent_controls(s.client_id,'set',args->>'agent_id',(args->>'enabled')::boolean,args->>'guided_hash',(args->>'expected_revision')::integer);
  insert into flux_private.mail_access_events(actor,source_id,action,artifact_id) values(who,s.id,case when (args->>'enabled')::boolean then 'canvas.agent.enabled' else 'canvas.agent.disabled' end,args->>'agent_id');
  return result;
 else raise exception 'Unknown canvas mail action';end if;
end $$;
create function public.flux_mail_canvas_worker(action text,payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
declare s flux_private.mail_sources;p flux_private.mail_pipelines;b jsonb;step jsonb;parent jsonb;old jsonb;result jsonb;previous_stage text;
begin
 select * into s from flux_private.mail_sources where enabled and token_hash=encode(pg_catalog.sha256(pg_catalog.convert_to(coalesce(coalesce(current_setting('request.headers',true),'{}')::jsonb->>'x-flux-mail',''),'UTF8')),'hex');
 if s.id is null then raise exception 'Mail source access denied';end if;
 select * into p from flux_private.mail_pipelines where source_id=s.id;
 if action='heartbeat' then
  update flux_private.mail_sources set last_seen=clock_timestamp(),health=payload where id=s.id;return jsonb_build_object('ok',true);
 end if;
 if action='plan' then return jsonb_build_object('configured',p.source_id is not null,'definition',p.definition,'definition_hash',p.definition_hash,'tested',p.tested_hash=p.definition_hash,'active',case when p.source_id is not null then flux_private.mail_plan_gate(p) else false end);end if;
 if p.source_id is null then raise exception 'Canvas pipeline unavailable';end if;
 if action='tested' then
  if payload->>'definition_hash' is distinct from p.definition_hash or payload->'passed' is distinct from 'true'::jsonb then raise exception 'Execution tests did not pass';end if;
  update flux_private.mail_pipelines set tested_hash=definition_hash,tests=payload where source_id=s.id;return jsonb_build_object('tested',true);
 end if;
 if not flux_private.mail_plan_gate(p) then raise exception 'Canvas agents are off, held, or changed';end if;
 if action='parents' then
  previous_stage:=case payload->>'stage' when 'parse' then 'capture' when 'json' then 'parse' else null end;
  if previous_stage is null then raise exception 'Unsupported stage';end if;
  select coalesce(jsonb_agg(x.body),'[]') into result from (
   select a.id,a.body from flux_private.mail_artifacts a where a.source_id=s.id and a.stage=previous_stage and a.body->>'definition_hash'=p.definition_hash and a.body->>'origin'='canvas_runtime'
    and not exists(select 1 from flux_private.mail_dispatches d where d.source_id=s.id and d.definition_hash=p.definition_hash and d.stage=payload->>'stage' and d.parent_id=a.id) order by a.occurred_at,a.id limit 10
  )x;return result;
 elsif action='done' then
  if payload->>'stage' not in ('parse','json') or not exists(select 1 from flux_private.mail_artifacts a where a.source_id=s.id and a.id=payload->>'parent_id' and a.body->>'definition_hash'=p.definition_hash) then raise exception 'Invalid dispatch parent';end if;
  insert into flux_private.mail_dispatches values(s.id,p.definition_hash,payload->>'stage',payload->>'parent_id',now()) on conflict do nothing;return jsonb_build_object('done',true);
 elsif action='commit' then
  b:=payload->'artifact';
  select value into step from jsonb_array_elements(p.definition->'steps') where value->>'stage'=b->>'stage';
  if step is null or b->>'id' is null or b->>'id' !~ '^[a-f0-9]{64}$' or b->>'definition_hash' is distinct from p.definition_hash or b->>'agent_id' is distinct from step->>'agent_id' or b->>'agent_hash' is distinct from step->>'guided_hash' or b->>'mailbox' is distinct from p.definition->>'mailbox' or b->>'origin' is distinct from 'canvas_runtime' or coalesce(b->>'status','') not in ('completed','review_required','failed','unsupported','empty') then raise exception 'Artifact does not bind the enabled canvas agent';end if;
  if b->>'stage'<>'capture' then
   select body into parent from flux_private.mail_artifacts where source_id=s.id and id=b->>'input_artifact_id';
   if parent is null or parent->>'definition_hash' is distinct from p.definition_hash or parent->>'stage'<>(case b->>'stage' when 'parse' then 'capture' else 'parse' end) or parent->>'message_id' is distinct from b->>'message_id' then raise exception 'Missing durable canvas input';end if;
  end if;
  select body into old from flux_private.mail_artifacts where source_id=s.id and id=b->>'id';
  if old is not null then if old is distinct from b then raise exception 'Immutable canvas run conflict';end if;return jsonb_build_object('saved',false);end if;
  insert into flux_private.mail_artifacts(source_id,id,stage,message_id,attachment_id,mailbox,occurred_at,status,body,content_hash) values(s.id,b->>'id',b->>'stage',b->>'message_id',coalesce(b->>'attachment_id',''),b->>'mailbox',(b->>'occurred_at')::timestamptz,b->>'status',b,encode(pg_catalog.sha256(pg_catalog.convert_to(b::text,'UTF8')),'hex'));
  return jsonb_build_object('saved',true);
 else raise exception 'Unknown canvas worker operation';end if;
end $$;
revoke all on function flux_private.mail_plan_gate(flux_private.mail_pipelines),public.flux_mail_pipeline(text,jsonb),public.flux_mail_canvas_worker(text,jsonb) from public;
grant execute on function public.flux_mail_pipeline(text,jsonb),public.flux_mail_canvas_worker(text,jsonb) to anon,authenticated;
