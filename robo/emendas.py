# Gera dados/emendas.json a partir dos arquivos de emendas parlamentares do Portal da Transparência.
# Uso: python robo/emendas.py <pasta com os CSV> [dados/emendas.json]
import pandas as pd, json, unicodedata, re, sys, os, glob
RAIZ=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS=os.path.join(RAIZ,'dados')
ENTRADA=sys.argv[1]
SAIDA=sys.argv[2] if len(sys.argv)>2 else os.path.join(OBS,'emendas.json')
def arq(nome):
    c=[f for f in glob.glob(os.path.join(ENTRADA,'**','*.csv'),recursive=True) if os.path.basename(f).endswith(nome)]
    if not c: raise SystemExit('arquivo não encontrado: '+nome)
    return sorted(c)[-1]
n=lambda s: re.sub(r'\s+',' ',unicodedata.normalize('NFD',str(s)).encode('ascii','ignore').decode().upper().strip())
num=lambda s: pd.to_numeric(s.str.replace('.','',regex=False).str.replace(',','.',regex=False),errors='coerce').fillna(0)
GRUPOS=[('extrema','Extrema-direita',['PL','NOVO','MISSAO']),('direita','Direita',['PP','UNIAO','REPUBLICANOS','PODE','PSD','CIDADANIA','SOLIDARIEDADE']),
        ('alinhados','Alinhados',['MDB','PDT','REDE','PSB','PV']),('esquerda','Esquerda',['PT','PSOL','PCDOB']),('outros','Outros partidos',[])]
PART={p:g for g,_,ps in GRUPOS for p in ps}
par=json.load(open(f'{OBS}/parlamentares.json'))['p']; ind=json.load(open(f'{OBS}/indice.json'))['p']
pornome={}
for k,v in par.items():
    if not v.get('n') or k.startswith('SN:'): continue
    pornome.setdefault(n(v['n']),k)
def grupo(k):
    v=par[k]; sig=n(v.get('s','')).replace(' ','')
    return PART.get(v.get('p','')) or PART.get(sig) or 'outros'
e=pd.read_csv(arq('EmendasParlamentares.csv'),sep=';',encoding='latin1',dtype=str)
e=e[(e['Ano da Emenda']>='2023')&e['Tipo de Emenda'].str.startswith('Emenda Individual')].copy()
e['emp']=num(e['Valor Empenhado']); e['pago']=num(e['Valor Pago'])+num(e['Valor Restos A Pagar Pagos'])
e['k']=e['Nome do Autor da Emenda'].map(n).map(pornome)
semv=e[e.k.isna()]['emp'].sum(); tot=e['emp'].sum()
e=e[e.k.notna()].copy(); e['g']=e.k.map(grupo)
e['pix']=e['Tipo de Emenda'].str.contains('Especiais')
A=e['Nome Ação'].fillna('').map(n)
# temas pelas ações e funções
F=e['Nome Função'].fillna(''); NP=~e['pix']
LISTADAS=['Saúde','Educação','Assistência social','Urbanismo','Agricultura','Desporto e lazer','Segurança pública','Defesa nacional','Cultura','Direitos da cidadania']
outras_top=e[NP & ~F.isin(LISTADAS)].groupby('Nome Função')['emp'].sum().sort_values(ascending=False).head(6).index.tolist()
TEMAS=[
 ('saude','Saúde','', 'A maior destinação das emendas individuais, por obrigação legal de reservar ao menos metade delas à área. Inclui custeio da atenção básica e de hospitais, equipamentos e obras.', NP & F.eq('Saúde')),
 ('pix','Transferências especiais (Pix)','', 'Dinheiro repassado direto ao caixa de estados e municípios, sem finalidade definida nem convênio. É a modalidade menos transparente, porque não se sabe de antemão em que será gasto.', e['pix']),
 ('educacao','Educação','', 'De creches e escolas a universidades e institutos federais, incluindo equipamentos, obras e transporte escolar.', NP & F.eq('Educação')),
 ('assistencia','Assistência social','', 'Serviços socioassistenciais, assistência comunitária e acolhimento, área por onde passa parte dos recursos de comunidades terapêuticas e de entidades assistenciais.', NP & F.eq('Assistência social')),
 ('urbanismo','Urbanismo','', 'Pavimentação, infraestrutura urbana e obras nos municípios, área tradicional das emendas de visibilidade local.', NP & F.eq('Urbanismo')),
 ('agricultura','Agricultura','privilegios', 'Fomento ao setor agropecuário, máquinas, cadeias produtivas e extensão rural.', NP & F.eq('Agricultura')),
 ('esporte','Esporte e lazer','', 'Programas, eventos e infraestrutura de esporte e lazer, uma das áreas com mais repasses a entidades privadas.', NP & F.eq('Desporto e lazer')),
 ('seguranca','Segurança e defesa','punitivismo', 'Policiamento, viaturas, equipamentos e programas de enfrentamento ao crime, além de unidades e projetos das Forças Armadas.', NP & F.isin(['Segurança pública','Defesa nacional'])),
 ('cultura','Cultura','', 'Difusão cultural, patrimônio e projetos culturais.', NP & F.eq('Cultura')),
 ('direitos','Direitos da cidadania','igualdade', 'Direitos humanos, mulheres, igualdade racial, pessoas com deficiência, povos indígenas e proteção animal.', NP & F.eq('Direitos da cidadania')),
 ('outras','Outras funções','', 'Demais áreas com finalidade definida, sobretudo '+', '.join(f.lower() for f in outras_top[:-1])+' e '+outras_top[-1].lower()+'.', NP & ~F.isin(LISTADAS)),
]
for tid,_,_,_,mask in TEMAS: e['t_'+tid]=mask.values
gr={g:{'nome':nm,'partidos':ps,'n':int(e[e.g==g].k.nunique()),
       'dep':int(e[(e.g==g)&(e.k.str[0]=='C')].k.nunique()),'sen':int(e[(e.g==g)&(e.k.str[0]=='S')].k.nunique())} for g,nm,ps in GRUPOS}
