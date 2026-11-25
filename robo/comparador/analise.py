"""Análise por IA das diferenças entre duas versões (a IA recebe só as diferenças, nunca os textos inteiros).

Devolve a conclusão (título), o resumo, o balanço e, para cada artigo com mudança, a classificação
(mérito ou redação), até duas etiquetas de efeito e uma nota curta. O texto literal continua no quadro;
a análise é um ponto de partida e não substitui a revisão humana.
"""
import json, os, re, time, urllib.request

MODELO = os.environ.get('COMPARADOR_MODELO', 'claude-sonnet-5-5')
LIMITE_ENTRADA = 160_000      # caracteres das diferenças enviadas à IA
CORTE_TRECHO = 900            # caracteres por dispositivo

INSTRUCOES = """Você analisa as diferenças entre duas versões de um texto legislativo brasileiro (projeto, substitutivo, emenda, parecer ou lei) para uma plataforma de acompanhamento do Congresso.

Regras:
- Escreva em português do Brasil, em registro claro e sóbrio: nem coloquial, nem burocrático. Frases curtas.
- Use só o que está nas diferenças recebidas. Não invente efeitos, números, prazos nem intenções. Não especule sobre motivações políticas.
- Seja factual e equilibrado: descreva o que a regra passa a dizer e o efeito prático direto (quem ganha ou perde poder, prazo, obrigação, garantia). Não use adjetivos de juízo ("grave", "polêmico", "positivo").
- Cite os artigos pelo rótulo da versão B (ou da versão A, se o artigo foi suprimido).
- As trocas de nome repetidas listadas no início já foram descontadas; mencione-as só no balanço, se forem relevantes.
- "merito" = muda o conteúdo da regra (quem, o quê, quando, quanto, como). "redacao" = muda só palavras, ordem, numeração ou pontuação, sem efeito prático.

Responda SOMENTE com um objeto JSON válido, sem texto antes ou depois, neste formato:
{
 "conclusao": "a principal conclusão em uma frase de até 110 caracteres, que sirva de título",
 "resumo": [ {"t": "título curto da mudança", "d": "duas ou três frases explicando a mudança", "ref": "Art. X"} ],
 "balanco": "um parágrafo de três a cinco frases com o sentido geral das mudanças, mencionando o que se manteve",
 "itens": { "Art. X": {"cls": "merito" ou "redacao", "efeito": ["até duas etiquetas curtas, de até 40 caracteres"], "nota": "uma a quatro frases sobre o que mudou neste artigo"} }
}
O resumo tem de 3 a 7 itens, em ordem de importância. Em "itens", inclua todos os artigos listados como alterados, novos, suprimidos ou reorganizados, usando exatamente o rótulo indicado entre colchetes."""

def _corta(s, n=CORTE_TRECHO):
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= n else s[:n] + ' […]'

def montar_entrada(meta, comp):
    linhas = [f"Proposição: {meta.get('proposicao') or 'não informada'}",
              f"Versão A: {meta['A']['nome']} ({meta['A'].get('autor') or 'autor não informado'}, {meta['A'].get('data') or 'sem data'})",
              f"Versão B: {meta['B']['nome']} ({meta['B'].get('autor') or 'autor não informado'}, {meta['B'].get('data') or 'sem data'})",
              f"Artigos: {comp['artigosA']} na versão A, {comp['artigosB']} na versão B.", '']
    if comp['renomeacoes']:
        linhas.append('Trocas de nome repetidas em todo o texto (já descontadas):')
        for r in comp['renomeacoes']:
            linhas.append(f"- \"{r['de']}\" → \"{r['para']}\" ({r['vezes']} vezes)")
        linhas.append('')
    iguais = []
    corpo = []
    for it in comp['itens']:
        chave = it['b'] or it['a']
        if it['cls'] == 'igual':
            iguais.append(chave); continue
        cab = f"### [{chave}]" + (f" (era {it['a']})" if it['a'] and it['b'] and it['a'] != it['b'] else '') + f" — {it['cls']}"
        bloco = [cab]
        if it['cls'] == 'reorganizado':
            bloco.append('- Só mudanças de posição ou de numeração dos dispositivos, sem alteração de texto.')
        for tipo, antes, depois in it['trechos']:
            if tipo == 'alterado':
                bloco.append(f"- ALTERADO. ANTES: {_corta(antes)} | DEPOIS: {_corta(depois)}")
            elif tipo == 'novo':
                bloco.append(f"- NOVO: {_corta(depois)}")
            else:
                bloco.append(f"- SUPRIMIDO: {_corta(antes)}")
        corpo.append('\n'.join(bloco))
    texto = '\n\n'.join(corpo)
    if len(texto) > LIMITE_ENTRADA:
        texto = texto[:LIMITE_ENTRADA] + '\n\n[As diferenças foram cortadas por tamanho. Analise só o que veio acima.]'
    linhas.append('Diferenças por artigo:')
    linhas.append(texto)
    if iguais:
        linhas.append('\nArtigos sem alteração: ' + ', '.join(iguais))
    return '\n'.join(linhas)

def analisar(meta, comp, chave_api=None):
    chave_api = chave_api or os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not chave_api:
        raise RuntimeError('sem ANTHROPIC_API_KEY')
    entrada = montar_entrada(meta, comp)
    ultimo = None
    for tentativa in range(3):
        corpo = {'model': MODELO, 'max_tokens': 16000, 'system': INSTRUCOES,
                 'messages': [{'role': 'user', 'content': entrada}]}
        req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=json.dumps(corpo).encode(),
                                     headers={'x-api-key': chave_api, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                j = json.load(r)
            txt = ''.join(b.get('text', '') for b in j.get('content', []) if b.get('type') == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            dados = json.loads(m.group(0))
            uso = j.get('usage', {})
            return validar(dados, comp), {'modelo': MODELO, 'entrada': uso.get('input_tokens'), 'saida': uso.get('output_tokens')}
        except Exception as e:
            ultimo = e
            time.sleep(10 * (tentativa + 1))
    raise RuntimeError(f'análise de IA falhou: {type(ultimo).__name__}: {str(ultimo)[:200]}')

def _txt(x, n):
    return re.sub(r'\s+', ' ', str(x or '')).strip()[:n]

def validar(d, comp):
    """Mantém só os campos esperados, com tamanhos limitados (o resultado é público)."""
    out = {'conclusao': _txt(d.get('conclusao'), 160), 'balanco': _txt(d.get('balanco'), 1500), 'resumo': [], 'itens': {}}
    for r in (d.get('resumo') or [])[:8]:
        if isinstance(r, dict) and r.get('t'):
            out['resumo'].append({'t': _txt(r.get('t'), 140), 'd': _txt(r.get('d'), 700), 'ref': _txt(r.get('ref'), 60)})
    validos = {it['b'] or it['a'] for it in comp['itens']}
    for k, v in (d.get('itens') or {}).items():
        k = _txt(k, 60).strip('[]')
        if k in validos and isinstance(v, dict):
            out['itens'][k] = {'cls': 'redacao' if v.get('cls') == 'redacao' else 'merito',
                               'efeito': [_txt(e, 40) for e in (v.get('efeito') or [])[:2] if e],
                               'nota': _txt(v.get('nota'), 900)}
    return out
