// Acompanhamento de parlamentares: lê nas APIs abertas da Câmara e do Senado a atividade legislativa registrada de
// cada deputado (dep:<id>) e senador (sen:<código>) acompanhado e devolve os eventos novos desde a última leitura.
//
// Câmara: proposições de autoria (projetos, requerimentos, emendas etc.), votos nominais (plenário e comissões),
//         discursos e mudança de partido ou de situação no mandato.
// Senado: proposições de autoria, relatorias designadas, votos nominais, pronunciamentos e mudança de partido.
// A Câmara não publica relatorias por deputado na API; elas aparecem nos dossiês, a partir da base diária do robô.

const CAM = 'https://dadosabertos.camara.leg.br/api/v2';
const SEN = 'https://legis.senado.leg.br/dadosabertos';
const UA = { 'user-agent': 'exterminadores.com.br (acompanhamento de parlamentares; contato@exterminadores.com.br)', accept: 'application/json' };
export const PARL = /^(dep:\d{1,9}|sen:\d{1,9})$/;
export const ehParl = k => /^(dep|sen):/.test(k);

const dia = (ms = Date.now()) => new Date(ms).toISOString().slice(0, 10);
const compacto = d => d.replace(/-/g, '');
const lista = x => (Array.isArray(x) ? x : x ? [x] : []);
const corta = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const dataBR = d => { const m = String(d || '').match(/(\d{4})-(\d{2})-(\d{2})/); return m ? `${m[3]}/${m[2]}` : ''; };
const rotProp = x => (+x.ano ? `${x.siglaTipo} ${x.numero}/${x.ano}` : `${x.siglaTipo} ${x.numero}`);
const VOTO = v => ({ 'Sim': 'Sim', 'Não': 'Não', 'Nao': 'Não', 'Abstenção': 'Abstenção', 'Obstrução': 'Obstrução', 'Artigo 17': 'Art. 17 (presidente)' }[v] || v || 'registrou presença');