totg={g:e[e.g==g].emp.sum() for g,_,_ in GRUPOS}
anos=['todos','2023','2024','2025','2026']
perfil={}
for a in anos:
    s=e if a=='todos' else e[e['Ano da Emenda']==a]
    perfil[a]={}
    for g,_,_ in GRUPOS:
        x=s[s.g==g]; fin=x[~x.pix]
        fun=fin.groupby('Nome Função')['emp'].sum()
        perfil[a][g]={'total':round(x.emp.sum()),'pago':round(x.pago.sum()),'pix':round(x[x.pix].emp.sum()),'saude':round(fun.get('Saúde',0)),
                      'n':int(x.k.nunique()),'funcoes':{f:round(v) for f,v in fun.items() if f!='Saúde' and v>0}}
# convênios e favorecidos
cv=pd.read_csv(arq('EmendasParlamentares_Convenios.csv'),sep=';',encoding='latin1',dtype=str); cv['valor']=num(cv['Valor Convênio'])
cod=e.drop_duplicates('Código da Emenda').set_index('Código da Emenda')
cv=cv[cv['Código da Emenda'].isin(cod.index)].copy(); cv['k']=cv['Código da Emenda'].map(cod.k); cv['g']=cv.k.map(grupo)
cv['obj']=cv['Objeto Convênio'].fillna('').str.strip(); cv['on']=cv.obj.map(n); cv['loc']=cv['Localidade do gasto'].fillna('')
fav=pd.read_csv(arq('EmendasParlamentares_PorFavorecido.csv'),sep=';',encoding='latin1',dtype=str,usecols=['Código da Emenda','Nome do Autor da Emenda','Tipo de Emenda','Ano/Mês','Favorecido','Natureza Jurídica','UF Favorecido','Município Favorecido','Valor Recebido'])
fav=fav[fav['Tipo de Emenda'].str.startswith('Emenda Individual')&(fav['Ano/Mês']>='202301')].copy()
fav['valor']=num(fav['Valor Recebido']); fav['k']=fav['Nome do Autor da Emenda'].map(n).map(pornome); fav=fav[fav.k.notna()].copy(); fav['g']=fav.k.map(grupo)
PRIV=r'Associação Privada|Fundação Privada|Organização Religiosa|Sociedade Empresária|Empresário|Cooperativa|Organização Social|Serviço Social Autônomo|Entidade Sindical|Sociedade Simples'
fav['priv']=fav['Natureza Jurídica'].fillna('').str.contains(PRIV)
rel=fav[fav['Natureza Jurídica'].fillna('').str.contains('Organização Religiosa')]
# tema extra: entidades religiosas (valor recebido)
OBJ_TEMA={'seguranca':r'VIATURA|POLICI|GUARDA MUNICIPAL|SEGURANCA PUBLICA|VIDEOMONITORAMENTO|CAMERA','drogas':r'TERAPEUTIC|DEPENDENT|DROGA','defesa':r'EXERCITO|MARINHA|AERONAUTICA|MILITAR|BATALHAO','agro':r'TRATOR|PATRULHA|AGRICOLA|RETROESCAVADEIRA|IMPLEMENTO','esporte':r'ESPORT|QUADRA|CAMPO DE FUTEBOL|EVENTO|COPA|CAMPEONATO'}
def nome_par(k): v=par[k]; return {'k':k,'n':v.get('n'),'p':v.get('p'),'s':v.get('s'),'uf':v.get('uf'),'c':v.get('c')}
temas=[]
for tid,nome,pauta,desc,_ in TEMAS:
    x=e[e['t_'+tid]]
    pg={g:round(x[x.g==g].emp.sum()) for g,_,_ in GRUPOS}
    med={g:(round(pg[g]/gr[g]['n']) if gr[g]['n'] else 0) for g in pg}
    fatia={g:(round(pg[g]/totg[g],4) if totg[g] else 0) for g in pg}
    alc={g:(round(x[(x.g==g)&(x.emp>0)].k.nunique()/gr[g]['n'],3) if gr[g]['n'] else 0) for g in pg}
    top=x.groupby('k').emp.sum().sort_values(ascending=False).head(5)
    codigos=set(x['Código da Emenda'])
    if tid=='pix':
        fp=fav[fav['Código da Emenda'].isin(codigos) & fav['Natureza Jurídica'].fillna('').str.contains('Município|Estado|Fundo')]
        mg=fp.groupby(['Favorecido','UF Favorecido','k']).valor.sum().sort_values(ascending=False).head(3)
        temas.append({'id':tid,'nome':nome,'pauta':pauta,'desc':desc,'total':pg,'media':med,'fatia':fatia,'alcance':alc,'top':[dict(nome_par(k),v=round(v)) for k,v in top.items()],
          'exemplos':[{'k':kk,'obj':'Repasse a '+re.sub(r'\b(De|Da|Do|Das|Dos|E)\b',lambda m:m.group(0).lower(),fv.title()),'v':round(v),'loc':uf} for (fv,uf,kk),v in mg.items()],'medida':'empenhado'})
        continue
    c=cv[cv['Código da Emenda'].isin(codigos)].sort_values('valor',ascending=False).drop_duplicates('obj').head(4)
    ex=[{'k':r.k,'obj':r.obj[:220],'v':round(r.valor),'loc':r.loc} for r in c.itertuples()]
    temas.append({'id':tid,'nome':nome,'pauta':pauta,'desc':desc,'total':pg,'media':med,'fatia':fatia,'alcance':alc,'top':[dict(nome_par(k),v=round(v)) for k,v in top.items()],'exemplos':ex,'medida':'empenhado'})
