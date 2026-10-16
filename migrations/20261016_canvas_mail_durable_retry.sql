create or replace function public.flux_mail_canvas_worker(action text,payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
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
 if action='existing' then
  select body into result from flux_private.mail_artifacts where source_id=s.id and id=payload->>'id' and body->>'definition_hash'=p.definition_hash;return result;
 end if;
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
