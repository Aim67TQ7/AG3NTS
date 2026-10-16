-- Scoped, read-only business observation. All authority is resolved server-side.
create or replace function flux_private.builder_result_json(value jsonb) returns jsonb
language plpgsql immutable set search_path='' as $$
declare result jsonb; item record;
begin
 if jsonb_typeof(value)='object' then
  result:='{}';
  for item in select * from jsonb_each(value) loop
   if lower(item.key) in ('contentbytes','bytes','raw_mime','mime','client_secret','access_token','refresh_token','password','api_key','encrypted_value','authorization','signed_url','download_url','file_path','source_path','signedurl','secret','token','password_hash','private_key','connection_string','content_bytes','rawmime','base64','storage_path','body_bytes','attachment_bytes') then continue;end if;
   result:=result||jsonb_build_object(item.key,flux_private.builder_result_json(item.value));
  end loop;return result;
 elsif jsonb_typeof(value)='array' then return coalesce((select jsonb_agg(flux_private.builder_result_json(v)) from jsonb_array_elements(value)v),'[]');
 elsif jsonb_typeof(value)='string' and value::text ~* '(sk-ant-|sk-proj-|sb_secret_|Bearer[[:space:]]+|https?://[^/ ]+:[^/ ]+@|data:[^;]+;base64,|https?://[^ ]+[?&](token|sig|signature|key|x-amz-)[^ ]*=)' then return '"[redacted]"';
 end if;return value;
end $$;
revoke all on function flux_private.builder_result_json(jsonb) from public,anon,authenticated;
create or replace function flux_private.builder_workflow_allowed(tenant text,company text,facility text,workflow text,actor uuid) returns boolean language sql stable set search_path='' as $$
 select coalesce((select body->>'company'=company and body->>'facility'=facility and flux_private.object_allowed(tenant,path,body,'view',actor,company) from public.flux_app_objects where client_id=tenant and path like 'workflows/%' and body->>'id'=workflow order by created_at desc,path desc limit 1),false)