// Contador de chamadas externas: a tarefa agendada para de ler parlamentares antes de passar do limite do Worker.
export function criarParl(conta) {
  const espera = ms => new Promise(r => setTimeout(r, ms));
  // A API da Câmara responde 429 quando recebe muitas chamadas seguidas: espera e tenta mais duas vezes.
  const get = async url => {
    for (let t = 0; ; t++) {
      conta.n++;
      const r = await fetch(url, { headers: UA });
      if (r.ok) return r.json();
      if (r.status === 429 && t < 2) { await espera(1500 * (t + 1)); continue; }
      throw new Error(`${r.status} ${url}`);
    }
  };

  // Votos nominais da Câmara, lidos uma vez por execução para todos os deputados acompanhados.
  // acomp/cam-votacoes.json guarda as votações já lidas (com votos ou já antigas), para não repetir.
  async function votosCamara(env, lerJ, gravarJ, desde) {
    const ke = 'acomp/cam-votacoes.json';
    const feitas = (await lerJ(env, ke)) || {};
    const porDep = new Map();
    const lst = (await get(`${CAM}/votacoes?dataInicio=${desde}&dataFim=${dia()}&itens=200&ordem=DESC&ordenarPor=dataHoraRegistro`)).dados || [];
    let lidas = 0;
    for (const v of lst) {
      // Até 60 votações novas por execução, com intervalo entre as chamadas; o resto fica para a hora seguinte.
      if (feitas[v.id] || conta.n > conta.max || lidas >= 60) continue;
      let votos;
      try { lidas++; votos = (await get(`${CAM}/votacoes/${v.id}/votos`)).dados || []; await espera(120); }
      catch (e) { console.log('votos da Câmara:', String(e).slice(0, 160)); break; }
      const reg = Date.parse(v.dataHoraRegistro || v.data) || Date.now();
      if (votos.length || Date.now() - reg > 3 * 3600e3) feitas[v.id] = v.data;
      // Sem a matéria na lista, o detalhe da votação diz qual proposição foi votada.
      let objeto = v.proposicaoObjeto;
      if (votos.length && !objeto) {
        try { const dt = (await get(`${CAM}/votacoes/${v.id}`)).dados || {}; const p = (dt.proposicoesAfetadas || [])[0] || (dt.objetosPossiveis || [])[0]; if (p) objeto = rotProp({ siglaTipo: p.siglaTipo, numero: p.numero, ano: p.ano }); } catch (_) {}
      }
      for (const x of votos) {
        const id = x.deputado_ && x.deputado_.id; if (!id) continue;
        porDep.set(String(id), [...(porDep.get(String(id)) || []), { id: v.id, voto: x.tipoVoto, texto: corta(objeto ? `${objeto}: ${v.descricao}` : v.descricao, 220), orgao: v.siglaOrgao, data: v.data }]);
      }
    }
    const limite = dia(Date.now() - 10 * 864e5);
    for (const [id, d] of Object.entries(feitas)) if (d < limite) delete feitas[id];
    await gravarJ(env, ke, feitas);
    return porDep;
  }

  // Atividade de um parlamentar desde a data indicada: lista de {id, tipo, texto, url, data} e o status atual.
  async function atividade(k, desde, votosCam) {
    const [casa, id] = k.split(':');
    const ev = [];
    if (casa === 'dep') {
      const [st, props, disc] = await Promise.all([
        get(`${CAM}/deputados/${id}`).then(j => j.dados),
        get(`${CAM}/proposicoes?idDeputadoAutor=${id}&dataApresentacaoInicio=${desde}&itens=100&ordem=DESC&ordenarPor=id`).then(j => j.dados || []),
        get(`${CAM}/deputados/${id}/discursos?dataInicio=${desde}&dataFim=${dia()}&ordenarPor=dataHoraInicio&ordem=DESC`).then(j => j.dados || [])]);
      for (const p of props) ev.push({ id: 'p' + p.id, tipo: 'autoria', texto: `Apresentou ${rotProp(p)}: ${corta(p.ementa, 200)}`, url: `https://www.camara.leg.br/propostas-legislativas/${p.id}`, data: '' });
      for (const d of disc) {
        // Sem sumário, usa o começo da transcrição, sem o cabeçalho "O SR. FULANO (PARTIDO - UF. ...) -".
        const fala = d.sumario || d.keywords || String(d.transcricao || '').replace(/^[^)]{0,200}\)\s*-\s*/, '');
        ev.push({ id: 'd' + d.dataHoraInicio + (d.tipoDiscurso || ''), tipo: 'discurso', texto: `Discursou (${corta(d.tipoDiscurso || (d.faseEvento && d.faseEvento.titulo) || 'pronunciamento', 40).toLowerCase()}) em ${dataBR(d.dataHoraInicio)}${fala ? `: ${corta(fala, 200)}` : ''}`, url: d.urlTexto || `https://www.camara.leg.br/deputados/${id}`, data: String(d.dataHoraInicio || '').slice(0, 10) });
      }
      for (const v of (votosCam && votosCam.get(id)) || []) ev.push({ id: 'v' + v.id, tipo: 'voto', texto: `Votou ${VOTO(v.voto)}${v.orgao && v.orgao !== 'PLEN' ? ` (${v.orgao})` : ' (Plenário)'}: ${v.texto}`, url: `https://www.camara.leg.br/deputados/${id}`, data: v.data });
      const u = (st && st.ultimoStatus) || {};
      return { nome: u.nomeEleitoral || u.nome || k, eventos: ev, status: { partido: u.siglaPartido || '', situacao: u.situacao || '' }, url: `https://www.camara.leg.br/deputados/${id}` };
    }
    const [det, props, rel, vot, disc] = await Promise.all([
      get(`${SEN}/senador/${id}`).then(j => j.DetalheParlamentar.Parlamentar.IdentificacaoParlamentar),
      get(`${SEN}/processo?codigoParlamentarAutor=${id}&dataInicioApresentacao=${desde}`).then(lista),
      get(`${SEN}/processo/relatoria?codigoParlamentar=${id}&dataInicio=${desde}`).then(lista),
      get(`${SEN}/votacao?codigoParlamentar=${id}&dataInicio=${desde}&dataFim=${dia()}`).then(lista),
      get(`${SEN}/senador/${id}/discursos?dataInicio=${compacto(desde)}&dataFim=${compacto(dia())}`).then(j => lista(((j.DiscursosParlamentar.Parlamentar || {}).Pronunciamentos || {}).Pronunciamento))]);
    const urlMat = c => c ? `https://www25.senado.leg.br/web/atividade/materias/-/materia/${c}` : `https://www25.senado.leg.br/web/senadores/senador/-/perfil/${id}`;
    for (const p of props) ev.push({ id: 'p' + p.id, tipo: 'autoria', texto: `Apresentou ${p.identificacao}: ${corta(p.ementa, 200)}`, url: urlMat(p.codigoMateria), data: p.dataApresentacao || '' });
    for (const r of rel) ev.push({ id: 'r' + r.id, tipo: 'relatoria', texto: `Designado ${String(r.descricaoTipoRelator || 'relator').toLowerCase()} de ${r.identificacaoProcesso}${r.siglaColegiado ? ` na ${r.siglaColegiado}` : ''}: ${corta(r.ementaProcesso, 160)}`, url: urlMat(r.codigoMateria), data: String(r.dataDesignacao || '').slice(0, 10) });
    for (const v of vot) {
      const meu = lista(v.votos).find(x => String(x.codigoParlamentar) === id);
      ev.push({ id: 'v' + v.codigoSessaoVotacao, tipo: 'voto', texto: `Votou ${VOTO(meu && meu.siglaVotoParlamentar)} (Plenário): ${v.identificacao || ''}${v.descricaoVotacao ? ` — ${corta(v.descricaoVotacao, 180)}` : ''}`, url: urlMat(v.codigoMateria), data: v.dataSessao || '' });
    }
    for (const d of disc) ev.push({ id: 'd' + d.CodigoPronunciamento, tipo: 'discurso', texto: `Discursou (${corta((d.TipoUsoPalavra && d.TipoUsoPalavra.Descricao) || 'pronunciamento', 40).toLowerCase()}) em ${dataBR(d.DataPronunciamento)}${d.TextoResumo ? `: ${corta(d.TextoResumo, 200)}` : ''}`, url: d.UrlTexto || urlMat(), data: d.DataPronunciamento || '' });
    return { nome: det.NomeParlamentar || k, eventos: ev, status: { partido: det.SiglaPartidoParlamentar || '', situacao: '' }, url: urlMat() };
  }

  return { votosCamara, atividade };
}

// Compara com o estado anterior e devolve só os eventos novos, com o estado a gravar.
export function novidades(antes, atual) {
  const vistos = new Set((antes && antes.vistos) || []);
  const novos = antes ? atual.eventos.filter(e => !vistos.has(e.id)) : [];
  if (antes && antes.status) {
    const a = antes.status, b = atual.status;
    if (b.partido && a.partido && b.partido !== a.partido) novos.push({ id: 'st', tipo: 'status', texto: `Mudou de partido: ${a.partido} para ${b.partido}`, url: atual.url, data: '' });
    if (b.situacao && a.situacao && b.situacao !== a.situacao) novos.push({ id: 'st2', tipo: 'status', texto: `Situação no mandato mudou: ${a.situacao} para ${b.situacao}`, url: atual.url, data: '' });
  }
  const todos = [...atual.eventos.map(e => e.id), ...((antes && antes.vistos) || [])];
  return { novos, estado: { nome: atual.nome, status: atual.status, url: atual.url, vistos: [...new Set(todos)].slice(0, 1500) } };
}
