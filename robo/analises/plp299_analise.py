# Análise local do PLP 299/2026. Uso: git clone -b analises-saida-plp299_tudo <repo> out; python3 robo/analises/plp299_analise.py out (gera out/../parl.json)
import json,sys,collections,csv
d=sys.argv[1]+'/'; L=lambda n:json.load(open(d+n))
SEC=[(1,3,'Agropecuária'),(5,9,'Extrativa e mineração'),(10,33,'Indústria'),(35,39,'Energia, água e saneamento'),(41,43,'Construção'),(45,47,'Comércio'),(49,53,'Transporte e logística'),(55,56,'Hospedagem e alimentação'),(58,63,'Comunicação e informação'),(64,66,'Finanças e seguros'),(68,68,'Imobiliário'),(69,75,'Serviços profissionais'),(77,82,'Serviços administrativos'),(84,84,'Adm. pública'),(85,85,'Educação'),(86,88,'Saúde'),(90,93,'Cultura, esporte e lazer'),(94,99,'Outros serviços')]
def sec(c):
    try: x=int(str(c).zfill(7)[:2])
    except: return 'Sem CNAE'
    for a,b,n in SEC:
        if a<=x<=b: return n
    return 'Outros serviços'
cad=L('cadastro.json');soc=L('socios.json')['socios'];emp=L('empresas.json')
ind=json.load(open('dados/indice.json'))['p']
votos={'S'+r['codigo']:r for r in csv.DictReader(open('robo/analises/plp299_votos.csv'),delimiter=';')}
dirbi=collections.defaultdict(float)
for b,ano,cod,trib,cn,v in L('dirbi_empresas.json')['dirbi']: dirbi[b]+=v
ecf=collections.defaultdict(float)
for e in L('ecf.json'):
    if e['ano'] and int(float(e['ano']))>=2023: ecf[e['cnpj'].replace('.','').replace('/','').replace('-','')[:8]]+=sum(v for k,v in e['itens'].items() if not k.startswith('f0000'))
def regime(b):
    r=cad.get(b,{}).get('regime')
    if not isinstance(r,list): return ''
    r=[x for x in r if isinstance(x,dict) and not x.get('cnpj_da_scp')]
    return max(r,key=lambda x:x['ano'])['forma_de_tributacao'] if r else ''
parl=collections.defaultdict(lambda:{'emp':[],'dirbi':0,'ecf':0})
for s in soc:
    b=s['cnpj'];c=cad.get(b,{})
    if c.get('situacao')!='ATIVA': continue
    p=parl[s['codigo']]
    p['emp'].append({'b':b,'razao':emp.get(b,{}).get('razao'),'cnae':c.get('cnae'),'desc':c.get('cnae_desc'),'sec':sec(c.get('cnae')),'reg':regime(b),'capital':emp.get(b,{}).get('capital',0),'dirbi':round(dirbi.get(b,0)),'ecf':round(ecf.get(b,0)),'uf':c.get('uf')})
    p['dirbi']+=dirbi.get(b,0); p['ecf']+=ecf.get(b,0)
info={}
for k,p in parl.items():
    i=ind.get(k,{}); v=votos.get(k,{})
    info[k]={'nome':i.get('n') or (v.get('nome')),'partido':i.get('s') or v.get('partido'),'uf':i.get('uf') or v.get('uf'),'grupo':i.get('cl'),'po':i.get('po'),'ex':i.get('ex'),'urg':v.get('urgencia'),'sub':v.get('substitutivo'),**p}
json.dump(info,open(d+'parl.json','w'),ensure_ascii=False)
# Senado
sen=[k for k in votos]; com=[k for k in sen if k in parl]
print('SENADO: senadores com empresa ativa',len(com),'de 81; empresas ativas',sum(len(parl[k]['emp']) for k in com))
def cont(ks,campo='substitutivo'): return dict(collections.Counter(votos[k][campo] for k in ks))
print(' voto sub com empresa',cont(com),' sem empresa',cont([k for k in sen if k not in parl]))
ben=[k for k in com if parl[k]['dirbi']+parl[k]['ecf']>0]
print(' com benefício declarado',len(ben),cont(ben))
for k in sorted(ben,key=lambda k:-(parl[k]['dirbi']+parl[k]['ecf'])): x=info[k];print('  ',x['nome'],x['partido'],x['uf'],x['sub'],round(x['dirbi']),round(x['ecf']),[ (e['razao'],e['sec'],e['dirbi'],e['ecf']) for e in x['emp'] if e['dirbi'] or e['ecf']])
bs=collections.defaultdict(set)
for k in com:
    for e in parl[k]['emp']: bs[e['sec']].add(k)
print(' SETORES (senadores):')
for s,ks in sorted(bs.items(),key=lambda x:-len(x[1])): print('  ',s,len(ks),cont(ks))
lp=[k for k in com if any('PRESUMIDO' in e['reg'] for e in parl[k]['emp'])]
print(' senadores com empresa no lucro presumido',len(lp),cont(lp))
# Câmara
dep=[k for k in parl if k[0]=='C']; depex=[k for k in dep if ind.get(k,{}).get('ex')]
print('CÂMARA: deputados com empresa ativa',len(dep),'em exercício',len(depex),'empresas',sum(len(parl[k]['emp']) for k in depex))
tot=collections.Counter(v.get('cl') for k,v in ind.items() if k[0]=='C' and v.get('ex'))
g=collections.Counter(ind[k].get('cl') for k in depex);print(' por grupo',dict(g),'total grupo',dict(tot))
bd=[k for k in depex if parl[k]['dirbi']+parl[k]['ecf']>0];print(' com benefício',len(bd),dict(collections.Counter(ind[k].get('cl') for k in bd)))
for k in sorted(bd,key=lambda k:-(parl[k]['dirbi']+parl[k]['ecf']))[:25]: x=info[k];print('  ',x['nome'],x['partido'],x['uf'],x['grupo'],round(x['dirbi']),round(x['ecf']),[(e['razao'],e['sec']) for e in x['emp'] if e['dirbi'] or e['ecf']][:2])
bc=collections.defaultdict(set)
for k in depex:
    for e in parl[k]['emp']: bc[e['sec']].add(k)
print(' SETORES (deputados):')
for s,ks in sorted(bc.items(),key=lambda x:-len(x[1])): print('  ',s,len(ks),dict(collections.Counter(ind[k].get('cl') for k in ks)))
lpd=[k for k in depex if any('PRESUMIDO' in e['reg'] for e in parl[k]['emp'])];print(' lucro presumido',len(lpd),dict(collections.Counter(ind[k].get('cl') for k in lpd)))
# Economia: DIRBI 2025 por setor
ds=collections.defaultdict(float)
for ano,cn,v in L('dirbi_setores.json')['setor']:
    if ano==2025: ds[sec(cn+'00000')]+=v
t=sum(ds.values());print('DIRBI 2025 total R$ bi',round(t/1e9,1))
for s,v in sorted(ds.items(),key=lambda x:-x[1]): print('  ',s,round(v/1e9,2),f'{100*v/t:.1f}%')
dc=collections.defaultdict(float)
for ano,cod,v in L('dirbi_setores.json')['codigo']:
    if ano==2025: dc[cod]+=v
print(' top códigos',[(c,round(v/1e9,1)) for c,v in sorted(dc.items(),key=lambda x:-x[1])[:12]])
