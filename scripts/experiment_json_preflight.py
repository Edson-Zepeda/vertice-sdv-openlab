"""Isolated proposal: bound JSON structural allocation before decoding.

This script does not change the application's JSON loader. It measures the
proposal against real valid fixtures and deliberately invalid local inputs.
"""
from __future__ import annotations
import gc
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from independent_oracle import named_cases
from vertice.codec import load_json, solve_json
from vertice.graph import ValidationError


def preflight(text):
    """Scan punctuation outside strings; JSON grammar remains json.loads' job."""
    if text.count('{')+text.count('[')<=5000 and text.count(',')+text.count(':')<=50000:
        return
    position=0
    length=len(text)
    containers=0
    punctuation=0
    while position<length:
        character=text[position]
        if character=='"':
            end=text.find('"',position+1)
            while end>=0:
                back=end-1
                while back>position and text[back]=='\\':
                    back-=1
                if (end-1-back)%2==0:
                    break
                end=text.find('"',end+1)
            if end<0:
                return  # The actual parser reports an unterminated string.
            position=end+1
            continue
        if character in '[{':
            containers+=1
            if containers>5000:
                raise ValidationError('El JSON excede la estructura admitida para un grafo.')
        elif character in ',:':
            punctuation+=1
            if punctuation>50000:
                raise ValidationError('El JSON contiene demasiados campos para un grafo.')
        position+=1


def timed(callback,repeats=5):
    callback()
    result=[]
    for _ in range(repeats):
        start=time.perf_counter_ns();callback();result.append((time.perf_counter_ns()-start)/1e6)
    return {'samples_ms':result,'median_ms':statistics.median(result)}


def measured_rejection(text):
    gc.collect();tracemalloc.start()
    try:
        # Include the existing UTF-8 size guard in the proposal allocation peak.
        if len(text.encode('utf8'))>2*1024*1024:raise ValidationError('Tamaño excedido')
        preflight(text);solve_json(text)
    except ValidationError as error:
        message=str(error)
    else:raise AssertionError('Expected a rejection')
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    return {'message':message,'peak_python_bytes':peak,'input_utf8_bytes':len(text.encode()),'sha256':hashlib.sha256(text.encode()).hexdigest()}


def main():
    output=ROOT/'evidence/profiling/json_preflight_experiment.json'
    checks=[]
    cases=named_cases()
    # Named-case records are supplied by the independent test fixture builder.
    if isinstance(cases,dict):cases=list(cases.values())
    fixture=json.loads((ROOT/'evidence/profiling/import_500_4000.json').read_text(encoding='utf8'))
    maximum=json.dumps(fixture,ensure_ascii=False,separators=(',',':'))
    preflight(maximum)
    checks.append({'name':'Maximum graph fixture','passed':load_json(maximum)==fixture})
    for file in sorted((ROOT/'examples').glob('*.json')):
        raw=file.read_text(encoding='utf8');preflight(raw)
        checks.append({'name':file.name,'passed':load_json(raw)==json.loads(raw)})
    # Braces, commas, quotes and escape sequences in labels are not structure.
    for label in ['[{,:}]'*12,'\\"'*30,'"'*80,'\\'*80,'🧭 ruta áéíóú','}{]['*20]:
        data={'schema_version':1,'directed':False,'nodes':[{'id':'A','label':label,'x':0,'y':0}],'edges':[]}
        for ascii_only in [False,True]:
            raw=json.dumps(data,ensure_ascii=ascii_only);preflight(raw)
            checks.append({'name':f'Escaped label {repr(label[:10])} ASCII={ascii_only}','passed':load_json(raw)==data})
    hostile={
        'wide_objects':'['+','.join(['{}']*699050)+']',
        'wide_integers':'['+','.join(['0']*500000)+']',
        'deep_array':'['*500+']'*500,
        'deep_object':'{"a":'*500+'0'+'}'*500,
    }
    report={'proposal_only':True,'python':sys.version,'scope':'Python traced allocation, not process/browser RAM; browser endurance test runs concurrently.',
            'checks':checks,'valid_maximum_bytes':len(maximum.encode()),
            'valid_preflight':timed(lambda:preflight(maximum)),
            'valid_current_pipeline':timed(lambda:solve_json(maximum)),
            'hostile':{name:measured_rejection(raw) for name,raw in hostile.items()}}
    report['all_checks_passed']=all(check['passed'] for check in checks)
    report['source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
