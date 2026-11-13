import json, collections, numpy as np, sys
R='/home/claude/exterminadores-do-futuro/dados/'
I=json.load(open(R+'indice.json'))['p']
vs=[x for a in (2023,2024,2025,2026) for x in json.load(open(R+f'votacoes-{a}.json'))['itens']]
def ajustar(casa, dims=2, iters=3000, seed=0):
    vv=[v for v in vs if v['k']==casa]
    rows=[]; leg={}; cols=[]
    for v in vv:
        s=v['v'].get('S',[]); n=v['v'].get('N',[])
        tot=len(s)+len(n)
        if tot<10 or min(len(s),len(n))/tot<0.025: continue  # votações quase unânimes não informam
        j=len(cols); cols.append(v['id'])
        for op,ids in (('S',s),('N',n)):
            for i in ids:
                k=casa+str(i); leg.setdefault(k,len(leg)); rows.append((leg[k],j,1.0 if op=='S' else 0.0))
    cont=collections.Counter(r[0] for r in rows)
    ok={i for i,c in cont.items() if c>=25}
    rows=[r for r in rows if r[0] in ok]
    inv={i:k for k,i in leg.items()}
    li=np.array([r[0] for r in rows]); vj=np.array([r[1] for r in rows]); y=np.array([r[2] for r in rows])
    rng=np.random.default_rng(seed); L=len(leg); J=len(cols)
    # início: PL à direita, PT/PSOL à esquerda, para fixar a orientação
    x=rng.normal(0,0.1,(L,dims))
    for k,i in leg.items():
        s=(I.get(k) or {}).get('s','')
        if s in('PL','NOVO','Novo'): x[i,0]=1
        if s in('PT','PSOL','PCdoB'): x[i,0]=-1
    a=np.zeros(J); b=rng.normal(0,0.1,(J,dims))
    lr=0.05; m=[np.zeros_like(p) for p in (x,a,b)]; s2=[np.zeros_like(p) for p in (x,a,b)]
    for t in range(1,iters+1):
        z=a[vj]+np.sum(b[vj]*x[li],1); p=1/(1+np.exp(-z)); g=p-y
        gx=np.zeros_like(x); np.add.at(gx,li,g[:,None]*b[vj]); gx+=0.5*x
        ga=np.bincount(vj,g,J)+0.01*a
        gb=np.zeros_like(b); np.add.at(gb,vj,g[:,None]*x[li]); gb+=0.1*b
        for q,(par,gr) in enumerate(((x,gx),(a,ga),(b,gb))):
            m[q]=0.9*m[q]+0.1*gr; s2[q]=0.999*s2[q]+0.001*gr*gr
            par-= lr*(m[q]/(1-0.9**t))/(np.sqrt(s2[q]/(1-0.999**t))+1e-8)
    acc=np.mean(((a[vj]+np.sum(b[vj]*x[li],1))>0)==(y==1))
    # orientação e escala: dimensão 1 com o PL à direita; 2,5% e 97,5% viram -1 e 1
    out={}
    X=x.copy()
    pl=[leg[k] for k in leg if (I.get(k) or {}).get('s')=='PL' and leg[k] in ok]; pt=[leg[k] for k in leg if (I.get(k) or {}).get('s')=='PT' and leg[k] in ok]
    for d in range(dims):
        if d==0 and X[pl,0].mean()<X[pt,0].mean(): X[:,0]*=-1
        idx=list(ok); lo,hi=np.percentile(X[idx,d],[2.5,97.5]); X[:,d]=(X[:,d]-(lo+hi)/2)/((hi-lo)/2)
    for i in ok: out[inv[i]]=[round(float(v),3) for v in X[i]]+[cont[i]]
    return out, len(cols), acc
res={}
for casa in 'CS':
    o,J,acc=ajustar(casa); res[casa]={'votacoes':J,'acerto':round(float(acc),3),'p':o}
    print(casa,'votações',J,'parlamentares',len(o),'acerto',round(acc,3), file=sys.stderr)
json.dump(res,open('/tmp/claude-0/-home-claude/681ce9dc-26ac-5d0f-9d1c-06587a7ce88b/scratchpad/ip/pos.json','w'))