# perfis
parl={}
for k,x in e.groupby('k'):
    fin=x[~x.pix]; fun=fin.groupby('Nome Função').emp.sum().sort_values(ascending=False)
    fk=fav[fav.k==k].copy(); fk['loc']=fk['Município Favorecido'].fillna('').str.title()+' ('+fk['UF Favorecido'].fillna('')+')'
    fk=fk[fk['Município Favorecido'].fillna('').ne('') & ~fk['Natureza Jurídica'].fillna('').str.contains('Economia Mista|Federal|Empresa Pública')]
    mg=fk.groupby('loc').valor.sum().sort_values(ascending=False); mun=mg.head(8)
    f=fav[(fav.k==k)&fav.priv].groupby(['Favorecido','Natureza Jurídica']).valor.sum().sort_values(ascending=False).head(6)
    c=cv[cv.k==k].sort_values('valor',ascending=False).drop_duplicates('obj').head(6)
    d=nome_par(k); d.update({'g':grupo(k),'emp':round(x.emp.sum()),'pago':round(x.pago.sum()),'pix':round(x[x.pix].emp.sum()),
      'anos':{a:round(v) for a,v in x.groupby('Ano da Emenda').emp.sum().items()},
      'funcoes':[[f_,round(v)] for f_,v in fun.items() if v>0],
      'temas':{t[0]:round(x[x['t_'+t[0]]].emp.sum()) for t in TEMAS if x[x['t_'+t[0]]].emp.sum()>0},
      'munis':[[m_,round(v)] for m_,v in mun.items()],'nmun':int(len(mg)),
      'favs':[[a_,b_,round(v)] for (a_,b_),v in f.items()],
      'objs':[[r.obj[:200],round(r.valor),r.loc] for r in c.itertuples()]})
    parl[k]=d

