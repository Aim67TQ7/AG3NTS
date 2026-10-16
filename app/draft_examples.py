"""Bounded, consented examples for design drafting; raw bytes are never persisted."""
import base64,binascii,hashlib
from .core import Invalid
MAX_BYTES=5*1024*1024
TYPES={'application/pdf':'document','image/png':'image','image/jpeg':'image','image/webp':'image'}
def example_content(body):
 example=body.get('example')
 if example is None:return [],[]
 if body.get('example_consent') is not True:raise Invalid('Approve sending this example to Anthropic before drafting')
 if not isinstance(example,dict) or example.get('media_type') not in TYPES:raise Invalid('Choose a PDF, PNG, JPEG or WebP example')
 encoded=example.get('data');media=example['media_type']
 if not isinstance(encoded,str) or len(encoded)>4*((MAX_BYTES+2)//3):raise Invalid('Example must be no larger than 5 MB')
 try:raw=base64.b64decode(encoded,validate=True)
 except (ValueError,binascii.Error):raise Invalid('Invalid example encoding')
 if not raw or len(raw)>MAX_BYTES:raise Invalid('Example must be no larger than 5 MB')
 valid={'application/pdf':raw.startswith(b'%PDF-'),'image/png':raw.startswith(b'\x89PNG\r\n\x1a\n'),'image/jpeg':raw.startswith(b'\xff\xd8\xff'),'image/webp':raw.startswith(b'RIFF') and raw[8:12]==b'WEBP'}
 if not valid[media]:raise Invalid('Example content does not match its file type')
 note=example.get('notes','')
 if not isinstance(note,str) or len(note)>4000:raise Invalid('Explain the example in up to 4000 characters')
 if not note.strip():raise Invalid('Describe the items to extract from this example')
 metadata={'sha256':hashlib.sha256(raw).hexdigest(),'media_type':media,'bytes':len(raw),'notes_hash':hashlib.sha256(note.encode()).hexdigest(),'provider':'Anthropic','consent':True}
 return [{'type':TYPES[media],'source':{'type':'base64','media_type':media,'data':encoded}},{'type':'text','text':'Operator instructions about the example: '+note}], [metadata]
