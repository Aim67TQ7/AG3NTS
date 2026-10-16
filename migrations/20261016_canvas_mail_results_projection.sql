create or replace function public.flux_mail_results(action text,args jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
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
   select id,stage,message_id,attachment_id,mailbox,occurred_at,status,committed_at,body->>'agent_id' as agent_id,body->>'origin' as origin,body->>'filename' as filename,body->>'agent_name' as agent_name,body->>'input_artifact_id' as input_artifact_id,body->'metrics' as metrics,body->>'subject' as subject
   from flux_private.mail_artifacts where source_id=s.id and (coalesce(args->>'origin','')='' or body->>'origin'=args->>'origin') and (coalesce(args->>'agent_id','')='' or body->>'agent_id'=args->>'agent_id') and (coalesce(args->>'stage','')='' or stage=args->>'stage') and (coalesce(args->>'message_id','')='' or message_id=args->>'message_id') and (coalesce(args->>'attachment_only','false')<>'true' or attachment_id not in ('','body')) and (coalesce(args->>'before','')='' or (occurred_at,id)<((args->>'before_time')::timestamptz,args->>'before')) order by occurred_at desc,id desc limit 51
  )x;
  select coalesce(jsonb_object_agg(stage,n),'{}') into counts from (select stage,count(*) as n from flux_private.mail_artifacts where source_id=s.id and (coalesce(args->>'origin','')='' or body->>'origin'=args->>'origin') and (coalesce(args->>'agent_id','')='' or body->>'agent_id'=args->>'agent_id') group by stage)x;
  return jsonb_build_object('configured',true,'source_id',s.id,'client_id',s.client_id,'company_assignment','unassigned','enabled',s.enabled,'last_seen',s.last_seen,'bridge_ready',s.enabled and s.last_seen>now()-interval '90 seconds','health',s.health,'counts',counts,'items',result);
 else raise exception 'Unknown results action';end if;
end $$;
