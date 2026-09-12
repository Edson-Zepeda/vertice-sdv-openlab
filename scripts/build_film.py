"""Video explicativo: gráficos de ejecuciones Python y mediciones guardadas.

Pillow compone gráficos científicos originales. Edge TTS recibe únicamente el
guion público y conserva palabras/tiempos; el render posterior funciona sin red.
"""
from __future__ import annotations
import argparse
import asyncio
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vertice import solve_payload
sys.path.insert(0, str(ROOT/'tests'))
from independent_oracle import bellman_ford, decimal_text, named_cases

WORK = ROOT / 'media' / 'render'
NARRATION = ROOT / 'media' / 'narration'
OUT = ROOT / 'web' / 'media'
W, H, FPS = 1920, 1080, 30
PAPER, INK, TEAL, CORAL = '#f5f4ed', '#153d37', '#125b51', '#d95435'
MUTED, LINE, SOFT, WHITE = '#526861', '#ccd8cd', '#e7eddf', '#fffef9'
LIME = '#d9e8a7'
VOICE = 'es-MX-JorgeNeural'

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def smooth(t):
    t = max(0., min(1., t))
    return t*t*(3-2*t)
def mix(a, b, t): return a+(b-a)*t

@lru_cache(maxsize=128)
def font(size=32, bold=False):
    path = ROOT / 'web' / 'fonts' / ('Manrope.ttf' if bold else 'DMSans.ttf')
    value = ImageFont.truetype(str(path), int(size))
    try:
        axes = value.get_variation_axes()
        value.set_variation_by_axes([700 if b'Weight' in a['name'] and bold else 450 if b'Weight' in a['name'] else a['default'] for a in axes])
    except (OSError, AttributeError):
        pass
    return value

def text(draw, value, x, y, size=32, color=INK, bold=False, anchor=None):
    draw.text((round(x), round(y)), str(value), font=font(size,bold), fill=color, anchor=anchor)

def box(draw, rect, fill=WHITE, outline=LINE, radius=24, width=2):
    draw.rounded_rectangle(tuple(round(v) for v in rect), radius=radius, fill=fill, outline=outline, width=width)

def wrapped(draw, value, x, y, width, size=32, color=INK, bold=False, spacing=10):
    line = ''
    for word in str(value).split():
        trial = (line+' '+word).strip()
        if line and draw.textlength(trial, font=font(size,bold)) > width:
            text(draw,line,x,y,size,color,bold)
            y += size+spacing
            line = word
        else: line = trial
    if line: text(draw,line,x,y,size,color,bold)
    return y+size+spacing

def arrow(draw, a, b, color=TEAL, width=5, head=14):
    draw.line((a,b),fill=color,width=width)
    angle=math.atan2(b[1]-a[1],b[0]-a[0])
    points=[b,(b[0]-head*math.cos(angle-.5),b[1]-head*math.sin(angle-.5)),(b[0]-head*math.cos(angle+.5),b[1]-head*math.sin(angle+.5))]
    draw.polygon(points,fill=color)

def probe(path):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_format','-show_streams','-of','json',str(path)],text=True,encoding='utf-8'))

def sources():
    examples = json.loads((ROOT/'web/data/examples.json').read_text(encoding='utf8'))
    data = {row['id']: {**row,'result':solve_payload({k:row[k] for k in ('graph','source','target')})} for row in examples}
    reverse={**data['direccion'],'source':'D','target':'A'}
    reverse['result']=solve_payload({k:reverse[k] for k in ('graph','source','target')})
    data['direccion_inversa']=reverse
    for row in data.values():
        row['oracle_cost']=decimal_text(bellman_ford(row['graph'],row['source'])[row['target']])
        assert row['oracle_cost']==row['result']['cost']
    decimal_case=next(row for row in named_cases() if row['id']=='decimal_exact')
    data['decimal_proof']=solve_payload(decimal_case['payload'])
    assert data['decimal_proof']['cost']=='0.3'
    data['benchmark'] = json.loads((ROOT/'evidence/verification/benchmark.json').read_text(encoding='utf8'))
    for row in data['benchmark']['results']:
        assert row['oracle_match'], 'No se grafica un benchmark que difiere del oráculo.'
    assert data['desvio']['result']['cost']=='11'
    assert data['aislado']['result']['status']=='no_path'
    return data

