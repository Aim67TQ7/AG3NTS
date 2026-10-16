-- Keep TEST and PROD approvals separate. A credential approval does not activate runtime.
alter table flux_private.builder_connections add column if not exists environment text not null default 'TEST' check(environment in ('TEST','PROD'));
do $$ declare d text; begin
 d:=pg_get_functiondef('public.flux_builder_session(text,jsonb)'::regprocedure);
 d:=replace(d,$old$insert into flux_private.builder_connections(tenant,company,id,credential_path,system,capabilities,approved_by) values(tenant_id,company_id,(args->>'id')::uuid,path_name,args->>'system',args->'capabilities',uid);$old$,$new$insert into flux_private.builder_connections(tenant,company,id,credential_path,system,capabilities,approved_by,environment) values(tenant_id,company_id,(args->>'id')::uuid,path_name,args->>'system',args->'capabilities',uid,coalesce(args->>'environment','TEST'));$new$);
 d:=replace(d,$old$'verification_status','owner_declared_design_access')) from flux_private.builder_connections c$old$,$new$'verification_status','owner_declared_design_access','environment',c.environment)) from flux_private.builder_connections c$new$);
 execute d;
end $$;