$$;
revoke all on function flux_private.builder_workflow_allowed(text,text,text,text,uuid) from public,anon,authenticated;
create or replace function public.flux_builder_observe(action text,args jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare ctx jsonb;uid uuid;t text;co uuid;code text;facility text;role_name text;wf text;result jsonb;item jsonb;cursor_time timestamptz;cursor_id text;
begin
 if args ? 'access_token' then ctx:=public.flux_mcp('resolve',args);uid:=(ctx->'user'->>'id')::uuid;t:=ctx->'client'->>'id';co:=(ctx->'company'->>'id')::uuid;role_name:=ctx->>'role';
 else uid:=flux_private.current_flux_user();t:=args->>'tenant';co:=(args->>'company')::uuid;select role into role_name from public.flux_memberships where user_id=uid and client_id=t;end if;
 select fc.code,fc.facility into code,facility from public.flux_companies fc where fc.id=co and fc.client_id=t;
 if uid is null or role_name is null or role_name not in ('owner','editor') or code is null or not flux_private.company_allowed(t,code,uid) then raise exception 'Observation scope denied';end if;
 wf:=args->>'workflow_id';
 if wf is not null and not flux_private.builder_workflow_allowed(t,code,facility,wf,uid) then raise exception 'Workflow unavailable';end if;
 if action='runtime_connections' then
  select jsonb_build_object('items',coalesce(jsonb_agg(jsonb_build_object('id','runtime:'||p.source_id,'workflow_id',p.workflow_id,'system','outlook_graph','capabilities',jsonb_build_array('mail.read'),'environment','PRODUCTION_READ_ONLY','adapter','maggie_capture','runtime_authorized',flux_private.mail_plan_gate(p),'design_connection_id',null,'binding_source','external_runtime_package','worker_last_seen',s.last_seen)),'[]'),'active',coalesce(bool_or(flux_private.mail_plan_gate(p)),false) or exists(select 1 from public.flux_runtime_workflows rw where rw.client_id=t and rw.state in ('running','active') and (wf is null or rw.id=wf) and flux_private.builder_workflow_allowed(t,code,facility,rw.id,uid))) into result from flux_private.mail_pipelines p join flux_private.mail_sources s on s.id=p.source_id where p.client_id=t and p.company_code=code and (wf is null or p.workflow_id=wf) and flux_private.builder_workflow_allowed(t,code,facility,p.workflow_id,uid);
 elsif action in ('list_runs','read_run','read_record') then
  if args->>'cursor' is not null then cursor_time:=split_part(args->>'cursor','~',1)::timestamptz;cursor_id:=split_part(args->>'cursor','~',2);end if;
  with permitted_workflows as (
   select distinct o.body->>'id' id from public.flux_app_objects o where o.client_id=t and o.path like 'workflows/%' and o.body->>'company'=code and o.body->>'facility'=facility and flux_private.builder_workflow_allowed(t,code,facility,o.body->>'id',uid)
  ), runs as (
   select 'job:'||j.id::text id,j.workflow_id,j.created_at occurred_at,j.status outcome,
    jsonb_build_object('id','job:'||j.id::text,'workflow_id',j.workflow_id,'outcome',j.status,'occurred_at',j.created_at,'finished_at',j.finished_at,'environment','TEST','definition_hash',j.definition_hash,'result',j.result,'steps',(select coalesce(jsonb_agg(jsonb_build_object('step',s.step,'created_at',s.created_at,'result',s.result) order by s.step),'[]') from public.flux_runtime_steps s where s.job_id=j.id and s.client_id=t)) body,
    null::text record_type
   from public.flux_runtime_jobs j where j.client_id=t and j.test_run=true and jsonb_typeof(j.definition->'steps')='array' and jsonb_array_length(j.definition->'steps')>0 and j.workflow_id in (select id from permitted_workflows) and not exists(select 1 from jsonb_array_elements(j.definition->'steps') n where n->'config'->'scope'->>'company' is distinct from code or n->'config'->'scope'->>'facility' is distinct from facility)
   union all
   select 'mail:'||a.id,p.workflow_id,a.occurred_at,a.status,a.body||jsonb_build_object('run_id','mail:'||a.id,'record_id',a.id,'scope_source','company-scoped runtime package','result_hash',a.content_hash),step->'guided'->'fields'->'output.record_type'->>'value'
   from flux_private.mail_artifacts a join flux_private.mail_pipelines p on p.source_id=a.source_id cross join lateral jsonb_array_elements(p.definition->'steps') step
   where p.client_id=t and p.company_code=code and p.workflow_id in(select id from permitted_workflows) and a.body->>'origin'='canvas_runtime' and a.body->>'workflow_id'=p.workflow_id and a.body->>'agent_id'=step->>'agent_id' and a.body->>'definition_hash'=p.definition_hash
  ), selected as (
   select * from runs where (wf is null or workflow_id=wf) and
    (action<>'read_run' or id=args->>'run_id') and
    (action<>'read_record' or (record_type=args->>'record_type' and id='mail:'||(args->>'id'))) and
    (args->>'since' is null or occurred_at>=(args->>'since')::timestamptz) and
    (args->>'outcome' is null or upper(outcome)=upper(args->>'outcome') or upper(args->>'outcome')='REVIEW_REQUIRED' and outcome='review_required') and
    (cursor_time is null or (occurred_at,id)<(cursor_time,cursor_id))
    order by occurred_at desc,id desc limit 51
  ) select case when action='list_runs' then jsonb_build_object('items',coalesce((select jsonb_agg(case when args->>'detail'='full' then flux_private.builder_result_json(x.body) else jsonb_build_object('id',x.id,'workflow_id',x.workflow_id,'outcome',x.outcome,'occurred_at',x.occurred_at,'metrics',x.body->'metrics','error',x.body->'error','record_type',x.record_type) end order by x.occurred_at desc,x.id desc) from (select * from selected limit 50)x),'[]'),'next_cursor',case when (select count(*) from selected)>50 then (select occurred_at::text||'~'||id from selected offset 49 limit 1) else null end) else (select flux_private.builder_result_json(body) from selected limit 1) end into result;
  if action<>'list_runs' and result is null then raise exception 'Stored result unavailable';end if;
 else raise exception 'Unknown observation action';end if;
 insert into flux_private.mcp_events(user_id,action,detail) values(uid,'runtime_observed',jsonb_build_object('tenant',t,'company',co,'operation',action,'workflow_id',wf));
 return flux_private.builder_result_json(result);
end $$;
revoke all on function public.flux_builder_observe(text,jsonb) from public;
grant execute on function public.flux_builder_observe(text,jsonb) to anon,authenticated;

-- Browser confirmation changes provenance only; values remain the reviewed proposal.
create or replace function flux_private.builder_confirm_fields(canvas jsonb) returns jsonb
language plpgsql immutable set search_path='' as $$
declare nodes jsonb:='[]';node jsonb;fields jsonb;field record;
begin
 for node in select value from jsonb_array_elements(canvas->'nodes') loop
  fields:=node->'data'->'guided'->'fields';
  for field in select * from jsonb_each(fields) loop
   if field.value->>'source'='proposed' then fields:=jsonb_set(fields,array[field.key,'source'],'"user"');end if;
  end loop;
  node:=jsonb_set(node,'{data,guided,fields}',fields);node:=jsonb_set(node,'{data}',(node->'data')-'guided_hash');nodes:=nodes||jsonb_build_array(node);
 end loop;
 return jsonb_set(canvas,'{nodes}',nodes);
end $$;
revoke all on function flux_private.builder_confirm_fields(jsonb) from public,anon,authenticated;

do $patch$
declare d text;
begin
 d:=pg_get_functiondef('public.flux_builder_session(text,jsonb)'::regprocedure);
 if position('flux_private.builder_decision_locked' in d)=0 then raise exception 'Catalog lock migration required';end if;
 d:=replace(d,'if v is not null and flux_private.builder_decision_locked(field_name,r->''body''->>''capability'',v) and',
 'if v is not null and flux_private.builder_decision_locked(field_name,r->''body''->>''capability'',v) and r->''body''->''fields''->field_name->>''source'' is distinct from ''proposed'' and');
 d:=replace(d,'native->>''kind'' not in (''schema'',''rules'')','native->>''kind'' not in (''schema'',''rules'',''instructions'',''asset'',''template'')');
 d:=replace(d,$old$elsif k='workflows' then
    native:=r->'body';$old$,$new$elsif k='workflows' then
    native:=case when args->>'confirm_proposed'='true' then flux_private.builder_confirm_fields(r->'body') else r->'body' end;$new$);
 d:=replace(d,$old$native:=existing;
    path_name:='workflows/'$old$,$new$native:=existing;
    if args->>'confirm_proposed'='true' then r:=r||jsonb_build_object('body',native,'content_hash',native->>'content_hash');end if;
    path_name:='workflows/'$new$);
 d:=replace(d,$old$'native_body',args->'native_bodies'->(item->>'id'))$old$,$new$'native_body',args->'native_bodies'->(item->>'id'),'confirm_proposed',args->'confirm_proposed','approve_resources',args->'approve_resources','confirmed_agent_hashes',args->'confirmed_agent_hashes','resource_hashes',args->'resource_hashes')$new$);
 d:=replace(d,$old$result:=result||jsonb_build_object('resource_id',r->>'resource_ref','status','draft','approval_required',true);$old$,$new$
    result:=result||jsonb_build_object('resource_id',r->>'resource_ref','status','draft','approval_required',true);
    if args->>'approve_resources'='true' and native->>'kind' in ('schema','rules','instructions') then
     if role_name<>'owner' then raise exception 'Owner resource approval required';end if;
     canonical:=tenant_id||'.'||(native->>'id');
     existing:=jsonb_build_object('id',canonical,'version',native->>'version','kind',native->>'kind','label',native->>'label','tenant',tenant_id,'company',company_code,'content',native->'content','content_hash',args->'resource_hashes'->>(r->>'id'),'library_ref',native-'content');
     if existing->>'content_hash' is null then raise exception 'Reviewed resource hash required';end if;
     if exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path='resources/'||canonical||'--'||(native->>'version')||'.json' and o.body->'content' is distinct from native->'content') then raise exception 'Resource version conflict';end if;
     insert into public.flux_app_objects(client_id,path,body) values(tenant_id,'resources/'||canonical||'--'||(native->>'version')||'.json',existing) on conflict do nothing;
     insert into public.flux_app_objects(client_id,path,body) values(tenant_id,'audit/resource-published-'||gen_random_uuid()::text||'.json',jsonb_build_object('record_id',gen_random_uuid(),'action','resource.published','actor',uid,'tenant',tenant_id,'company',company_code,'created_at',now(),'payload',jsonb_build_object('resource_ref',r->>'resource_ref','definition_hash',existing->>'content_hash','decision','browser-owner-approved-change-set')));
     result:=result||jsonb_build_object('status','approved','approval_required',false);
    end if;$new$);
 d:=replace(d,$old$canonical:=node->'data'->'guided'->>'id';
    next_doc:=$old$,$new$canonical:=node->'data'->'guided'->>'id';
    if args->>'confirm_proposed'='true' then
     next_doc:=jsonb_set(next_doc,array['agents',canonical,'body'],node->'data'->'guided');
     next_doc:=jsonb_set(next_doc,array['agents',canonical,'content_hash'],args->'confirmed_agent_hashes'->canonical);
    end if;
    next_doc:=$new$);
 execute d;