def scenes():
    return [
      {'id':'intro','title':'El costo decide la ruta.','label':'VÉRTICE / SDV','minimum':14,
       'narration':'Una conexión puede cambiar todo el recorrido. Vértice convierte un grafo en una decisión que puedes explicar: crear nodos, asignar costos y encontrar la ruta mínima. Cada línea resaltada proviene de una ejecución real del algoritmo.'},
      {'id':'objects','title':'Cuatro clases. Una responsabilidad clara.','label':'PROGRAMACIÓN ORIENTADA A OBJETOS','minimum':18,
       'narration':'El reto de software pide Dijkstra desde cero y programación orientada a objetos. Nodo conserva identidad y posición. Conexión guarda extremos y peso. Grafo mantiene las relaciones válidas. El solucionador consulta esa estructura y calcula la ruta. La interfaz y la terminal usan el mismo núcleo Python.'},
      {'id':'trace','title':'La frontera avanza.','label':'EVENTOS EMITIDOS POR PYTHON','minimum':27,
       'narration':'El inicio entra con costo cero. La cola elige el menor costo conocido. Al asentar un nodo, su distancia se vuelve definitiva. Después, el algoritmo compara sus conexiones y conserva únicamente las mejoras. El verde claro muestra la frontera: distancias tentativas que todavía pueden cambiar. La búsqueda termina cuando se asienta el destino.'},
      {'id':'relax','title':'Mejorar una distancia cambia la decisión.','label':'RELAJACIÓN / EJEMPLO EJECUTADO','minimum':21,
       'narration':'Llegar directamente del nodo ese al nodo a cuesta cuatro. Pero pasar por el nodo be cuesta dos más uno: tres. Esa mejora reemplaza el costo conocido de a. La entrada antigua permanece en la cola y se descarta al extraerse. Los predecesores guardan cómo reconstruir la ruta encontrada, sin confundir una visita con una mejora.'},
      {'id':'decimal','title':'Los decimales conservan su valor.','label':'ENTRADA Y ARITMÉTICA EXACTAS','minimum':18,
       'narration':'Un décimo más dos décimos debe producir tres décimos. El motor conserva el texto numérico, valida sus límites y suma con aritmética decimal. También rechaza pesos negativos y valores demasiado precisos. Importar un archivo no debe redondear silenciosamente el problema que la persona quiere resolver.'},
      {'id':'cases','title':'Los casos difíciles también tienen respuesta.','label':'GRAFOS DIDÁCTICOS / RESULTADOS REALES','minimum':23,
       'narration':'Un ciclo de costo cero no debe atrapar la búsqueda. Dos rutas empatadas pueden ser óptimas; se muestra una de forma reproducible. En un grafo dirigido, invertir el recorrido puede impedir llegar. Y cuando el destino está desconectado, la respuesta correcta es sin ruta. Estos casos forman parte de las pruebas.'},
      {'id':'oracle','title':'Comprobar desde otro algoritmo.','label':'VERIFICACIÓN INDEPENDIENTE','minimum':22,
       'narration':'Para revisar Dijkstra usamos Bellman Ford, un algoritmo independiente, con costos enteros en micro unidades. Contrastamos el costo mínimo con ese oráculo. Revisamos las conexiones de la ruta y las trazas mediante invariantes. Conservamos las pruebas que fallaron antes de corregirlas. Esa evidencia muestra lo que se comprobó, sin convertir las pruebas en una garantía absoluta.'},
      {'id':'benchmark','title':'Medir también exige separar los costos.','label':'MEDICIONES LOCALES / MILISEGUNDOS','minimum':23,
       'narration':'Medimos por separado el solucionador y el proceso completo de validación, construcción y salida JSON. Cada barra resume nueve ejecuciones del mismo caso, después del calentamiento. El tamaño y la densidad del grafo importan. Estas mediciones corresponden a Python en esta computadora; no representan el tiempo de un vehículo ni el de todos los navegadores.'},
      {'id':'studio','title':'Edita. Calcula. Comprueba.','label':'ESTUDIO INTERACTIVO','minimum':20,
       'narration':'En el estudio puedes cambiar el grafo, deshacer una edición e importar o exportar tus ejemplos. La reproducción permite detenerse en cada decisión. El informe conecta requisitos, clases, pruebas y límites. El resultado es un proyecto de software que puedes explorar, reproducir y defender con el código abierto a la vista.'},
    ]