# ------------------------------------------------ distribuição por estado
# População do Censo 2022 (IBGE).
POP={'AC':830018,'AL':3127683,'AP':733759,'AM':3941613,'BA':14141626,'CE':8794957,'DF':2817381,'ES':3833712,'GO':7056495,'MA':6776699,
 'MT':3658649,'MS':2757013,'MG':20539989,'PA':8120131,'PB':3974687,'PR':11444380,'PE':9058931,'PI':3271199,'RJ':16055174,'RN':3302729,
 'RS':10882965,'RO':1581196,'RR':636707,'SC':7610361,'SP':44411238,'SE':2210004,'TO':1511460}
NOME_UF={'ACRE':'AC','ALAGOAS':'AL','AMAPA':'AP','AMAZONAS':'AM','BAHIA':'BA','CEARA':'CE','DISTRITO FEDERAL':'DF','ESPIRITO SANTO':'ES','GOIAS':'GO',
 'MARANHAO':'MA','MATO GROSSO':'MT','MATO GROSSO DO SUL':'MS','MINAS GERAIS':'MG','PARA':'PA','PARAIBA':'PB','PARANA':'PR','PERNAMBUCO':'PE','PIAUI':'PI',
 'RIO DE JANEIRO':'RJ','RIO GRANDE DO NORTE':'RN','RIO GRANDE DO SUL':'RS','RONDONIA':'RO','RORAIMA':'RR','SANTA CATARINA':'SC','SAO PAULO':'SP','SERGIPE':'SE','TOCANTINS':'TO'}
NOMES={'AC':'Acre','AL':'Alagoas','AP':'Amapá','AM':'Amazonas','BA':'Bahia','CE':'Ceará','DF':'Distrito Federal','ES':'Espírito Santo','GO':'Goiás','MA':'Maranhão',
 'MT':'Mato Grosso','MS':'Mato Grosso do Sul','MG':'Minas Gerais','PA':'Pará','PB':'Paraíba','PR':'Paraná','PE':'Pernambuco','PI':'Piauí','RJ':'Rio de Janeiro','RN':'Rio Grande do Norte',
 'RS':'Rio Grande do Sul','RO':'Rondônia','RR':'Roraima','SC':'Santa Catarina','SP':'São Paulo','SE':'Sergipe','TO':'Tocantins'}
titulo=lambda t: re.sub(r"\b(De|Da|Do|Das|Dos|E|D')\b",lambda m:m.group(0).lower(),str(t).title())
e['uf']=e['UF'].map(lambda x: NOME_UF.get(n(x)))
semuf=e[e.uf.isna()].emp.sum()
e['uf_autor']=e.k.map(lambda k: par[k].get('uf'))
area_de={}
for t in TEMAS: area_de[t[0]]=t[1]
estados={}
fm=fav[~fav['Natureza Jurídica'].fillna('').str.contains('Economia Mista|Federal|Empresa Pública') & fav['Município Favorecido'].fillna('').ne('')]
for uf,x in e[e.uf.notna()].groupby('uf'):
    tot_uf=x.emp.sum()
    porg={g:round(x[x.g==g].emp.sum()) for g,_,_ in GRUPOS}
    top=x.groupby('k').emp.sum().sort_values(ascending=False).head(6)
    mun=fm[fm['UF Favorecido']==uf].groupby('Município Favorecido').valor.sum().sort_values(ascending=False).head(6)
    areas={t[0]:round(x[x['t_'+t[0]]].emp.sum()) for t in TEMAS}
    fora=x[x.uf_autor.notna() & (x.uf_autor!=uf)].emp.sum()
    bancada={g:int(x[(x.g==g)&(x.uf_autor==uf)].k.nunique()) for g,_,_ in GRUPOS}
    estados[uf]={'nome':NOMES[uf],'pop':POP[uf],'total':round(tot_uf),'pago':round(x.pago.sum()),
      'pix':round(x[x.pix].emp.sum()),'grupos':porg,'bancada':bancada,'fora':round(fora),
      'top':[dict(nome_par(k),v=round(v)) for k,v in top.items()],
      'munis':[[titulo(m_),round(v)] for m_,v in mun.items()],'areas':areas}

