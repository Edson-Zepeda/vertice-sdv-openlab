"""Prepara referencias nativas para comparar el worker real en un navegador."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from vertice import solve_payload

source=ROOT/'evidence/verification/cases.json'
document=json.loads(source.read_text(encoding='utf8'))
rows=document if isinstance(document,list) else document['cases']
cases=[]
for row in rows:
    result=solve_payload(row['payload'])
    for key in ('cost','status'):
        assert result[key]==row['expected'][key]
    cases.append({'id':row['id'],'title':row['title'],'payload':row['payload'],'native_result':result})
output={'reference':'CPython and independently checked fixture expectations','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'core':{name:hashlib.sha256((ROOT/'vertice'/name).read_bytes()).hexdigest() for name in ('__init__.py','graph.py','dijkstra.py','codec.py')},'cases':cases}
(ROOT/'web/qa-cases.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8')
print(f'{len(cases)} referencias nativas para la comparación real del navegador.')