async def voice_assets(items):
    import edge_tts
    limiter=asyncio.Semaphore(2)
    async def one(index,scene):
        audio=NARRATION/f'voice_{index:02}.mp3'
        metadata=NARRATION/f'voice_{index:02}.json'
        text_hash=hashlib.sha256((scene['narration']+VOICE+'+2%').encode()).hexdigest()
        if audio.exists() and metadata.exists() and json.loads(metadata.read_text(encoding='utf8'))['text_hash']==text_hash:
            return
        async with limiter:
            words=[]
            speech=edge_tts.Communicate(scene['narration'],VOICE,rate='+2%',boundary='WordBoundary')
            with audio.open('wb') as stream:
                async for chunk in speech.stream():
                    if chunk['type']=='audio': stream.write(chunk['data'])
                    elif chunk['type']=='WordBoundary':
                        words.append({'text':chunk['text'],'start':chunk['offset']/1e7,'end':(chunk['offset']+chunk['duration'])/1e7})
            metadata.write_text(json.dumps({'voice':VOICE,'generated_voice':True,'text_hash':text_hash,'text':scene['narration'],'words':words},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    await asyncio.gather(*(one(i,s) for i,s in enumerate(items)))

def subtitle_chunks(words):
    group=[]
    for word in words:
        trial=' '.join([w['text'] for w in group]+[word['text']])
        if group and (len(trial)>76 or word['end']-group[0]['start']>5.2):
            yield {'start':group[0]['start'],'end':group[-1]['end']+.12,'text':' '.join(w['text'] for w in group)}
            group=[]
        group.append(word)
    if group: yield {'start':group[0]['start'],'end':group[-1]['end']+.15,'text':' '.join(w['text'] for w in group)}

def restore_punctuation(words, original):
    cursor=0;result=[]
    for word in words:
        position=original.lower().find(word['text'].lower(),cursor)
        label=word['text']
        if position>=0:
            end=position+len(word['text'])
            while end<len(original) and original[end] in '.,;:!?':end+=1
            label=original[position:end]
            cursor=end
        result.append({**word,'text':label})
    return result

def phrase_start(words, phrase, default=0):
    normalize=lambda value: ''.join(c.lower() for c in value if c.isalnum())
    target=[normalize(value) for value in phrase.split()]
    tokens=[normalize(word['text']) for word in words]
    for i in range(len(tokens)-len(target)+1):
        if tokens[i:i+len(target)]==target:return words[i]['start']+.55
    return default

class Renderer:
    def __init__(self,data,items):
        self.data,self.items=data,items
        self.bases=[self.base(i,scene) for i,scene in enumerate(items)]
        shot=ROOT/'output/playwright/desktop-route.png'
        self.screen=Image.open(shot).convert('RGB') if shot.exists() else None
    def base(self,index,scene):
        image=Image.new('RGB',(W,H),PAPER)
        draw=ImageDraw.Draw(image)
        text(draw,'VÉRTICE',80,42,37,INK,True)
        text(draw,'SDV · SOFTWARE',1840,51,24,MUTED,anchor='rt')
        draw.line((80,106,1840,106),fill=LINE,width=2)
        text(draw,scene['label'],82,141,25,TEAL,True)
        text(draw,scene['title'],77,187,61 if len(scene['title'])>42 else 68,INK,True)
        text(draw,f'{index+1:02} / {len(self.items):02}',1840,1025,23,MUTED,anchor='rt')
        text(draw,'RUTAS MÍNIMAS · DIJKSTRA',80,1025,23,MUTED)
        return image
    def graph(self,draw,example,rect,progress=1.,state=None,route=False,weights=True):
        graph=example['graph']; result=example['result']
        left,top,width,height=rect
        xs=[n['x'] for n in graph['nodes']]; ys=[n['y'] for n in graph['nodes']]
        scale=min((width-100)/max(1,max(xs)-min(xs)),(height-120)/max(1,max(ys)-min(ys)))
        mx,my=(max(xs)+min(xs))/2,(max(ys)+min(ys))/2
        positions={n['id']:(left+width/2+(n['x']-mx)*scale,top+height/2+(n['y']-my)*scale) for n in graph['nodes']}
        radius=29 if width<650 else 37
        path_edges=set(result['edge_path']) if route else set()
        current=state.get('edge') if state else None
        cost_labels=[]
        for index,edge in enumerate(graph['edges']):
            start,end=positions[edge['source']],positions[edge['target']]
            amount=smooth(progress*1.5-index/max(1,len(graph['edges']))*.5)
            point=(mix(start[0],end[0],amount),mix(start[1],end[1],amount))
            color=CORAL if edge['id'] in path_edges else TEAL if edge['id']==current else '#aebeb0'
            draw.line((start,point),fill=color,width=7 if edge['id'] in path_edges else 4)
            if graph['directed'] and amount>.95:
                dx,dy=end[0]-start[0],end[1]-start[1]; length=max(1,math.hypot(dx,dy))
                tip=(end[0]-dx/length*(radius+4),end[1]-dy/length*(radius+4))
                arrow(draw,(tip[0]-dx/length*12,tip[1]-dy/length*12),tip,color,4,12)
            if weights and amount>.85:
                x,y=(start[0]+end[0])/2,(start[1]+end[1])/2
                label=str(edge['weight']); size=25 if width<650 else 29
                label_width=draw.textlength(label,font=font(size))+22
                cost_labels.append((x,y,label_width,label,size,color if edge['id'] in path_edges else INK))
        if route and len(result['path'])>1:
            travel=(self.now*.42)%(len(result['path'])-1)
            i=int(travel);fraction=travel-i
            a,b=positions[result['path'][i]],positions[result['path'][i+1]]
            x,y=mix(a[0],b[0],fraction),mix(a[1],b[1],fraction)
            draw.ellipse((x-10,y-10,x+10,y+10),fill=WHITE,outline=CORAL,width=4)
        for x,y,label_width,label,size,color in cost_labels:
            box(draw,(x-label_width/2,y-20,x+label_width/2,y+20),PAPER,LINE,10,1)
            text(draw,label,x,y,size,color,anchor='mm')
        settled=set(state.get('settled',[])) if state else set()
        distances=state.get('distances',{}) if state else {}
        for node in graph['nodes']:
            x,y=positions[node['id']]
            fill=CORAL if route and node['id'] in result['path'] else TEAL if node['id'] in settled else LIME if distances.get(node['id']) is not None else WHITE
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill,outline=INK,width=3)
            text(draw,node['id'],x,y-1,29 if width<650 else 34,WHITE if fill in (TEAL,CORAL) else INK,True,'mm')
            if state and node['id'] in distances:
                cost=distances[node['id']]
                text(draw,'∞' if cost is None else cost,x,y+radius+19,23,MUTED,anchor='mm')
        return positions
    def trace_state(self,events,index):
        state={'settled':[],'distances':{},'edge':None}
        for event in events[:index+1]:
            if event['kind']=='initialize': state['distances'][event['node']]='0'
            elif event['kind']=='relax': state['distances'][event['target']]=event['new_cost']
            elif event['kind']=='settle': state['settled'].append(event['node'])
        state['edge']=events[index].get('edge')
        return state
    def frame(self,index,t,duration):
        self.now=t
        scene=self.items[index]; kind=scene['id']; p=t/duration
        image=self.bases[index].copy(); draw=ImageDraw.Draw(image)
        if kind=='intro':
            example=self.data['desvio']; found=p>.48
            self.graph(draw,example,(80,300,1220,565),smooth(t/3),route=found)
            text(draw,'S → T',1400,370,40,MUTED,True)
            text(draw,'11' if found else '…',1370,423,146,CORAL,True)
            text(draw,'costo mínimo' if found else 'explorando',1400,609,32,MUTED)
            if found: wrapped(draw,'S → B → D → E → T',1398,688,390,35,INK,True)
        elif kind=='objects':
            cards=[(80,365,430,780,'Node','Identidad · etiqueta','x, y'),(475,365,825,780,'Edge','Origen · destino','peso Decimal'),(870,365,1220,780,'Graph','Nodos · conexiones','adyacencia válida'),(1265,365,1838,780,'DijkstraSolver','Consulta el grafo','ruta · costo · traza')]
            beats=scene['beats']['classes']
            active=max((i for i,at in enumerate(beats) if t>=at),default=-1)
            for i,(x1,y1,x2,y2,title,a,b) in enumerate(cards):
                offset=(1-smooth((t-i*.6)/1.1))*65
                box(draw,(x1,y1+offset,x2,y2+offset),TEAL if i==3 else WHITE,TEAL if i==3 else LINE)
                color=WHITE if i==3 else INK
                text(draw,f'0{i+1}',x1+26,y1+offset+28,27,LIME if i==3 else CORAL,True)
                text(draw,title,x1+26,y1+offset+104,42 if i<3 else 43,color,True)
                wrapped(draw,a,x1+26,y1+offset+205,x2-x1-50,29,color)
                wrapped(draw,b,x1+26,y1+offset+285,x2-x1-50,28,LIME if i==3 else MUTED)
                if i==active:
                    draw.rounded_rectangle((x1,y1+offset,x2,y2+offset),radius=24,outline=CORAL,width=5)
                    local=min(1,max(0,(t-beats[i])/.7))
                    draw.line((x1+28,y1+offset+180,x1+28+(x2-x1-56)*smooth(local),y1+offset+180),fill=LIME if i==3 else CORAL,width=5)
            arrow(draw,(1005,823),(1600,823),CORAL,5)
            xx=mix(1005,1600,(t*.2)%1)
            draw.ellipse((xx-9,814,xx+9,832),fill=INK)
            text(draw,'Una responsabilidad por clase',80,837,30,MUTED)
        elif kind=='trace':
            example=self.data['desvio']; events=example['result']['trace']
            step=min(len(events)-1,int(max(0,t-1)/(duration-2)*len(events)))
            state=self.trace_state(events,step);event=events[step]
            self.graph(draw,example,(60,315,1250,565),1,state,route=event['kind']=='finish')
            box(draw,(1345,310,1840,864))
            text(draw,f'PASO {step+1:02} / {len(events)}',1380,341,26,TEAL,True)
            titles={'initialize':'Inicio = 0','settle':f'Asentar {event.get("node","")}','consider':'Comparar conexión','relax':'Mejorar costo','stale':'Descartar entrada','finish':'Ruta mínima: 11'}
            wrapped(draw,titles[event['kind']],1380,391,420,35,INK,True)
            frontier=[(n,c) for n,c in state['distances'].items() if n not in state['settled']]
            frontier.sort(key=lambda item:(Decimal(item[1]),item[0]))
            text(draw,'FRONTERA · TENTATIVA',1380,486,24,MUTED,True)
            for i,(node,cost) in enumerate(frontier[:5]):
                yy=535+i*52;box(draw,(1380,yy,1805,yy+42),SOFT,SOFT,8)
                text(draw,node,1398,yy+20,27,INK,True,'lm');text(draw,cost,1787,yy+20,27,INK,True,'rm')
            if not frontier:text(draw,'Sin nodos pendientes',1380,548,27,MUTED)
            text(draw,f'{len(state["settled"])} nodos asentados',1380,812,26,TEAL)
        elif kind=='relax':
            box(draw,(80,330,1050,850)); box(draw,(1100,330,1840,850),TEAL,TEAL)
            pts={'S':(220,581),'B':(540,742),'A':(865,486)}
            amount=smooth(t/5)
            for a,b,label,color in [('S','A','4',MUTED),('S','B','2',CORAL),('B','A','1',CORAL)]:
                pa,pb=pts[a],pts[b];draw.line((pa,(mix(pa[0],pb[0],amount),mix(pa[1],pb[1],amount))),fill=color,width=7)
                tx,ty=(pa[0]+pb[0])/2,(pa[1]+pb[1])/2
                box(draw,(tx-25,ty-24,tx+25,ty+24),PAPER,PAPER,10)
                text(draw,label,tx,ty,33,color,True,'mm')
            for name,(x,y) in pts.items():
                draw.ellipse((x-44,y-44,x+44,y+44),fill=WHITE,outline=INK,width=4)
                text(draw,name,x,y,38,INK,True,'mm')
            text(draw,'Costo conocido de A',1150,389,34,WHITE,True)
            text(draw,'4',1160,477,104,'#abc3b5',True)
            text(draw,'→',1360,486,83,LIME,True)
            text(draw,'3' if p>.3 else '?',1515,477,104,WHITE,True)
            text(draw,'2 + 1 < 4',1155,632,61,LIME,True)
            text(draw,'Mejora estricta',1158,745,33,WHITE)
        elif kind=='decimal':
            for i,(label,value) in enumerate([('PRIMER TRAMO','0.1'),('SEGUNDO TRAMO','0.2'),('COSTO TOTAL','0.3')]):
                x=85+i*610; amount=smooth((t-i*.7)/1.1)
                box(draw,(x,370+(1-amount)*60,x+525,795+(1-amount)*60),TEAL if i==2 else WHITE,TEAL if i==2 else LINE)
                text(draw,label,x+34,417+(1-amount)*60,25,LIME if i==2 else MUTED,True)
                text(draw,value,x+35,509+(1-amount)*60,118,WHITE if i==2 else INK,True)
                active_decimal=max((j for j,at in enumerate(scene['beats']['values']) if t>=at),default=-1)
                if i==active_decimal:draw.rounded_rectangle((x,370,x+525,795),radius=24,outline=CORAL,width=5)
                if i<2:text(draw,'+' if i==0 else '=',x+551,530,60,CORAL,True)
            box(draw,(85,836,667,897),SOFT,SOFT,10)
            box(draw,(674,836,1829,897),TEAL,TEAL,10)
            text(draw,'0.1',376,866,29,INK,True,'mm');text(draw,'0.2',1250,866,29,WHITE,True,'mm')
        elif kind=='cases':
            rows=[('cero','Ciclos cero','0.25'),('empate','Rutas empatadas','2'),('aislado','Destino aislado','Sin ruta')]
            if scene['beats']['direction']<=t<scene['beats']['disconnected']:
                rows[2]=('direccion_inversa','Sentido único','Sin ruta')
            for i,(key,title,cost) in enumerate(rows):
                x=75+i*605
                box(draw,(x,321,x+570,878))
                text(draw,title,x+27,353,31,INK,True)
                example=self.data[key]
                if key=='cero':
                    # A planar visual layout of the same graph avoids crossing cost labels.
                    coordinates={'A':(0,0),'B':(200,-160),'C':(380,0),'D':(200,160),'E':(620,160)}
                    example={**example,'graph':{**example['graph'],'nodes':[{**node,'x':coordinates[node['id']][0],'y':coordinates[node['id']][1]} for node in example['graph']['nodes']]}}
                self.graph(draw,example,(x+10,414,550,300),1,route=p>.25)
                text(draw,cost,x+27,781,52,CORAL,True)
                text(draw,f'{example["source"]} → {example["target"]}',x+530,815,29,TEAL,True,'rm')
                text(draw,'costo mínimo' if example['result']['status']=='ok' else 'resultado explícito',x+28,845,24,MUTED)
        elif kind=='oracle':
            cases=['desvio','cero','empate','aislado','direccion']
            selected=self.data[cases[min(len(cases)-1,int(p*len(cases)))]]
            expected=selected['oracle_cost'];label='Sin ruta' if expected is None else expected
            box(draw,(80,351,850,822));box(draw,(1070,351,1840,822),TEAL,TEAL)
            text(draw,'DIJKSTRA',120,395,28,TEAL,True)
            text(draw,'Cola mínima',120,470,58,INK,True)
            wrapped(draw,'Relajaciones y asentamiento de nodos.',123,575,650,33,MUTED)
            text(draw,'BELLMAN-FORD',1110,395,28,LIME,True)
            text(draw,'Oráculo independiente',1110,470,48,WHITE,True)
            wrapped(draw,'Relajaciones por rondas; costos enteros.',1113,575,650,33,WHITE)
            text(draw,label,120,701,71,CORAL,True);text(draw,label,1110,701,71,LIME,True)
            text(draw,f'{selected["source"]} → {selected["target"]}',800,725,30,MUTED,True,'rm')
            text(draw,f'{selected["source"]} → {selected["target"]}',1790,725,30,WHITE,True,'rm')
            text(draw,'COSTO',953,510,22,MUTED,True,'mm');text(draw,'=',912,545,85,CORAL,True)
            text(draw,'Costo vs. oráculo; ruta y traza por invariantes.',82,863,31,TEAL,True)
        elif kind=='benchmark':
            selected=[r for r in self.data['benchmark']['results'] if r['trace_enabled']]
            maximum=max(r['json_to_json']['median_ms'] for r in selected)*1.14
            labels={'chain_50':'Cadena / 50 nodos','chain_200':'Cadena / 200 nodos','chain_500':'Cadena / 500 nodos','directed_500_4000':'Dirigido / 500 nodos','undirected_grid_400':'Malla / 400 nodos','unreachable_500_zero_chain':'Sin ruta / 500 nodos','same_source_target_500':'Inicio = destino / 500 nodos'}
            x,y,width=550,361,1210
            for tick in range(5):
                value=maximum*tick/4;xx=x+width*tick/4
                draw.line((xx,331,xx,852),fill=LINE,width=2)
                text(draw,f'{value:.0f}',xx,302,25,MUTED,anchor='mm')
            for i,row in enumerate(selected):
                yy=y+i*72
                text(draw,labels[row['id']],83,yy-3,27,INK)
                text(draw,f'{row["edges"]} conexiones',84,yy+29,23,MUTED)
                a=row['solver_only']['median_ms'];b=row['json_to_json']['median_ms']
                amount=smooth((t-i*.18)/3)
                draw.rounded_rectangle((x,yy,x+max(3,width*a/maximum*amount),yy+18),radius=4,fill=TEAL)
                draw.rounded_rectangle((x,yy+24,x+max(3,width*b/maximum*amount),yy+42),radius=4,fill=CORAL)
                text(draw,f'{b:.1f}',x+width*b/maximum+12,yy+34,25,CORAL,True,'lm')
            draw.rectangle((80,880,104,904),fill=TEAL);text(draw,'Algoritmo',117,880,25,INK)
            draw.rectangle((346,880,370,904),fill=CORAL);text(draw,'JSON → JSON',383,880,25,INK)
            text(draw,'Mediana · 9 ejecuciones · CPython local · con traza',1838,880,25,MUTED,anchor='rt')
        elif kind=='studio':
            if self.screen:
                # Show the actual studio region large enough to read, with a slow pan.
                height=min(self.screen.height,round(self.screen.width*630/1640))
                top=round((self.screen.height-height)*smooth(p))
                source=self.screen.crop((0,top,self.screen.width,top+height))
                ratio=min(1640/source.width,610/source.height)
                frame=source.resize((round(source.width*ratio),round(source.height*ratio)),Image.Resampling.LANCZOS)
                x=(W-frame.width)//2;y=299
                image.paste(frame,(x,y))
                draw=ImageDraw.Draw(image)
            else:
                self.graph(draw,self.data['desvio'],(80,330,1750,560),1,route=True)
        # Burned captions use actual word boundaries; the downloadable VTT matches.
        cue=next((c for c in scene['cues'] if c['start']<=t<min(c['end'],duration)),None)
        if cue:
            box(draw,(170,923,1750,1005),INK,INK,15)
            if draw.textlength(cue['text'],font=font(30))<1510:
                text(draw,cue['text'],W/2,964,30,WHITE,anchor='mm')
            else:
                wrapped(draw,cue['text'],210,930,1500,29,WHITE,spacing=5)
        draw.line((80,1009,80+1760*max(0,min(1,p)),1009),fill=CORAL,width=4)
        return image

def timestamp(seconds, comma=False):
    milliseconds=round(seconds*1000);hours,milliseconds=divmod(milliseconds,3600000);minutes,milliseconds=divmod(milliseconds,60000);sec,ms=divmod(milliseconds,1000)
    return f'{hours:02}:{minutes:02}:{sec:02}{"," if comma else "."}{ms:03}'

def main():
    global FFMPEG,FFPROBE
    parser=argparse.ArgumentParser()
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--ffmpeg',default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe',default=shutil.which('ffprobe'))
    args=parser.parse_args();FFMPEG,FFPROBE=args.ffmpeg,args.ffprobe
    if not FFMPEG or not FFPROBE: parser.error('Se requieren ffmpeg y ffprobe.')
    WORK.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True);NARRATION.mkdir(parents=True,exist_ok=True)
    data=sources();items=scenes()
    asyncio.run(voice_assets(items))
    offset=0;vtt=['WEBVTT',''];metadata=[';FFMETADATA1','title=VÉRTICE / SDV - Cada decisión a la vista','artist=VÉRTICE']
    for i,scene in enumerate(items):
        voice=NARRATION/f'voice_{i:02}.mp3';meta=json.loads((NARRATION/f'voice_{i:02}.json').read_text(encoding='utf8'))
        audio_duration=float(probe(voice)['format']['duration'])
        scene['duration']=math.ceil(max(scene['minimum'],audio_duration+1.25)*FPS)/FPS
        scene['start']=offset
        scene['cues']=list(subtitle_chunks(restore_punctuation(meta['words'],scene['narration'])))
        for current,next_cue in zip(scene['cues'],scene['cues'][1:]):
            current['end']=min(current['end'],next_cue['start']-.001)
            assert current['end']>current['start']
        if scene['id']=='cases':
            scene['beats']={'direction':phrase_start(meta['words'],'En un grafo dirigido',scene['duration']*.5),'disconnected':phrase_start(meta['words'],'Y cuando',scene['duration']*.75)}
        elif scene['id']=='objects':
            scene['beats']={'classes':[phrase_start(meta['words'],phrase) for phrase in ('Nodo conserva','Conexión guarda','Grafo mantiene','El solucionador')]}
        elif scene['id']=='decimal':
            scene['beats']={'values':[phrase_start(meta['words'],phrase) for phrase in ('Un décimo','dos décimos','tres décimos')]}
        for cue in scene['cues']:
            cue['start']+=.55;cue['end']+=.55
            vtt.extend([f'{timestamp(offset+cue["start"])} --> {timestamp(offset+min(cue["end"],scene["duration"]))}',cue['text'],''])
        metadata.extend(['[CHAPTER]','TIMEBASE=1/1000',f'START={round(offset*1000)}',f'END={round((offset+scene["duration"])*1000)}',f'title={scene["title"]}'])
        offset+=scene['duration']
    (OUT/'VerticeSDV.vtt').write_text('\n'.join(vtt),encoding='utf8')
    (WORK/'chapters.ffmeta').write_text('\n'.join(metadata)+'\n',encoding='utf8')
    renderer=Renderer(data,items)
    for i,scene in enumerate(items):
        renderer.frame(i,scene['duration']*.58,scene['duration']).save(WORK/f'preview_{i+1:02}.png')
    # The chapter's closing pause shows the completed route without a cut-off caption.
    renderer.frame(0,items[0]['duration']-.1,items[0]['duration']).save(OUT/'VerticeSDV_Poster.jpg',quality=94)
    proof={'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'resolution':[W,H],'fps':FPS,'duration_seconds':offset,
           'scenes':items,'voice':VOICE,'generated_voice':True,'charts':'Graph geometry and trace data from actual Python executions; benchmark data from stored measurements.',
           'source_hashes':{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in [ROOT/'web/data/examples.json',ROOT/'evidence/verification/benchmark.json',ROOT/'tests/independent_oracle.py',ROOT/'vertice/graph.py',ROOT/'vertice/dijkstra.py',ROOT/'vertice/codec.py',Path(__file__)]}}
    asset_paths=[ROOT/'output/playwright/desktop-route.png',ROOT/'web/fonts/Manrope.ttf',ROOT/'web/fonts/DMSans.ttf']
    asset_paths.extend(NARRATION/f'voice_{i:02}.{suffix}' for i in range(len(items)) for suffix in ('mp3','json'))
    proof['asset_hashes']={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in asset_paths if p.exists()}
    labels=['Idea','Clases','Recorrido','Relajación','Decimales','Casos','Pruebas','Rendimiento','Estudio']
    (ROOT/'web/data/film.json').write_text(json.dumps({'duration':offset,'chapters':[{'label':labels[i],'title':s['title'],'start':s['start']} for i,s in enumerate(items)]},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (WORK/'film-plan.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'previews':len(items),'duration_seconds':offset,'render':args.render}),flush=True)
    if not args.render:return
    silent=WORK/'silent.mp4';log=WORK/'render.log';started=time.monotonic()
    with log.open('wb') as errors:
        command=[FFMPEG,'-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','medium','-crf','20','-threads','2','-pix_fmt','yuv420p',str(silent)]
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=errors)
        try:
            index=0
            for n in range(round(offset*FPS)):
                at=n/FPS
                while index+1<len(items) and at>=items[index+1]['start']:index+=1
                local=at-items[index]['start'];frame=renderer.frame(index,local,items[index]['duration'])
                if index and local<.45:
                    previous=renderer.frame(index-1,items[index-1]['duration']-.45+local,items[index-1]['duration'])
                    frame=Image.blend(previous,frame,smooth(local/.45))
                process.stdin.write(frame.tobytes())
                if n%(FPS*10)==0:print(json.dumps({'seconds':at,'total':offset,'elapsed':round(time.monotonic()-started,1)}),flush=True)
        finally:process.stdin.close()
        if process.wait()!=0:raise RuntimeError('Falló el render; consulta media/render/render.log.')
    inputs=[];filters=[]
    for i,scene in enumerate(items):
        inputs+=['-i',str(NARRATION/f'voice_{i:02}.mp3')]
        filters.append(f'[{i}:a]adelay=550|550,apad,atrim=duration={scene["duration"]},asetpts=PTS-STARTPTS[a{i}]')
    filters.append(''.join(f'[a{i}]' for i in range(len(items)))+f'concat=n={len(items)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[out]')
    narration=WORK/'narration.m4a'
    subprocess.run([FFMPEG,'-v','error','-y',*inputs,'-filter_complex',';'.join(filters),'-map','[out]','-c:a','aac','-b:a','192k',str(narration)],check=True)
    output=OUT/'VerticeSDV_Demo.mp4'
    subprocess.run([FFMPEG,'-v','error','-y','-i',str(silent),'-i',str(narration),'-i',str(WORK/'chapters.ffmeta'),'-map','0:v','-map','1:a','-map_metadata','2','-map_chapters','2','-c','copy','-movflags','+faststart',str(output)],check=True)
    proof['output']={'path':str(output.relative_to(ROOT)).replace('\\','/'),'sha256':digest(output),'bytes':output.stat().st_size,'probe':probe(output)}
    (ROOT/'evidence'/'video.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'video':str(output),'bytes':output.stat().st_size,'elapsed_seconds':round(time.monotonic()-started,1)}),flush=True)

if __name__=='__main__':main()
