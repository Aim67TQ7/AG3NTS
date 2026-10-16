-- Reviewed build-session, atomic change-set and scoped design-connection RPC.
begin;
create table flux_private.builder_connections (
 tenant text not null, company uuid not null, id uuid not null,
 credential_path text not null, system text not null, capabilities jsonb not null,
 approved_by uuid not null, approved_at timestamptz not null default now(), revoked boolean not null default false,
 primary key(tenant,company,id)
);
alter table flux_private.builder_connections enable row level security;
revoke all on flux_private.builder_connections from public,anon,authenticated;
create table flux_private.builder_sessions (
 tenant text not null, company uuid not null, user_id uuid not null,
 revision bigint not null default 0, document jsonb not null default '{}',
 primary key(tenant,company,user_id)
);
create table flux_private.builder_requests (
 tenant text not null, company uuid not null, user_id uuid not null,
 request_id uuid not null, request_hash text not null, response jsonb not null,
 created_at timestamptz not null default now(), primary key(tenant,company,user_id,request_id)
);
create table flux_private.builder_history (
 tenant text not null, company uuid not null, user_id uuid not null,
 revision bigint not null, request_id uuid, action text not null,
 document jsonb not null, changes jsonb not null, changed_fields jsonb not null,
 created_at timestamptz not null default now(), primary key(tenant,company,user_id,revision)
);
alter table flux_private.builder_sessions enable row level security;
alter table flux_private.builder_requests enable row level security;
alter table flux_private.builder_history enable row level security;
revoke all on flux_private.builder_sessions,flux_private.builder_requests,flux_private.builder_history from public,anon,authenticated;
create function flux_private.builder_immutable() returns trigger language plpgsql set search_path='' as $$
begin raise exception 'Builder audit and request records are immutable'; end $$;
create trigger builder_history_immutable before update or delete on flux_private.builder_history for each row execute function flux_private.builder_immutable();
create trigger builder_requests_immutable before update or delete on flux_private.builder_requests for each row execute function flux_private.builder_immutable();

