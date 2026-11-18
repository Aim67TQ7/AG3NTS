"""Company-scoped observation of the independently deployed directory operator.

This integration grants no Studio execution authority and stores no credentials.
"""
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import JSONResponse
import httpx
from . import fresh
from .core import digest

router = APIRouter(prefix='/api/studio/copackers-operator')
AGENT_ID = 'copackers-directory-operator'
PUBLIC_STATUS = 'https://copackers-operator.by-pete.com/status'
STATUS_URL = 'http://127.0.0.1:8609/status'


def allowed(context=None):
    c = fresh.CTX.get() if context is None else context
    return bool(c and c.get('client', {}).get('id') == 'n0v8v-llc'
                and c.get('company', {}).get('code') == 'N0V8V')


def installed_agent():
    if not allowed():
        return None
    values = {
        'identity.department': 'sales', 'identity.company': 'N0V8V',
        'identity.environment': 'PROD', 'trigger.type': 'schedule',
        'trigger.source_record': 'schedule.tick', 'trigger.schedule': 'hourly',
        'trigger.duplicates': 'process_new_revision_only',
        'input.source_system': 'supabase', 'input.freshness': 'under_24_hours',
        'input.when_missing': 'review_required', 'execute.method': 'deterministic_rule',
        'execute.model_access': 'off', 'execute.cost_ceiling': 'zero',
        'execute.time_limit': '5m', 'execute.rule': 'none',
        'execute.instructions': 'none', 'output.record_type': 'custom_needs_schema',
        'output.evidence': 'source_refs_hashes', 'output.outcomes': 'full_set',
        'output.next': 'none', 'error.retry': 'none',
        'error.retryable': 'none', 'error.escalation': 'human_review_queue',
        'error.ambiguous_external': 'suspend_and_reconcile',
        'verify.method': 'automatic', 'verify.postcondition': 'evidence_hash_match',
    }
    fields = {key: {'value': value, 'source': 'installed_external_runtime',
                     'why': 'Observed external deployment; no Studio execution grant.'}
              for key, value in values.items()}
    guided = {
        'id': AGENT_ID, 'version': '1.0.0',
        'name': 'CoPackers Near Me Business Operator',
        'responsibility': 'Operate copackersnearme.com toward profitable paid listings and qualified introductions, with source verification and measured costs.',
        'capability': 'RULE', 'tenant': 'n0v8v-llc', 'company': 'N0V8V',
        'facility': '', 'guide_version': '1.0.0', 'catalog_version': '1.0.0',
        'fields': fields, 'questions_for_user': [], 'questions_by_step': {},
        'runtime_binding': {'kind': 'external_directory', 'id': AGENT_ID,
                            'status_url': PUBLIC_STATUS, 'managed_by': 'Docker on PETE'},
    }
    definition = {
        'id': AGENT_ID, 'version': '1.0.0', 'name': guided['name'],
        'responsibility': guided['responsibility'], 'capability': 'RULE',
        'tenant': 'n0v8v-llc', 'company': 'N0V8V', 'facility': '',
        'guided': guided, 'guided_hash': digest(guided), 'status': 'external_installed',
        'authority': None, 'model_access': 'off', 'resource_refs': [],
        'input_schema': {'type': 'object'}, 'output_schema': {'type': 'object'},
        'functions': {}, 'tests': [],
        'execution': {'kind': 'external-service', 'dispatch_enabled': False,
                      'runtime': '/opt/copackers-operator', 'status_url': PUBLIC_STATUS},
        'instructions': 'This installed operator runs independently in Docker on PETE. AG3NTS observes it through a read-only status endpoint. Source verification, listing quality, durable inbound leads, commercial tasks and revenue/cost accounting live in its own runtime. Paid spend requires an approved budget. Source links do not prove claims. Never mark revenue as collected without payment evidence. This card grants no native Studio execution, credential selection, publication approval or advertising authority.',
    }
    definition['content_hash'] = digest(definition)
    return definition


@router.get('/status')
async def status():
    if not allowed():
        return JSONResponse({'detail': 'Directory operator is not available in this company'}, 404)
    observed_at = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(STATUS_URL)
        if response.status_code != 200 or len(response.content) > 65536:
            raise ValueError('Unavailable status response')
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError('Invalid status response')
        return {'available': True, 'observed_at': observed_at,
                'status_url': PUBLIC_STATUS, 'runtime': 'Independent Docker service',
                'native_studio_execution': False,
                'status': str(body.get('status', 'reachable'))[:80],
                'operator': body}
    except (httpx.HTTPError, ValueError):
        return JSONResponse({'available': False, 'observed_at': observed_at,
                             'status': 'unavailable', 'native_studio_execution': False},
                            headers={'Cache-Control': 'no-store'})