end $patch$;
-- Expose only this actor's non-secret request completion metadata and permit declared design scopes.
do $$ declare d text; begin
 d:=pg_get_functiondef('public.flux_builder_session(text,jsonb)'::regprocedure);
 d:=replace(d,$old$'outlook_graph','epicor_rest','sharepoint','supabase','custom'$old$,$new$'outlook_graph','epicor_rest','epicor_baq','sharepoint','supabase','custom','teams','smtp','webhook'$new$);
 d:=replace(d,$old$'records.read','records.write'$old$,$new$'records.read','records.write','teams.send'$new$);
 d:=replace(d,$old$'legacy',coalesce($old$,$new$'secret_fulfillments',coalesce((select jsonb_agg(o.body) from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'secret-request-fulfillments/%' and o.body->>'company'=company_code and o.body->>'created_by'=uid::text),'[]'),'legacy',coalesce($new$);
 execute d;
end $$;

-- Archival is a reviewed metadata action; it never edits or takes ownership of legacy agent snapshots.
do $patch$
declare d text;
begin
 d:=pg_get_functiondef('public.flux_builder_session(text,jsonb)'::regprocedure);
 d:=replace(d,$old$path_name:='library-'||tenant_id||'/'||(native->>'id')||'--'||(native->>'version')||'.json';$old$,$new$
    if native->'content'->>'format'='flux-workflow-archive-request-v1' then
     canonical:=native->'content'->>'workflow_id';
     if not exists(select 1 from (select * from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'workflows/%' and o.body->>'id'=canonical order by o.created_at desc,o.path desc limit 1) latest where latest.body->>'content_hash'=native->'content'->>'expected_hash' and latest.body->>'company'=company_code and latest.body->>'facility'=facility_code and flux_private.object_allowed(tenant_id,latest.path,latest.body,'edit',uid,company_code)) then raise exception 'Archive source changed or edit permission removed';end if;
     if exists(select 1 from flux_private.mail_pipelines p where p.client_id=tenant_id and p.workflow_id=canonical and flux_private.mail_plan_gate(p)) or exists(select 1 from public.flux_runtime_workflows rw where rw.client_id=tenant_id and rw.id=canonical and rw.state in ('active','running')) then raise exception 'Hold active runtime before archival';end if;
     insert into public.flux_app_objects(client_id,path,body) values(tenant_id,'audit/archive-'||gen_random_uuid()::text||'.json',jsonb_build_object('action','canvas.archived','actor',uid,'tenant',tenant_id,'company',company_code,'created_at',now(),'payload',jsonb_build_object('canvas_id',canonical,'recoverable',true,'expected_hash',native->'content'->>'expected_hash')));
    end if;
    path_name:='library-'||tenant_id||'/'||(native->>'id')||'--'||(native->>'version')||'.json';$new$);
 execute d;
end $patch$;
