"""One responsibility: preserve extracted text/tables as a versioned JSON document."""
import hashlib,json,re
VERSION='1.0.0'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def convert(parsed):
 text=parsed.get('text') or '';issues=[]
 if parsed.get('status')!='extracted':issues.append('source_'+str(parsed.get('status','unknown')))
 if parsed.get('truncated'):issues.append('source_truncated')
 if parsed.get('confidence') is not None and parsed['confidence']<60:issues.append('low_ocr_confidence')
 if parsed.get('error'):issues.append('source_reader_warning')
 tables=parsed.get('tables') or [];parts=parsed.get('parts') or []
 if not isinstance(tables,list) or not isinstance(parts,list):raise ValueError('Invalid parser tables or parts')
 pages=[]
 for match in re.finditer(r'(?:^|\n)=== page (\d+) ===\n(.*?)(?=\n=== page \d+ ===\n|\Z)',text,re.S):pages.append({'page':int(match[1]),'text':match[2].strip()})
 if not pages and text:pages=[{'page':1,'text':text}]
 return {'schema':'flux.document-json','schema_version':VERSION,'source':{k:parsed.get(k) for k in ('message_id','attachment_id','mailbox','filename','content_type','sha256','reader_version','extracted_at')},'document':{'text':text,'pages':pages,'tables':tables,'parts':parts},'quality':{'source_status':parsed.get('status'),'method':parsed.get('method'),'confidence':parsed.get('confidence'),'truncated':bool(parsed.get('truncated')),'issues':issues,'human_review_required':bool(issues)},'business_fields':{},'business_fields_status':'No business extraction schema applied'}