create function public.flux_builder_session(action text,args jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare
 ctx jsonb; uid uuid; tenant_id text; company_id uuid; company_code text; facility_code text; role_name text;
 current_doc jsonb; next_doc jsonb; rev bigint; cached flux_private.builder_requests%rowtype;
 rid uuid; item jsonb; r jsonb; k text; ident text; path_name text; native jsonb; existing jsonb;
 proposal jsonb; changes jsonb; result jsonb; review_decision text; canonical text; field_name text; node jsonb; old_record jsonb; v text;
begin
 if args ? 'access_token' then
  ctx:=public.flux_mcp('resolve',jsonb_build_object('access_token',args->>'access_token'));
  uid:=(ctx->'user'->>'id')::uuid;tenant_id:=ctx->'client'->>'id';company_id:=(ctx->'company'->>'id')::uuid;role_name:=ctx->>'role';
 else
  uid:=flux_private.current_flux_user();tenant_id:=args->>'tenant';company_id:=(args->>'company')::uuid;
  select role into role_name from public.flux_memberships where user_id=uid and client_id=tenant_id;
 end if;
 select code,facility into company_code,facility_code from public.flux_companies where id=company_id and client_id=tenant_id;
 if uid is null or role_name is null or role_name not in ('owner','editor') or company_code is null or not flux_private.company_allowed(tenant_id,company_code,uid) then raise exception 'Builder scope denied'; end if;
 if length(args::text)>2000000 then raise exception 'Builder request too large'; end if;
 -- One actor/company serialization point covers concurrent first inserts, request retries and reviews.
 perform pg_advisory_xact_lock(hashtextextended(tenant_id||company_id::text||uid::text,0));
 select revision,document into rev,current_doc from flux_private.builder_sessions where tenant=tenant_id and company=company_id and user_id=uid;
 rev:=coalesce(rev,0);current_doc:='{"agents":{},"workflows":{},"resources":{},"waivers":{},"plans":{},"change_sets":{}}'::jsonb||coalesce(current_doc,'{}');
 if args->>'request_id' is not null then
  rid:=(args->>'request_id')::uuid;
  select * into cached from flux_private.builder_requests where tenant=tenant_id and company=company_id and user_id=uid and request_id=rid;
  if found then
   if cached.request_hash is distinct from args->>'request_hash' then raise exception 'BUILDER_CONFLICT request_id reused with different content'; end if;
   if action='snapshot' then return jsonb_build_object('cached',true,'response',cached.response);end if;
   return cached.response;
  end if;
  if exists(select 1 from flux_private.mcp_proposals where tenant=tenant_id and company=company_id and user_id=uid and body->>'id'=rid::text) then raise exception 'BUILDER_CONFLICT request_id belongs to a legacy proposal';end if;
 end if;
 if action='approve_connection' then
  if args ? 'access_token' or role_name<>'owner' then raise exception 'Browser company owner required';end if;
  path_name:='library-'||tenant_id||'/'||(args->>'credential_id')||'--'||(args->>'credential_version')||'.json';
  if not exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path=path_name and o.body->>'kind'='credential' and flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) then raise exception 'Credential edit permission required';end if;
  if args->>'system' not in ('outlook_graph','epicor_rest','sharepoint','supabase','custom') or jsonb_typeof(args->'capabilities') is distinct from 'array' or jsonb_array_length(args->'capabilities') not between 1 and 20 or exists(select 1 from jsonb_array_elements_text(args->'capabilities') c where c not in ('mail.read','mail.send','files.read','files.write','epicor.read','epicor.write','records.read','records.write')) then raise exception 'Choose registered capabilities';end if;
  insert into flux_private.builder_connections(tenant,company,id,credential_path,system,capabilities,approved_by) values(tenant_id,company_id,(args->>'id')::uuid,path_name,args->>'system',args->'capabilities',uid);
  insert into flux_private.mcp_events(user_id,action,detail) values(uid,'connection_design_approved',jsonb_build_object('tenant',tenant_id,'company',company_id,'tool','approve_connection','connection_id',args->>'id','capabilities',args->'capabilities','request_id',args->>'request_id'));
  return jsonb_build_object('id',args->>'id','status','approved','verification_status','owner_declared_design_access','runtime_authorized',false);
 elsif action='revoke_connection' then
  if args ? 'access_token' or role_name<>'owner' then raise exception 'Browser company owner required';end if;
  update flux_private.builder_connections set revoked=true where tenant=tenant_id and company=company_id and id=(args->>'id')::uuid;
  insert into flux_private.mcp_events(user_id,action,detail) values(uid,'connection_design_revoked',jsonb_build_object('tenant',tenant_id,'company',company_id,'connection_id',args->>'id','request_id',args->>'request_id'));
  return jsonb_build_object('status','revoked');
 elsif action='snapshot' then
  return jsonb_build_object('revision',rev,'document',current_doc,'connections',coalesce((select jsonb_agg(jsonb_build_object('id',c.id,'system',c.system,'capabilities',c.capabilities,'status','approved','approved_by',c.approved_by,'approved_at',c.approved_at,'verification_status','owner_declared_design_access')) from flux_private.builder_connections c where c.tenant=tenant_id and c.company=company_id and not c.revoked and exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path=c.credential_path and flux_private.object_allowed(tenant_id,o.path,o.body,'use',uid,company_code))),'[]'),
   'workflows',coalesce((select jsonb_agg(x) from (select distinct on (body->>'id') jsonb_build_object('path',o.path,'body',o.body,'can_edit',flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) x from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'workflows/%' and o.body->>'company'=company_code and o.body->>'facility'=facility_code and flux_private.object_allowed(tenant_id,o.path,o.body,'view',uid,company_code) order by body->>'id',o.created_at desc,o.path desc) rows),'[]'),
   'agents',coalesce((select jsonb_agg(x) from (select distinct on (o.body->>'id') jsonb_build_object('path',o.path,'body',o.body,'can_edit',flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) x from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'agents/%' and o.body->>'company'=company_code and o.body->>'facility'=facility_code and flux_private.object_allowed(tenant_id,o.path,o.body,'view',uid,company_code) order by o.body->>'id',o.created_at desc,o.path desc) rows),'[]'),
   'resources',coalesce((select jsonb_agg(o.body || jsonb_build_object('canonical',o.path like 'resources/%','approved',o.path like 'resources/%' and exists(select 1 from public.flux_app_objects a where a.client_id=tenant_id and a.path like 'audit/%' and a.body->>'action'='resource.published' and a.body->'payload'->>'resource_ref'=(o.body->>'kind')||':'||(o.body->>'id')||'@'||(o.body->>'version')))) from public.flux_app_objects o where o.client_id=tenant_id and (o.path like 'library-'||tenant_id||'/%' or o.path like 'resources/%') and o.body->>'kind' in ('schema','rules','instructions','template','asset') and flux_private.object_allowed(tenant_id,o.path,o.body,'use',uid,company_code)),'[]'),
   'legacy',coalesce((select jsonb_agg(body) from flux_private.mcp_proposals where tenant=tenant_id and company=company_id and user_id=uid and body->'proposal'->>'kind'='agent'),'[]'));
 elsif action='commit' then
  if rid is null or args->>'request_hash' !~ '^[a-f0-9]{64}$' then raise exception 'Request UUID and hash required';end if;
  if (args->>'expected_revision')::bigint is distinct from rev then raise exception 'BUILDER_CONFLICT state revision changed';end if;
  next_doc:=args->'document';changes:=args->'changes';
  if next_doc::text ~* '(sk-ant-|sk-proj-|Bearer[[:space:]]+[^[:space:]]+|"(password|secret|client_secret|api_key|access_token|refresh_token|authorization|private_key|encrypted_value)"[[:space:]]*:)' then raise exception 'Secrets cannot enter builder documents or audit history';end if;
  if jsonb_typeof(next_doc) is distinct from 'object' or jsonb_typeof(changes) is distinct from 'array' then raise exception 'Invalid builder document';end if;
  if exists(select 1 from jsonb_object_keys(next_doc) key where key not in ('agents','workflows','resources','waivers','plans','change_sets')) then raise exception 'Unknown document collection';end if;
  for k in select unnest(array['agents','workflows','resources','waivers','plans','change_sets']) loop
   if jsonb_typeof(coalesce(next_doc->k,'{}'))<>'object' then raise exception 'Invalid collection';end if;
   for ident in select key from jsonb_object_keys(coalesce(next_doc->k,'{}')||coalesce(current_doc->k,'{}')) key loop
    if next_doc->k->ident is distinct from current_doc->k->ident and (select count(*) from jsonb_array_elements(changes) c where c->>'kind'=k and c->>'id'=ident)<>1 then raise exception 'Unattributed state change';end if;
   end loop;
  end loop;
  -- Every change is attributed by the verified scope; clients cannot supply native object paths.
  for item in select value from jsonb_array_elements(changes) loop
   k:=item->>'kind';ident:=item->>'id';r:=next_doc->k->ident;
   if k not in ('agents','workflows','resources','waivers','plans','change_sets') or r is null or (r->>'revision')::bigint is distinct from coalesce((current_doc->k->ident->>'revision')::bigint,0)+1 or r->>'review_status' is distinct from 'awaiting_user_review' then raise exception 'Invalid builder revision';end if;
   old_record:=current_doc->k->ident;
   if r ?| array['approved_by','approved_at','reviewed_by','reviewed_at','applied_result'] then raise exception 'Model cannot supply human review evidence';end if;
   if r->'native_source' is distinct from old_record->'native_source' and old_record is not null then raise exception 'Native source provenance cannot be replaced';end if;
   if k='resources' and exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and (o.path like 'library-'||tenant_id||'/%' or o.path like 'resources/%') and o.body->>'version'=r->'body'->>'version' and o.body->>'kind'=r->'body'->>'kind' and o.body->>'id' in (r->'body'->>'id',tenant_id||'.'||(r->'body'->>'id')) and o.body->'content' is distinct from r->'body'->'content') then raise exception 'BUILDER_CONFLICT immutable resource version';end if;
   if k='agents' then
    for field_name in select unnest(array['execute.authority','verify.approval_gate','execute.model_access']) loop
     v:=r->'body'->'fields'->field_name->>'value';
     if v is not null and not (field_name='execute.model_access' and v='off') and r->'body'->'fields'->field_name is distinct from old_record->'body'->'fields'->field_name then
      if not exists(select 1 from public.flux_app_objects o cross join lateral jsonb_array_elements(coalesce(o.body->'nodes','[]')) n where o.client_id=tenant_id and o.path like 'workflows/%' and o.body->>'company'=company_code and n->'data'->'guided'->>'id'=ident and n->'data'->'guided'->'fields'->field_name=r->'body'->'fields'->field_name and flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) and not exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path=r->'native_source'->>'path' and o.path like 'agents/%' and o.body->'guided'->'fields'->field_name=r->'body'->'fields'->field_name and flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) then raise exception 'Human choice required';end if;
     end if;
    end loop;
   end if;
   if k='workflows' then
    for node in select value from jsonb_array_elements(r->'body'->'nodes') loop
     if node->'data'->'guided' is distinct from next_doc->'agents'->(node->'data'->'guided'->>'id')->'body' then raise exception 'Workflow node must match scoped agent draft';end if;
     if node->'data'->>'power' is distinct from 'Off' then raise exception 'Proposal nodes must remain Off';end if;
    end loop;
   end if;
   if k='agents' and (r->'body'->'fields'->'identity.owner'->>'value' is distinct from uid::text or r->'body'->'fields'->'identity.company'->>'value' is distinct from company_code or r->'body'->'fields'->'identity.environment'->>'value' is distinct from 'TEST') then raise exception 'Agent identity scope denied';end if;
   if k='workflows' and (r->'body'->>'tenant' is distinct from tenant_id or r->'body'->>'company' is distinct from company_code or r->'body'->>'facility' is distinct from facility_code or coalesce((r->'body'->>'execution_enabled')::boolean,true)) then raise exception 'Workflow scope denied';end if;
   if r ? 'native_source' and not exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path=r->'native_source'->>'path' and o.body->>'content_hash'=r->'native_source'->>'content_hash' and flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) then raise exception 'BUILDER_CONFLICT native source changed or edit permission removed';end if;
   if k='workflows' and r ? 'native_source' and exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'workflows/%' and o.body->>'id'=ident and o.created_at>(select o2.created_at from public.flux_app_objects o2 where o2.client_id=tenant_id and o2.path=r->'native_source'->>'path')) then raise exception 'BUILDER_CONFLICT newer canvas exists';end if;
   if k='agents' and r ? 'native_source' and exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'agents/%' and o.body->>'id'=ident and o.created_at>(select o2.created_at from public.flux_app_objects o2 where o2.client_id=tenant_id and o2.path=r->'native_source'->>'path')) then raise exception 'BUILDER_CONFLICT newer agent exists';end if;
   if k='change_sets' and (r->'body'->'base_document') is distinct from (current_doc-'change_sets') then raise exception 'BUILDER_CONFLICT change set base changed';end if;
   if k='agents' then continue;end if;
   proposal:=jsonb_build_object('kind','build_session','record_kind',k,'record_id',ident,'content_hash',r->>'content_hash','revision',r->'revision','body',r->'body','validation',item->'validation');
   path_name:='mcp-inbox/'||uid::text||'-'||(r->>'proposal_id')||'.json';
   insert into flux_private.mcp_proposals(path,user_id,tenant,company,body) values(path_name,uid,tenant_id,company_id,jsonb_build_object('id',r->>'proposal_id','created_by',uid,'tenant',tenant_id,'company',company_id,'created_at',now(),'request_hash',args->>'request_hash','proposal',proposal))
   on conflict(path) do update set body=excluded.body,decision=null;
  end loop;
  result:=args->'response';
  insert into flux_private.builder_sessions values(tenant_id,company_id,uid,rev+1,next_doc) on conflict(tenant,company,user_id) do update set revision=excluded.revision,document=excluded.document;
  insert into flux_private.builder_requests(tenant,company,user_id,request_id,request_hash,response) values(tenant_id,company_id,uid,rid,args->>'request_hash',result);
  insert into flux_private.builder_history(tenant,company,user_id,revision,request_id,action,document,changes,changed_fields) values(tenant_id,company_id,uid,rev+1,rid,'propose',next_doc,changes,coalesce(args->'changed_fields','[]'));
  return result;
 elsif action='review' then
  if args ? 'access_token' then raise exception 'Human browser review required';end if;
  if (args->>'expected_revision')::bigint is distinct from rev then raise exception 'BUILDER_CONFLICT review revision changed';end if;
  k:=args->>'record_kind';ident:=args->>'record_id';r:=current_doc->k->ident;
  if r is null or r->>'content_hash' is distinct from args->>'expected_hash' then raise exception 'BUILDER_CONFLICT review hash changed';end if;
  if r->>'review_status' in ('applied','approved','dismissed') then return coalesce(r->'applied_result',jsonb_build_object('status',r->>'review_status'));end if;
  review_decision:='dismissed';result:=jsonb_build_object('status','dismissed','activation_enabled',false);
  if (args->>'approve')::boolean then
   review_decision:='applied';result:=jsonb_build_object('status','applied','activation_enabled',false);
   if k='change_sets' then
    if (current_doc-'change_sets') is distinct from r->'body'->'base_document' then raise exception 'BUILDER_CONFLICT change set base changed';end if;
    next_doc:=(r->'body'->'document')||jsonb_build_object('change_sets',coalesce(current_doc->'change_sets','{}'));
    perform public.flux_builder_session('commit',jsonb_build_object('tenant',tenant_id,'company',company_id,'request_id',r->'body'->>'apply_request_id','request_hash',r->>'content_hash','expected_revision',rev,'document',next_doc,'changes',r->'body'->'changes','changed_fields',jsonb_build_array('atomic_change_set'),'response',jsonb_build_object('change_set_id',ident)));
    for item in select value from jsonb_array_elements(r->'body'->'changes') loop
     if item->>'kind' in ('resources','workflows') then
      select revision into rev from flux_private.builder_sessions where tenant=tenant_id and company=company_id and user_id=uid;
      perform public.flux_builder_session('review',jsonb_build_object('tenant',tenant_id,'company',company_id,'record_kind',item->>'kind','record_id',item->>'id','expected_hash',item->>'content_hash','expected_revision',rev,'approve',true,'native_body',args->'native_bodies'->(item->>'id')));
     end if;
    end loop;
    select revision,document into rev,current_doc from flux_private.builder_sessions where tenant=tenant_id and company=company_id and user_id=uid;
    result:=jsonb_build_object('status','applied','change_set_id',ident,'members',r->'body'->'changes','activation_enabled',false,'resources_approval_required',true);
   elsif k='waivers' then
    if role_name<>'owner' then raise exception 'Owner authorization required';end if;
    review_decision:='approved';r:=r||jsonb_build_object('approved_by',uid,'approved_at',now());result:=jsonb_build_object('status','approved','waiver_id',ident,'activation_enabled',false);
   elsif k='workflows' then
    native:=r->'body';
    if native->>'tenant' is distinct from tenant_id or native->>'company' is distinct from company_code or native->>'facility' is distinct from facility_code or coalesce((native->>'execution_enabled')::boolean,true) then raise exception 'Workflow scope denied';end if;
    if r ? 'native_source' then
     if not exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path=r->'native_source'->>'path' and o.body->>'content_hash'=r->'native_source'->>'content_hash' and flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) then raise exception 'BUILDER_CONFLICT native source unavailable';end if;
     if exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'workflows/%' and o.body->>'id'=ident and o.created_at>(select o2.created_at from public.flux_app_objects o2 where o2.client_id=tenant_id and o2.path=r->'native_source'->>'path')) then raise exception 'BUILDER_CONFLICT newer canvas exists';end if;
    end if;
    for node in select value from jsonb_array_elements(native->'nodes') loop
     old_record:=current_doc->'agents'->(node->'data'->'guided'->>'id');
     if old_record ? 'native_source' and (not exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path=old_record->'native_source'->>'path' and flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) or exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'agents/%' and o.body->>'id'=old_record->>'id' and o.created_at>(select o2.created_at from public.flux_app_objects o2 where o2.client_id=tenant_id and o2.path=old_record->'native_source'->>'path'))) then raise exception 'BUILDER_CONFLICT agent source changed or permission removed';end if;
    end loop;
    v:=case when r ? 'native_source' then regexp_replace(native->>'version','[0-9]+$',(coalesce((select substring(o.body->>'version' from '[0-9]+$')::int from public.flux_app_objects o where o.client_id=tenant_id and o.path=r->'native_source'->>'path'),0)+1)::text) else '0.0.'||(r->>'revision') end;
    existing:=args->'native_body';
    if existing is null or (existing-array['version','draft_revision','release_version','content_hash','created_at','actor','status','execution_enabled']) is distinct from (native-array['version','draft_revision','release_version','content_hash','created_at','actor','status','execution_enabled']) or existing->>'version' is distinct from v or existing->>'draft_revision' is distinct from v or existing->>'actor' is distinct from uid::text or existing->>'status' is distinct from 'draft' or coalesce((existing->>'execution_enabled')::boolean,true) or existing->>'content_hash' !~ '^[a-f0-9]{64}$' then raise exception 'Native canvas must match reviewed proposal';end if;
    native:=existing;
    path_name:='workflows/'||ident||'--'||(native->>'version')||'.json';
    result:=result||jsonb_build_object('canvas',native);
   elsif k='resources' then
    native:=r->'body';
    if native->>'kind' not in ('schema','rules') or native->>'tenant' is distinct from tenant_id or native->>'created_by' is distinct from uid::text or native->>'status'<>'draft' or native ? 'encrypted_value' then raise exception 'Resource scope denied';end if;
    if exists(select 1 from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'library-'||tenant_id||'/%' and o.body->>'id'=native->>'id' and not flux_private.object_allowed(tenant_id,o.path,o.body,'edit',uid,company_code)) then raise exception 'Resource edit permission required';end if;
    path_name:='library-'||tenant_id||'/'||(native->>'id')||'--'||(native->>'version')||'.json';
    result:=result||jsonb_build_object('resource_id',r->>'resource_ref','status','draft','approval_required',true);
   elsif k='plans' then
    if r->'body'->'source'->>'kind'='workflow' then
     canonical:=r->'body'->'source'->>'workflow_id';
     if current_doc->'workflows'->canonical is not null then
      if current_doc->'workflows'->canonical->>'content_hash' is distinct from r->'body'->'source'->>'content_hash' then raise exception 'BUILDER_CONFLICT workflow plan source changed';end if;
     elsif r->'body'->'source'->>'content_hash' is distinct from (select o.body->>'content_hash' from public.flux_app_objects o where o.client_id=tenant_id and o.path like 'workflows/%' and o.body->>'company'=company_code and o.body->>'id'=canonical and flux_private.object_allowed(tenant_id,o.path,o.body,'view',uid,company_code) order by o.created_at desc,o.path desc limit 1) then raise exception 'BUILDER_CONFLICT workflow plan source changed';end if;
    end if;
    if r->'body'->'source'->>'kind'='waiver' and (current_doc->'waivers'->(r->'body'->'source'->>'waiver_id')->>'review_status' is distinct from 'approved' or current_doc->'waivers'->(r->'body'->'source'->>'waiver_id')->>'content_hash' is distinct from r->'body'->'source'->>'content_hash') then raise exception 'Approved waiver required';end if;
    result:=result||jsonb_build_object('kind','workflow_plan','status','accepted_for_design','environment','TEST');
   elsif k='agents' then
    raise exception 'Review the connected workflow proposal to apply this agent';
   else raise exception 'Unknown proposal kind';end if;
   if k in ('workflows','resources') then
    select body into existing from public.flux_app_objects where client_id=tenant_id and path=path_name;
    if found and existing->>'content_hash' is distinct from native->>'content_hash' then raise exception 'BUILDER_CONFLICT immutable native version exists';end if;
    if existing is null then insert into public.flux_app_objects(client_id,path,body) values(tenant_id,path_name,native);end if;
    if k='workflows' then r:=r||jsonb_build_object('native_source',jsonb_build_object('path',path_name,'content_hash',native->>'content_hash'));end if;
   end if;
  end if;
  r:=r||jsonb_build_object('review_status',review_decision,'applied_result',result,'reviewed_by',uid,'reviewed_at',now());next_doc:=jsonb_set(current_doc,array[k,ident],r);
  if k='workflows' and (args->>'approve')::boolean then
   for node in select value from jsonb_array_elements(r->'body'->'nodes') loop
    canonical:=node->'data'->'guided'->>'id';
    next_doc:=jsonb_set(next_doc,array['agents',canonical],(next_doc->'agents'->canonical)||jsonb_build_object('review_status','applied','reviewed_by',uid,'reviewed_at',now()));
   end loop;
  end if;
  update flux_private.builder_sessions set revision=rev+1,document=next_doc where tenant=tenant_id and company=company_id and user_id=uid;
  update flux_private.mcp_proposals set decision=jsonb_build_object('decision',review_decision,'result',result,'actor',uid,'created_at',now()) where tenant=tenant_id and company=company_id and user_id=uid and body->>'id'=r->>'proposal_id';
  insert into flux_private.builder_history(tenant,company,user_id,revision,request_id,action,document,changes,changed_fields) values(tenant_id,company_id,uid,rev+1,(r->>'request_id')::uuid,'review',next_doc,jsonb_build_array(jsonb_build_object('kind',k,'id',ident,'decision',review_decision,'content_hash',r->>'content_hash')),'[]');
  return result;
 end if;
 raise exception 'Unknown builder operation';
end $$;
-- Old clients and new tools share the request UUID namespace for this user/company.
create function flux_private.builder_legacy_request_guard() returns trigger language plpgsql security definer set search_path='' as $$
begin
 perform pg_advisory_xact_lock(hashtextextended(new.tenant||new.company::text||new.user_id::text,0));
 if exists(select 1 from flux_private.builder_requests b where b.tenant=new.tenant and b.company=new.company and b.user_id=new.user_id and b.request_id::text=new.body->>'id') then raise exception 'BUILDER_CONFLICT request_id already used by builder';end if;
 return new;
end $$;
create trigger builder_legacy_request_guard before insert on flux_private.mcp_proposals for each row execute function flux_private.builder_legacy_request_guard();
revoke all on function flux_private.builder_legacy_request_guard() from public;
revoke all on function public.flux_builder_session(text,jsonb) from public;
grant execute on function public.flux_builder_session(text,jsonb) to anon,authenticated;
revoke all on function flux_private.builder_immutable() from public;
commit;
