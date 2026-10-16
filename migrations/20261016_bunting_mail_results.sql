create table flux_private.mail_sources(id text primary key,client_id text not null references public.flux_clients(id),token_hash text not null unique,mailboxes text[] not null,enabled boolean not null default false,last_seen timestamptz,health jsonb not null default '{}');
create table flux_private.mail_artifacts(source_id text not null references flux_private.mail_sources(id),id text not null,stage text not null check(stage in ('capture','parse','json')),message_id text not null,attachment_id text not null,mailbox text not null,occurred_at timestamptz not null,status text not null,body jsonb not null,content_hash text not null,committed_at timestamptz not null default now(),primary key(source_id,id));
create index mail_artifact_page on flux_private.mail_artifacts(source_id,occurred_at desc,id desc);
create table flux_private.mail_access_events(id bigint generated always as identity primary key,actor uuid,source_id text not null,action text not null,artifact_id text,at timestamptz not null default now());
alter table flux_private.mail_sources enable row level security;
alter table flux_private.mail_artifacts enable row level security;
alter table flux_private.mail_access_events enable row level security;
revoke all on flux_private.mail_sources,flux_private.mail_artifacts,flux_private.mail_access_events from public,anon,authenticated;
create function public.flux_mail_ingest(action text,payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
declare s flux_private.mail_sources; token text; b jsonb; existing jsonb; parent jsonb; inserted integer:=0;
begin
 token:=coalesce(current_setting('request.headers',true),'{}')::jsonb->>'x-flux-mail';
 select * into s from flux_private.mail_sources where enabled and token_hash=encode(pg_catalog.sha256(pg_catalog.convert_to(coalesce(token,''),'UTF8')),'hex');
 if s.id is null then raise exception 'Mail source access denied';end if;
 if action='heartbeat' then
  if octet_length(payload::text)>16384 then raise exception 'Health too large';end if;
  update flux_private.mail_sources set last_seen=clock_timestamp(),health=payload where id=s.id;return jsonb_build_object('ok',true);
 end if;
 if action<>'commit' or jsonb_typeof(payload->'artifacts') is distinct from 'array' or jsonb_array_length(payload->'artifacts')>12 or octet_length(payload::text)>12000000 then raise exception 'Invalid artifact batch';end if;
 for b in select value from jsonb_array_elements(payload->'artifacts') loop
  if b->>'id' is null or b->>'id' !~ '^[a-f0-9]{64}$' or coalesce(b->>'stage','') not in ('capture','parse','json') or coalesce(b->>'message_id','')='' or b->>'mailbox' is null or not(b->>'mailbox'=any(s.mailboxes)) or coalesce(b->>'status','') not in ('completed','review_required','failed','unsupported','empty') or not(b ? 'output') then raise exception 'Invalid mail artifact';end if;
  if b->>'stage'<>'capture' then
   select body into parent from flux_private.mail_artifacts where source_id=s.id and id=b->>'input_artifact_id';
   if parent is null or parent->>'message_id'<>b->>'message_id' or parent->>'mailbox'<>b->>'mailbox' or parent->>'stage'<>(case when b->>'stage'='parse' then 'capture' else 'parse' end) or (b->>'stage'='json' and parent->>'attachment_id' is distinct from b->>'attachment_id') then raise exception 'Missing or incompatible input artifact';end if;
  end if;
  select body into existing from flux_private.mail_artifacts where source_id=s.id and id=b->>'id';
  if existing is not null then if existing is distinct from b then raise exception 'Immutable artifact conflict';end if;continue;end if;
  insert into flux_private.mail_artifacts(source_id,id,stage,message_id,attachment_id,mailbox,occurred_at,status,body,content_hash) values(s.id,b->>'id',b->>'stage',b->>'message_id',coalesce(b->>'attachment_id',''),b->>'mailbox',(b->>'occurred_at')::timestamptz,b->>'status',b,encode(pg_catalog.sha256(pg_catalog.convert_to(b::text,'UTF8')),'hex'));inserted:=inserted+1;
 end loop;
 return jsonb_build_object('inserted',inserted,'accepted',jsonb_array_length(payload->'artifacts'));
end $$;
create function public.flux_mail_results(action text,args jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
declare who uuid:=flux_private.current_flux_user();s flux_private.mail_sources;result jsonb;artifact jsonb;counts jsonb;
begin
 if who is null then raise exception 'Sign-in required';end if;
 select * into s from flux_private.mail_sources where client_id=args->>'client_id';
 if s.id is null then return jsonb_build_object('configured',false,'items','[]'::jsonb);end if;
 if not exists(select 1 from public.flux_memberships where user_id=who and client_id=s.client_id) then raise exception 'Client access denied';end if;
 if action='get' then
  select body into artifact from flux_private.mail_artifacts where source_id=s.id and id=args->>'id';
  if artifact is null then raise exception 'Artifact not found';end if;
  insert into flux_private.mail_access_events(actor,source_id,action,artifact_id) values(who,s.id,'read',args->>'id');return artifact;
 elsif action='list' then
  select coalesce(jsonb_agg(x order by x.occurred_at desc,x.id desc),'[]') into result from (
   select id,stage,message_id,attachment_id,mailbox,occurred_at,status,committed_at,body->>'filename' as filename,body->>'agent_name' as agent_name,body->>'input_artifact_id' as input_artifact_id,body->'metrics' as metrics,body->>'subject' as subject
   from flux_private.mail_artifacts where source_id=s.id and (coalesce(args->>'stage','')='' or stage=args->>'stage') and (coalesce(args->>'message_id','')='' or message_id=args->>'message_id') and (coalesce(args->>'attachment_only','false')<>'true' or attachment_id not in ('','body')) and (coalesce(args->>'before','')='' or (occurred_at,id)<((args->>'before_time')::timestamptz,args->>'before')) order by occurred_at desc,id desc limit 51
  )x;
  select coalesce(jsonb_object_agg(stage,n),'{}') into counts from (select stage,count(*) as n from flux_private.mail_artifacts where source_id=s.id group by stage)x;
  return jsonb_build_object('configured',true,'source_id',s.id,'client_id',s.client_id,'company_assignment','unassigned','enabled',s.enabled,'last_seen',s.last_seen,'bridge_ready',s.enabled and s.last_seen>now()-interval '90 seconds','health',s.health,'counts',counts,'items',result);
 else raise exception 'Unknown results action';end if;
end $$;
revoke all on function public.flux_mail_ingest(text,jsonb),public.flux_mail_results(text,jsonb) from public;
grant execute on function public.flux_mail_ingest(text,jsonb),public.flux_mail_results(text,jsonb) to anon,authenticated;
