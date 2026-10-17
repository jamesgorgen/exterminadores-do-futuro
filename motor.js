// Motor de busca do Monitor Legislativo.
// Consulta as APIs de dados abertos da Câmara e do Senado, filtra por partido
// e classifica cada proposição nos temas da taxonomia pela ementa.
// Funciona no navegador (window.Motor) e no Node (module.exports) para testes.

(function (raiz) {
  'use strict';

  // ---------------------------------------------------------------- partidos
  // camara: siglas aceitas pela API da Câmara no parâmetro siglaPartidoAutor
  // senado: como a sigla aparece no texto de autoria do Senado
  // antecessoras: siglas anteriores do mesmo partido (opcionais na busca)
  const PARTIDOS = [
    { id: 'PL', nome: 'PL', camara: ['PL'], senado: ['PL'], antecessoras: ['PR'] },
    { id: 'NOVO', nome: 'Novo', camara: ['NOVO'], senado: ['NOVO'], antecessoras: [] },
    { id: 'PP', nome: 'PP', camara: ['PP'], senado: ['PP', 'PROGRESSISTAS'], antecessoras: ['PPB'] },
    { id: 'UNIAO', nome: 'União Brasil', camara: ['UNIÃO'], senado: ['UNIÃO', 'UNIAO', 'UNIÃO BRASIL'], antecessoras: ['DEM', 'PSL'] },
    { id: 'PODE', nome: 'Podemos', camara: ['PODE'], senado: ['PODEMOS', 'PODE'], antecessoras: ['PTN'] },
    { id: 'REPUBLICANOS', nome: 'Republicanos', camara: ['REPUBLICANOS'], senado: ['REPUBLICANOS'], antecessoras: [] },
    { id: 'PRB', nome: 'PRB', camara: ['PRB'], senado: ['PRB'], antecessoras: [] }
  ];

  const TIPOS = ['PL', 'PLP', 'PEC', 'PDL'];
  const SIGLAS_SO_DEPUTADOS = new Set(['UNIÃO']);
  // Último ano em que cada sigla antiga existiu. Fora disso não há o que buscar.
  const SIGLA_ATE = { PR: 2019, PPB: 2003, DEM: 2022, PSL: 2022, PTN: 2017, PRB: 2019 };

  const API_CAMARA = 'https://dadosabertos.camara.leg.br/api/v2/proposicoes';
  const API_SENADO = 'https://legis.senado.leg.br/dadosabertos/processo';

  // ---------------------------------------------------------------- texto
  function nfc(s) { return (s || '').normalize('NFC'); }

  // Minúsculas, sem acento, hífen vira espaço. Preserva o comprimento do texto em NFC,
  // o que permite marcar os trechos encontrados na ementa original.
  function normalizar(s) {
    const t = nfc(s);
    let out = '';
    for (const ch of t) {
      const base = ch.normalize('NFD').replace(/[̀-ͯ]/g, '');
      let c = (base.length === 1 ? base : ch).toLowerCase();
      if (c.length !== ch.length) c = ch; // segurança: mantém o comprimento
      if (c === '-' || c === '–' || c === '—') c = ' ';
      out += c;
    }
    return out;
  }

  function escapar(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  // Sigla: tem maiúscula e nenhuma minúscula ("IA", "SUS", "5G", "LGBTQIA+", "BR-319").
  function ehSigla(termo) {
    return /[A-Z]/.test(termo) && !/[a-zà-ÿ]/.test(termo) && termo.length <= 12;
  }

  // Termo iniciado por "=" só vale como palavra exata, sem variações no fim ("=fome" não encontra "fomento").
  function compilarTermo(bruto) {
    const exato = bruto.startsWith('=');
    const termo = exato ? bruto.slice(1) : bruto;
    if (ehSigla(termo)) {
      const corpo = escapar(nfc(termo)).replace(/\s+/g, '\\s+');
      return { termo, sigla: true, curto: termo.replace(/[^A-Z]/g, '').length <= 3,
        re: new RegExp('(?<![A-Za-zÀ-ÿ0-9])' + corpo + '(?![A-Za-zÀ-ÿ0-9])', 'g') };
    }
    const n = normalizar(termo).trim();
    const corpo = escapar(n).replace(/\s+/g, '\\s+');
    // Aceita até três letras adicionais no fim (plural, gênero, derivações curtas).
    return { termo, sigla: false,
      re: new RegExp('(?<![a-z0-9])' + corpo + (exato ? '' : '[a-z]{0,3}') + '(?![a-z0-9])', 'g') };
  }

  function compilarTaxonomia(tax) {
    return {
      cadernos: tax.cadernos,
      temas: tax.temas.map(t => ({
        ...t,
        _termos: t.termos.map(compilarTermo),
        _excluir: (t.excluir || []).map(compilarTermo)
      })),
      _homenagens: (tax.homenagens || []).map(compilarTermo)
    };
  }

  function quaseTudoMaiusculo(s) {
    const letras = s.replace(/[^A-Za-zÀ-ÿ]/g, '');
    if (letras.length < 20) return false;
    const mai = letras.replace(/[^A-ZÀ-Þ]/g, '').length;
    return mai / letras.length > 0.8;
  }

  function procurar(termoC, original, normal, emCaixaAlta) {
    if (termoC.sigla && termoC.curto && emCaixaAlta) return [];
    const alvo = termoC.sigla ? original : normal;
    const achados = [];
    termoC.re.lastIndex = 0;
    let m;
    while ((m = termoC.re.exec(alvo)) !== null) {
      achados.push([m.index, m.index + m[0].length]);
      if (m[0].length === 0) termoC.re.lastIndex++;
    }
    return achados;
  }

  // Devolve [{id, termos:[...], trechos:[[ini,fim],...]}] para a ementa.
  function classificar(ementa, taxC) {
    const original = nfc(ementa);
    const normal = normalizar(original);
    const caixaAlta = quaseTudoMaiusculo(original);
    const resultado = [];
    for (const tema of taxC.temas) {
      const termos = new Set();
      const trechos = [];
      for (const tc of tema._termos) {
        const a = procurar(tc, original, normal, caixaAlta);
        if (a.length) { termos.add(tc.termo); trechos.push(...a); }
      }
      if (!termos.size) continue;
      const excluido = tema._excluir.some(tc => procurar(tc, original, normal, caixaAlta).length);
      if (excluido) continue;
      resultado.push({ id: tema.id, termos: [...termos], trechos });
    }
    return resultado;
  }

  function ehHomenagem(ementa, taxC) {
    const original = nfc(ementa);
    const normal = normalizar(original);
    return taxC._homenagens.some(tc => procurar(tc, original, normal, false).length);
  }

  // ---------------------------------------------------------------- partidos no Senado
  // "Senador Fulano (PL/SP), Senadora Beltrana (PT/BA)" -> ["PL", "PT"]
  function partidosDaAutoria(autoria) {
    const out = [];
    const re = /\(([^()\/]+)\/[A-Z]{2}\)/g;
    let m;
    while ((m = re.exec(autoria || '')) !== null) out.push(nfc(m[1]).trim().toUpperCase());
    return out;
  }

  // Monta o dicionário sigla encontrada -> id do partido monitorado.
  function mapaSiglas(idsPartidos, incluirAntecessoras, casa) {
    const mapa = new Map();
    for (const p of PARTIDOS) {
      if (!idsPartidos.includes(p.id)) continue;
      const siglas = casa === 'camara' ? p.camara : p.senado;
      siglas.forEach(s => mapa.set(s.toUpperCase(), p.id));
      if (incluirAntecessoras) p.antecessoras.forEach(s => mapa.set(s.toUpperCase(), p.id));
    }
    return mapa;
  }

  // ---------------------------------------------------------------- datas
  function iso(d) { return d.toISOString().slice(0, 10); }
  function janelasMensais(inicio, fim) {
    const out = [];
    let a = new Date(inicio + 'T00:00:00Z');
    const f = new Date(fim + 'T00:00:00Z');
    while (a <= f) {
      const b = new Date(Date.UTC(a.getUTCFullYear(), a.getUTCMonth() + 1, 0));
      out.push([iso(a), iso(b < f ? b : f)]);
      a = new Date(Date.UTC(a.getUTCFullYear(), a.getUTCMonth() + 1, 1));
    }
    return out;
  }
  function janelasQuinzenais(inicio, fim) {
    const out = [];
    for (const [a, b] of janelasMensais(inicio, fim)) {
      const meio = a.slice(0, 8) + '15';
      if (meio > a && meio < b) {
        out.push([a, meio]);
        out.push([a.slice(0, 8) + '16', b]);
      } else out.push([a, b]);
    }
    return out;
  }
  function janelasAnuais(inicio, fim) {
    const out = [];
    let a = new Date(inicio + 'T00:00:00Z');
    const f = new Date(fim + 'T00:00:00Z');
    while (a <= f) {
      const b = new Date(Date.UTC(a.getUTCFullYear(), 11, 31));
      out.push([iso(a), iso(b < f ? b : f)]);
      a = new Date(Date.UTC(a.getUTCFullYear() + 1, 0, 1));
    }
    return out;
  }

  // ---------------------------------------------------------------- execução em paralelo
  async function emParalelo(tarefas, limite, aoConcluir) {
    const resultados = new Array(tarefas.length);
    let proxima = 0;
    async function trabalhador() {
      while (proxima < tarefas.length) {
        const i = proxima++;
        resultados[i] = await tarefas[i]();
        if (aoConcluir) aoConcluir();
      }
    }
    await Promise.all(Array.from({ length: Math.min(limite, tarefas.length) }, trabalhador));
    return resultados;
  }

  // ---------------------------------------------------------------- Câmara
  // A API da Câmara não conclui buscas por partido com intervalo de datas (dataApresentacaoInicio/Fim).
  // Por isso a consulta é feita por ano, e o recorte de datas é aplicado depois, na página.
  function urlCamara(sigla, tipos, ano, pagina) {
    const p = new URLSearchParams({
      siglaPartidoAutor: sigla, siglaTipo: tipos.join(','), ano: String(ano),
      itens: '100', pagina: String(pagina), ordem: 'ASC', ordenarPor: 'id'
    });
    return API_CAMARA + '?' + p.toString();
  }

  function ultimaPagina(json) {
    const l = (json.links || []).find(x => x.rel === 'last');
    if (!l) return 1;
    const m = /[?&]pagina=(\d+)/.exec(l.href);
    return m ? parseInt(m[1], 10) : 1;
  }

  // Legislaturas da Câmara que cruzam o período (56 começou em 2019).
  function legislaturas(inicio, fim) {
    const out = [];
    for (let leg = 50; leg <= 60; leg++) {
      const ini = `${1995 + (leg - 50) * 4}-02-01`;
      const fimLeg = `${1999 + (leg - 50) * 4}-01-31`;
      if (ini <= fim && fimLeg >= inicio) out.push(leg);
    }
    return out;
  }

  function urlCamaraPorDeputados(ids, tipos, ano, pagina) {
    const p = new URLSearchParams({
      idDeputadoAutor: ids.join(','), siglaTipo: tipos.join(','), ano: String(ano),
      itens: '100', pagina: String(pagina), ordem: 'ASC', ordenarPor: 'id'
    });
    return API_CAMARA + '?' + p.toString();
  }

  async function buscarCamara(opc, buscarJson, progresso) {
    const mapa = mapaSiglas(opc.partidos, opc.antecessoras, 'camara');
    const anos = [];
    for (let a = parseInt(opc.inicio.slice(0, 4), 10); a <= parseInt(opc.fim.slice(0, 4), 10); a++) anos.push(a);
    const itens = new Map();
    const avisos = [];
    // Fica só com o que foi apresentado dentro do período. Se a data registrada não bate
    // com o ano do projeto (há registros antigos inconsistentes), vale o ano.
    const noPeriodo = d => {
      const data = (d.dataApresentacao || '').slice(0, 10);
      if (data && data.slice(0, 4) === String(d.ano)) return data >= opc.inicio && data <= opc.fim;
      return true;
    };
    const guardar = (json, idPartido, sigla, viaDeputados) => {
      for (const d of json.dados || []) {
        if (!noPeriodo(d)) continue;
        const chave = `${d.siglaTipo} ${d.numero}/${d.ano}`;
        let it = itens.get(chave);
        if (!it) {
          it = { chave, casa: ['Câmara'], sigla: d.siglaTipo, numero: d.numero, ano: d.ano,
            data: (d.dataApresentacao || '').slice(0, 10), ementa: nfc(d.ementa || ''),
            partidos: new Set(), siglasEncontradas: new Set(), idCamara: d.id,
            link: 'https://www.camara.leg.br/propostas-legislativas/' + d.id, autores: null };
          itens.set(chave, it);
        }
        it.partidos.add(idPartido);
        it.siglasEncontradas.add(sigla);
        if (viaDeputados) (it.viaDeputados = it.viaDeputados || new Set()).add(sigla);
      }
    };

    let paginasPerdidas = 0;
    // Busca todas as páginas de uma consulta paginada da Câmara.
    async function todasPaginas(montarUrl, guardarPagina) {
      const primeira = await buscarJson(montarUrl(1));
      guardarPagina(primeira);
      const total = ultimaPagina(primeira);
      if (total > 1) {
        progresso.adicionar(total - 1);
        const resto = [];
        for (let p = 2; p <= total; p++) resto.push(p);
        await emParalelo(resto.map(p => async () => {
          try { guardarPagina(await buscarJson(montarUrl(p))); }
          catch (e) { paginasPerdidas++; }
        }), 3, () => progresso.avancar());
      }
    }

    // Caminho alternativo: lista os deputados do partido e busca pela autoria de cada um.
    // Usado quando a API recusa o filtro por sigla (acontece com UNIÃO).
    async function viaDeputados(sigla, idPartido) {
      const ids = new Set();
      for (const leg of legislaturas(opc.inicio, opc.fim)) {
        const p = new URLSearchParams({ siglaPartido: sigla, idLegislatura: String(leg), itens: '100' });
        try {
          const j = await buscarJson('https://dadosabertos.camara.leg.br/api/v2/deputados?' + p.toString());
          (j.dados || []).forEach(d => ids.add(d.id));
        } catch (e) { /* legislatura sem dados */ }
      }
      if (!ids.size) { avisos.push({ tipo: 'falha', casa: 'Câmara', sigla, ano: anos.join(', ') }); return; }
      const lista = [...ids];
      const lotes = [];
      for (let i = 0; i < lista.length; i += 20) lotes.push(lista.slice(i, i + 20));
      const tarefas = [];
      for (const lote of lotes) for (const ano of anos) tarefas.push({ lote, ano });
      progresso.adicionar(tarefas.length);
      await emParalelo(tarefas.map(t => async () => {
        try {
          await todasPaginas(pg => urlCamaraPorDeputados(t.lote, opc.tipos, t.ano, pg), j => guardar(j, idPartido, sigla, true));
        } catch (e) { avisos.push({ tipo: 'falha', casa: 'Câmara', sigla, ano: t.ano }); }
      }), 3, () => progresso.avancar());
      avisos.push({ tipo: 'metodo', sigla, deputados: lista.length });
    }

    progresso.adicionar(mapa.size);
    await emParalelo([...mapa].map(([sigla, idPartido]) => async () => {
      // A API da Câmara não responde ao filtro por UNIÃO (erro após longa espera).
      // Para essa sigla, vai direto pela lista de deputados.
      if (SIGLAS_SO_DEPUTADOS.has(sigla)) { await viaDeputados(sigla, idPartido); return; }
      const anosSigla = SIGLA_ATE[sigla] ? anos.filter(a => a <= SIGLA_ATE[sigla]) : anos;
      if (!anosSigla.length) return; // sigla que já não existia no período
      let funciona = true;
      try {
        await todasPaginas(pg => urlCamara(sigla, opc.tipos, anosSigla[anosSigla.length - 1], pg), j => guardar(j, idPartido, sigla, false));
      } catch (e) { funciona = false; }
      // Falha pontual da API: registra para a opção "Buscar de novo o que faltou" e segue.
      if (!funciona) avisos.push({ tipo: 'falha', casa: 'Câmara', sigla, ano: anosSigla[anosSigla.length - 1] });
      const demais = anosSigla.slice(0, -1);
      progresso.adicionar(demais.length);
      await emParalelo(demais.map(ano => async () => {
        try {
          await todasPaginas(pg => urlCamara(sigla, opc.tipos, ano, pg), j => guardar(j, idPartido, sigla, false));
        } catch (e) { avisos.push({ tipo: 'falha', casa: 'Câmara', sigla, ano }); }
      }), 2, () => progresso.avancar());
    }), opc.paralelo || 4, () => progresso.avancar());
    if (paginasPerdidas) avisos.push({ tipo: 'falha', casa: 'Câmara', paginas: paginasPerdidas });
    return { itens: [...itens.values()], avisos };
  }

  async function autoresCamara(item, buscarJson) {
    const j = await buscarJson(API_CAMARA + '/' + item.idCamara + '/autores');
    return (j.dados || []).map(a => a.nome).filter(Boolean);
  }

  // ---------------------------------------------------------------- Senado
  function urlSenado(tipos, ini, fim) {
    const p = new URLSearchParams();
    tipos.forEach(t => p.append('sigla', t));
    p.set('dataInicioApresentacao', ini);
    p.set('dataFimApresentacao', fim);
    return API_SENADO + '?' + p.toString();
  }

  async function buscarSenado(opc, buscarJson, progresso) {
    const mapa = mapaSiglas(opc.partidos, opc.antecessoras, 'senado');
    const janelas = janelasQuinzenais(opc.inicio, opc.fim);
    progresso.adicionar(janelas.length);
    const itens = new Map();
    const avisos = [];
    await emParalelo(janelas.map(([ini, fim]) => async () => {
      let lista;
      try { lista = await buscarJson(urlSenado(opc.tipos, ini, fim)); }
      catch (e) { avisos.push({ tipo: 'falha', casa: 'Senado', ini, fim }); return; }
      for (const d of Array.isArray(lista) ? lista : []) {
        if (d.objetivo === 'Revisora') continue; // projeto vindo da Câmara
        const siglas = partidosDaAutoria(d.autoria);
        const ids = new Set();
        const encontradas = new Set();
        siglas.forEach(s => { if (mapa.has(s)) { ids.add(mapa.get(s)); encontradas.add(s); } });
        if (!ids.size) continue;
        const m = /^(\S+)\s+(\d+)\/(\d{4})/.exec(d.identificacao || '');
        const chave = m ? `${m[1]} ${parseInt(m[2], 10)}/${m[3]}` : d.identificacao;
        itens.set(chave, { chave, casa: ['Senado'], sigla: m ? m[1] : '', numero: m ? parseInt(m[2], 10) : '',
          ano: m ? parseInt(m[3], 10) : '', data: d.dataApresentacao || '', ementa: nfc(d.ementa || ''),
          partidos: ids, siglasEncontradas: encontradas, autores: [d.autoria],
          link: d.codigoMateria ? 'https://www25.senado.leg.br/web/atividade/materias/-/materia/' + d.codigoMateria : '',
          situacao: d.situacaoAtual || '', tramitando: d.tramitando || '', urlDocumento: d.urlDocumento || '' });
      }
    }), opc.paralelo || 3, () => progresso.avancar());
    return { itens: [...itens.values()], avisos };
  }

  // ---------------------------------------------------------------- busca completa
  async function buscar(opc, taxC, buscarJson, aoProgredir) {
    let total = 0, feito = 0;
    const progresso = {
      adicionar(n) { total += n; aoProgredir && aoProgredir(feito, total); },
      avancar() { feito++; aoProgredir && aoProgredir(feito, total); }
    };
    const tarefas = [];
    if (opc.casas.includes('camara')) tarefas.push(buscarCamara(opc, buscarJson, progresso));
    if (opc.casas.includes('senado')) tarefas.push(buscarSenado(opc, buscarJson, progresso));
    const partes = await Promise.all(tarefas);
    const avisos = partes.flatMap(p => p.avisos);

    // Junta as duas Casas: desde 2019 o projeto mantém o mesmo número nas duas.
    const porChave = new Map();
    for (const it of partes.flatMap(p => p.itens)) {
      const ja = porChave.get(it.chave);
      if (!ja) { porChave.set(it.chave, it); continue; }
      ja.casa = [...new Set([...ja.casa, ...it.casa])];
      it.partidos.forEach(p => ja.partidos.add(p));
      it.siglasEncontradas.forEach(s => ja.siglasEncontradas.add(s));
      if (!ja.autores && it.autores) ja.autores = it.autores;
      if (!ja.situacao && it.situacao) ja.situacao = it.situacao;
      if (!ja.urlDocumento && it.urlDocumento) ja.urlDocumento = it.urlDocumento;
    }

    const saida = [];
    for (const it of porChave.values()) {
      it.homenagem = ehHomenagem(it.ementa, taxC);
      it.temas = classificar(it.ementa, taxC);
      it.partidos = [...it.partidos];
      it.siglasEncontradas = [...it.siglasEncontradas];
      it.viaDeputados = it.viaDeputados ? [...it.viaDeputados] : [];
      saida.push(it);
    }
    saida.sort((a, b) => (b.data || '').localeCompare(a.data || ''));
    return { itens: saida, avisos };
  }

  const Motor = { PARTIDOS, TIPOS, normalizar, compilarTaxonomia, classificar, ehHomenagem,
    partidosDaAutoria, mapaSiglas, janelasMensais, janelasQuinzenais, janelasAnuais, legislaturas, urlCamara, urlSenado,
    ultimaPagina, buscar, autoresCamara, emParalelo };

  if (typeof module !== 'undefined' && module.exports) module.exports = Motor;
  else raiz.Motor = Motor;
})(typeof window !== 'undefined' ? window : globalThis);