# ------------------------------------------------ distribuição por município
# Pagamentos a prefeituras, fundos municipais e entidades locais, ligados ao código do IBGE pelo nome e pela UF.
UFCOD={'11':'RO','12':'AC','13':'AM','14':'RR','15':'PA','16':'AP','17':'TO','21':'MA','22':'PI','23':'CE','24':'RN','25':'PB','26':'PE','27':'AL','28':'SE','29':'BA',
 '31':'MG','32':'ES','33':'RJ','35':'SP','41':'PR','42':'SC','43':'RS','50':'MS','51':'MT','52':'GO','53':'DF'}
def chave_mun(nome,uf): return re.sub(r'[^A-Z]','',n(nome).replace("D'",'D').replace('-',''))+'|'+uf
topo=json.load(open(os.path.join(OBS,'municipios.topo.json')))
obj=list(topo['objects'].values())[0]['geometries']
cod_por_nome={chave_mun(g['properties']['name'],UFCOD[g['properties']['id'][:2]]):g['properties']['id'] for g in obj}
NAT_MUN=r'Município|Fundo Público da Administração Direta Municipal|Associação Privada|Fundação Privada|Organização Religiosa|Cooperativa|Organização Social|Sociedade Empresária|Empresário|Entidade Sindical|Serviço Social'
fmun=fav[fav['Código da Emenda'].str[:4].ge('2023') & fav['Natureza Jurídica'].fillna('').str.contains(NAT_MUN) & ~fav['Natureza Jurídica'].fillna('').str.contains('Estadual|Federal')].copy()
fmun['cod']=[cod_por_nome.get(chave_mun(m,u)) for m,u in zip(fmun['Município Favorecido'].fillna(''),fmun['UF Favorecido'].fillna(''))]
cob_mun=fmun[fmun.cod.notna()].valor.sum()/fmun.valor.sum() if len(fmun) else 0
fmun=fmun[fmun.cod.notna()]
fmun['pixm']=fmun['Tipo de Emenda'].str.contains('Especiais')
popm={}
try: popm=json.load(open(os.path.join(OBS,'populacao-municipios.json')))['pop']
except Exception: pass
ORD=[g for g,_,_ in GRUPOS]
municipios={}
fmun['ano']=fmun['Código da Emenda'].str[:4]
for cod,x in fmun.groupby('cod'):
    top=x.groupby('k').valor.sum().sort_values(ascending=False).head(3)
    anos={}
    for an,y in x.groupby('ano'):
        gv=y.groupby('g').valor.sum()
        anos[an]=[round(y.valor.sum()),*[round(gv.get(g,0)) for g in ORD],round(y[y.pixm].valor.sum())]
    municipios[cod]={'p':popm.get(cod,0),'t':[[k,round(v)] for k,v in top.items()],'a':anos}
json.dump({'gerado':pd.Timestamp.now().isoformat()[:19],'campos':['total',*ORD,'pix'],'anos':sorted(fmun['ano'].unique().tolist()),'cobertura_nomes':round(cob_mun,4),
  'total_pago':round(fav[fav['Código da Emenda'].str[:4].ge('2023')].valor.sum()),'total_mapa':round(fmun.valor.sum()),
  'tem_pop':bool(popm),'m':municipios},open(os.path.join(os.path.dirname(SAIDA),'emendas-municipios.json'),'w'),ensure_ascii=False,separators=(',',':'))
print('municípios',len(municipios),'ligação por nome',round(cob_mun,3),'pop',len(popm))
saida={'gerado':pd.Timestamp.now().isoformat()[:19],'fonte':'Portal da Transparência, emendas parlamentares','periodo':'2023 a 2026 (2026 parcial)',
  'grupos':gr,'ordem':[g for g,_,_ in GRUPOS],'perfil':perfil,'temas':temas,'parl':parl,
  'cobertura':{'total':round(tot),'sem_vinculo':round(semv)},'estados':estados,'sem_uf':round(semuf)}
json.dump(saida,open(SAIDA,'w'),ensure_ascii=False,separators=(',',':'))
print('parl',len(parl),'cobertura',round(1-semv/tot,3),{g:v['n'] for g,v in gr.items()})
for t in temas: print(t['id'],{g:round(v/1e6,1) for g,v in t['total'].items()},{g:round(v/1e3) for g,v in t['media'].items()})
