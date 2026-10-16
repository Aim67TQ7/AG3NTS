-- Synthetic local auth contracts ONLY; no production tokens, records or grants.
create role anon;create role authenticated;
create schema flux_private;
create table public.flux_memberships(user_id uuid,client_id text,role text);
create table public.flux_companies(id uuid,client_id text,code text,facility text);
create table public.flux_app_objects(client_id text,path text,body jsonb,created_at timestamptz default clock_timestamp(),primary key(client_id,path));
create table flux_private.mcp_proposals(path text primary key,user_id uuid,tenant text,company uuid,body jsonb,decision jsonb);
create function flux_private.current_flux_user() returns uuid language sql as $$select nullif(current_setting('test.actor',true),'')::uuid$$;
create function flux_private.company_allowed(t text,c text,u uuid) returns boolean language sql as $$select exists(select 1 from public.flux_memberships where client_id=t and user_id=u) and coalesce(current_setting('test.company_denied',true),'')<>'yes'$$;
create function flux_private.object_allowed(t text,p text,b jsonb,a text,u uuid,c text) returns boolean language sql as $$select b->>'deny' is distinct from a and coalesce(b->>'company',c)=c$$;
create function public.flux_mcp(action text,args jsonb) returns jsonb language plpgsql as $$
declare u uuid; t text; c uuid; r text;
begin
 if action<>'resolve' or args->>'access_token'<>'fmca_synthetic' then raise exception 'Invalid token';end if;
 u:=nullif(current_setting('test.actor',true),'')::uuid;t:=current_setting('test.tenant');c:=current_setting('test.company')::uuid;
 select role into r from public.flux_memberships where user_id=u and client_id=t;
 if r not in ('owner','editor') or r is null then raise exception 'Access removed';end if;
 return jsonb_build_object('user',jsonb_build_object('id',u),'client',jsonb_build_object('id',t),'company',jsonb_build_object('id',c),'role',r);
end $$;

create table flux_private.mcp_events(user_id uuid,action text,detail jsonb);
