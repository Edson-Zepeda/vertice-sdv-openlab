"""Create labeled teaching graphs; these are not measured road networks."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def graph(nodes, links, directed=False):
    return {'schema_version':1, 'directed':directed,
            'nodes':[{'id':key,'label':key,'x':x,'y':y} for key,x,y in nodes],
            'edges':[{'id':f'e{i+1}','source':a,'target':b,'weight':str(w)} for i,(a,b,w) in enumerate(links)]}

examples = [
    {'id':'desvio','name':'Un mejor desvío','description':'Una conexión indirecta mejora el costo conocido.', 'source':'S','target':'T',
     'graph':graph([('S',90,250),('A',270,100),('B',260,390),('C',470,110),('D',480,290),('E',710,130),('F',700,420),('T',920,260)],
                   [('S','A',4),('S','B',2),('A','B',1),('A','C',3),('A','D',6),('B','D',4),('C','D',1),('C','E',4),('D','E',2),('D','F',3),('E','T',3),('F','T',3)])},
    {'id':'empate','name':'Dos rutas, un costo','description':'Empate reproducible por ID de nodo.', 'source':'A','target':'D',
     'graph':graph([('A',170,260),('B',480,110),('C',480,410),('D',790,260)],
                   [('A','B',1),('A','C',1),('B','D',1),('C','D',1)])},
    {'id':'cero','name':'Cero también cuenta','description':'Costos cero, ciclo y decimales exactos.', 'source':'A','target':'D',
     'graph':graph([('A',150,240),('B',360,100),('C',380,370),('D',650,250),('E',840,130)],
                   [('A','B',0),('B','C',0),('C','A',0),('C','D','0.25'),('A','D',1),('D','E','0.1')])},
    {'id':'aislado','name':'Sin conexión','description':'El destino está en otro componente.', 'source':'A','target':'Z',
     'graph':graph([('A',130,240),('B',360,130),('C',360,390),('Y',730,160),('Z',850,350)],
                   [('A','B',2),('A','C',3),('B','C',1),('Y','Z',2)])},
    {'id':'direccion','name':'Sentido único','description':'Invertir inicio y destino cambia lo alcanzable.', 'source':'A','target':'D',
     'graph':graph([('A',120,230),('B',350,100),('C',600,100),('D',820,280),('E',410,410)],
                   [('A','B',1),('B','C',1),('C','D',1),('D','B','0.5'),('A','E',8),('E','D',1)], True)},
]
nodes = [(f'N{row}{col}', 120+col*145, 70+row*95) for row in range(5) for col in range(6)]
links = []
for row in range(5):
    for col in range(6):
        if col < 5: links.append((f'N{row}{col}', f'N{row}{col+1}', 1+(row+col)%3))
        if row < 4: links.append((f'N{row}{col}', f'N{row+1}{col}', 1+(2*row+col)%3))
examples.append({'id':'malla','name':'Red de 30 nodos','description':'Observa cómo crece la frontera.', 'source':'N00','target':'N45','graph':graph(nodes,links)})
for relative in ('examples', 'web/data'):
    (ROOT/relative).mkdir(parents=True, exist_ok=True)
(ROOT/'web/data/examples.json').write_text(json.dumps(examples, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
for item in examples:
    (ROOT/'examples'/f"{item['id']}.json").write_text(json.dumps(item['graph'], ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(f'{len(examples)} teaching graphs generated')
