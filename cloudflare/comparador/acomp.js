// Acompanhamento de projetos: seguir proposições, avisos por push (Web Push com VAPID, sem conteúdo cifrado:
// o service worker do site busca os avisos em /api/avisos) e resumo diário por e-mail.
//
// R2, prefixo acomp/:
//   indice.json                 {p: {"camara:ID"|"senado:ID": {t: título, u: [contas], d: [aparelhos sem conta]}}}
//   estado/<chave>.json         última movimentação e versões conhecidas de cada projeto
//   disp/<aparelho>.json        inscrição de push de um aparelho (endpoint) e, sem conta, os projetos seguidos
//   avisos/<aparelho>.json      avisos ainda não lidos pelo service worker
//   email/<conta>.json          novidades do dia para o resumo por e-mail
//   config/vapid.json, config/segredo
//
// Limites (serviço sem IA): sem cadastro, até 3 projetos, só push; com cadastro, até 100 projetos, push e e-mail.

const A = 'acomp/';
const LIM_ANON = 3, LIM_CONTA = 100;
const CONSENT_ACOMP = '2026-11-25';
const CHAVE = /^(camara:\d{1,9}|senado:\d{1,12})$/;
const CAM = 'https://dadosabertos.camara.leg.br/api/v2';
const SEN = 'https://legis.senado.leg.br/dadosabertos';
const TIPOS_CAM = new Set(['PRLP', 'PRL', 'PAR', 'PPP', 'SBT', 'SBT-A', 'SBE', 'SBR', 'EMC', 'EMC-A', 'EMP', 'EMR', 'EMS', 'ESB', 'EMA', 'RDF', 'PEP', 'PES', 'EMD']);
const TIPOS_SEN = /^(PROJETO|PARECER|RELATORIO|EMENDA|TEXTO|SUBSTITUTIVO|AUTOGRAFO|REDACAO)/;
const UA = { 'user-agent': 'exterminadores.com.br (acompanhamento de projetos; contato@exterminadores.com.br)', accept: 'application/json' };

const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const seguro = k => k.replace(':', '_');

export function criarAcomp(h) {
  const { json, erro, sha256, lerJ, gravarJ, agoraIso, limpa, sessao } = h;

  // ---------------------------------------------------------------- índice com gravação condicional
  async function mudarIndice(env, fn) {
    for (let t = 0; t < 6; t++) {
      const o = await env.R2.get(A + 'indice.json');
      const ind = o ? await o.json() : { p: {} };
      fn(ind);
      for (const [k, v] of Object.entries(ind.p)) if (!v.u.length && !v.d.length) delete ind.p[k];
      const ok = await env.R2.put(A + 'indice.json', JSON.stringify(ind), o ? { onlyIf: { etagMatches: o.etag } } : {});
      if (ok) return ind;
      await new Promise(r => setTimeout(r, 80 * (t + 1)));
    }
    throw new Error('índice ocupado');
  }
  const juntar = (ind, k, t, campo, id) => { const e = ind.p[k] || (ind.p[k] = { t, u: [], d: [] }); if (t) e.t = t; if (!e[campo].includes(id)) e[campo].push(id); };
  const tirar = (ind, k, campo, id) => { const e = ind.p[k]; if (e) e[campo] = e[campo].filter(x => x !== id); };

  // ---------------------------------------------------------------- VAPID e push
  async function vapid(env) {
    const o = await lerJ(env, A + 'config/vapid.json');
    if (o) return o;
    const par = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
    const novo = { publica: b64u(await crypto.subtle.exportKey('raw', par.publicKey)), privada: await crypto.subtle.exportKey('jwk', par.privateKey) };
    await env.R2.put(A + 'config/vapid.json', JSON.stringify(novo));
    return (await lerJ(env, A + 'config/vapid.json')) || novo;
  }
  async function enviarPush(env, endpoint) {
    const v = await vapid(env);
    const aud = new URL(endpoint).origin;
    const cab = b64u(new TextEncoder().encode(JSON.stringify({ typ: 'JWT', alg: 'ES256' })));
    const corpo = b64u(new TextEncoder().encode(JSON.stringify({ aud, exp: Math.floor(Date.now() / 1000) + 12 * 3600, sub: 'mailto:contato@exterminadores.com.br' })));
    const chave = await crypto.subtle.importKey('jwk', v.privada, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
    const ass = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, chave, new TextEncoder().encode(cab + '.' + corpo));
    const r = await fetch(endpoint, { method: 'POST', headers: { authorization: `vapid t=${cab}.${corpo}.${b64u(ass)}, k=${v.publica}`, ttl: '86400', urgency: 'normal', 'content-length': '0' } });
    return r.status;
  }
  const idAparelho = async endpoint => (await sha256('disp|' + endpoint)).slice(0, 32);
  const endpointOk = e => typeof e === 'string' && /^https:\/\/[a-z0-9.-]+\//i.test(e) && e.length < 1000;

  // ---------------------------------------------------------------- rotas
  async function quem(req, env, corpo) {
    const u = await sessao(req, env);
    if (u) return { u };
    if (corpo && endpointOk(corpo.endpoint)) {
      const d = await lerJ(env, `${A}disp/${await idAparelho(corpo.endpoint)}.json`);
      if (d) return { d, dId: await idAparelho(corpo.endpoint) };
    }
    return {};
  }
  const corpoDe = async req => { try { return await req.json(); } catch { return {}; } };
  const semSessao = u => { const { sessaoHash, sessaoExpira, ...r } = u; return r; };

  async function chavePublica(req, env) { return json(req, { chave: (await vapid(env)).publica }); }

  async function inscrever(req, env) {
    const c = await corpoDe(req);
    const endpoint = c.sub && c.sub.endpoint;
    if (!endpointOk(endpoint)) return erro(req, 'Inscrição de avisos inválida.');
    const id = await idAparelho(endpoint), k = `${A}disp/${id}.json`;
    const u = await sessao(req, env);
    const d = (await lerJ(env, k)) || { criado: agoraIso(), projetos: [] };
    if (!u && !d.consentimento && c.consentimento !== true) return erro(req, 'É preciso concordar com o uso da lista de projetos para receber avisos.');
    d.endpoint = endpoint; d.atualizado = agoraIso(); d.consentimento = d.consentimento || CONSENT_ACOMP;
    if (u) {
      d.usuario = u.id;
      const ru = semSessao(u); ru.dispositivos = [...new Set([...(ru.dispositivos || []), id])].slice(-10);
      await gravarJ(env, `contas/usuarios/${u.id}.json`, ru);
    }
    await gravarJ(env, k, d);
    return json(req, { ok: true, conta: !!u });
  }

  async function cancelar(req, env) {
    const c = await corpoDe(req);
    if (!endpointOk(c.endpoint)) return erro(req, 'Pedido inválido.');
    const id = await idAparelho(c.endpoint), d = await lerJ(env, `${A}disp/${id}.json`);
    if (d) {
      if (d.projetos && d.projetos.length) await mudarIndice(env, ind => d.projetos.forEach(p => tirar(ind, p.k, 'd', id)));
      if (d.usuario) { const u = await lerJ(env, `contas/usuarios/${d.usuario}.json`); if (u) { u.dispositivos = (u.dispositivos || []).filter(x => x !== id); await gravarJ(env, `contas/usuarios/${u.id}.json`, u); } }
      await env.R2.delete(`${A}disp/${id}.json`); await env.R2.delete(`${A}avisos/${id}.json`);
    }
    return json(req, { ok: true });
  }

  async function lista(req, env) {
    const c = req.method === 'POST' ? await corpoDe(req) : {};
    const q = await quem(req, env, c);
    if (q.u) return json(req, { conta: true, projetos: q.u.acomp || [], limite: LIM_CONTA, email: q.u.avisosEmail !== false, consentimento: !!q.u.consentimentoAcomp, aparelhos: (q.u.dispositivos || []).length });
    if (q.d) return json(req, { conta: false, projetos: q.d.projetos || [], limite: LIM_ANON, email: false, consentimento: true });
    return json(req, { conta: false, projetos: [], limite: LIM_ANON, email: false, consentimento: false });
  }

  async function seguir(req, env) {
    const c = await corpoDe(req);
    const k = String(c.k || ''), t = limpa(c.t, 160);
    if (!CHAVE.test(k)) return erro(req, 'Projeto inválido.');
    const q = await quem(req, env, c);
    if (q.u) {
      const u = semSessao(q.u);
      if (!u.consentimentoAcomp) { if (c.consentimento !== true) return erro(req, 'É preciso concordar com o uso da lista de projetos acompanhados.', 400, { precisaConsentimento: true }); u.consentimentoAcomp = { versao: CONSENT_ACOMP, data: agoraIso() }; }
      u.acomp = u.acomp || [];
      if (!u.acomp.some(p => p.k === k)) {
        if (u.acomp.length >= LIM_CONTA) return erro(req, `O limite é de ${LIM_CONTA} projetos acompanhados por conta.`, 429);
        u.acomp.push({ k, t, desde: agoraIso() });
      }
      if (u.avisosEmail === undefined) u.avisosEmail = true;
      await gravarJ(env, `contas/usuarios/${u.id}.json`, u);
      await mudarIndice(env, ind => juntar(ind, k, t, 'u', u.id));
      return json(req, { ok: true, projetos: u.acomp });
    }
    if (q.d) {
      const d = q.d; d.projetos = d.projetos || [];
      if (!d.projetos.some(p => p.k === k)) {
        if (d.projetos.length >= LIM_ANON) return erro(req, `Sem cadastro, é possível acompanhar até ${LIM_ANON} projetos. Entre com o seu e-mail na Minha área para acompanhar até ${LIM_CONTA}.`, 429);
        d.projetos.push({ k, t, desde: agoraIso() });
      }
      await gravarJ(env, `${A}disp/${q.dId}.json`, d);
      await mudarIndice(env, ind => juntar(ind, k, t, 'd', q.dId));
      return json(req, { ok: true, projetos: d.projetos });
    }
    return erro(req, 'Para acompanhar projetos, ative os avisos neste aparelho ou entre com o seu e-mail na Minha área.', 401);
  }

  async function deixar(req, env) {
    const c = await corpoDe(req); const k = String(c.k || '');
    if (!CHAVE.test(k)) return erro(req, 'Projeto inválido.');
    const q = await quem(req, env, c);
    if (q.u) {
      const u = semSessao(q.u); u.acomp = (u.acomp || []).filter(p => p.k !== k);
      await gravarJ(env, `contas/usuarios/${u.id}.json`, u); await mudarIndice(env, ind => tirar(ind, k, 'u', u.id));
      return json(req, { ok: true, projetos: u.acomp });
    }
    if (q.d) {
      q.d.projetos = (q.d.projetos || []).filter(p => p.k !== k);
      await gravarJ(env, `${A}disp/${q.dId}.json`, q.d); await mudarIndice(env, ind => tirar(ind, k, 'd', q.dId));
      return json(req, { ok: true, projetos: q.d.projetos });
    }
    return erro(req, 'Sessão encerrada.', 401);
  }

  async function preferenciaEmail(req, env) {
    const u = await sessao(req, env); if (!u) return erro(req, 'Sessão encerrada.', 401);
    const c = await corpoDe(req); const r = semSessao(u); r.avisosEmail = c.ativo === true;
    await gravarJ(env, `contas/usuarios/${u.id}.json`, r);
    return json(req, { ok: true, email: r.avisosEmail });
  }

  async function segredo(env) {
    const o = await env.R2.get(A + 'config/segredo'); if (o) return o.text();
    const s = [...crypto.getRandomValues(new Uint8Array(32))].map(b => b.toString(16).padStart(2, '0')).join('');
    await env.R2.put(A + 'config/segredo', s); return s;
  }
  const tokenSaida = async (env, uid) => (await sha256((await segredo(env)) + '|saida|' + uid)).slice(0, 32);
  async function sairEmail(req, env, url) {
    const uid = url.searchParams.get('u') || '', t = url.searchParams.get('t') || '';
    const pagina = msg => new Response(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Avisos por e-mail</title><body style="font-family:Arial,sans-serif;max-width:560px;margin:40px auto;padding:0 20px;color:#1B2523"><h1 style="font-size:22px">Avisos por e-mail</h1><p>${msg}</p><p><a href="https://exterminadores.com.br/conta.html">Ir para a Minha área</a></p></body>`, { headers: { 'content-type': 'text/html; charset=utf-8' } });
    if (!/^[0-9a-f]{32}$/.test(uid) || t !== await tokenSaida(env, uid)) return pagina('Link inválido.');
    const u = await lerJ(env, `contas/usuarios/${uid}.json`);
    if (u) { u.avisosEmail = false; await gravarJ(env, `contas/usuarios/${uid}.json`, u); }
    return pagina('Pronto: você não vai mais receber o resumo diário por e-mail. Os avisos por push e a lista de projetos continuam como estavam, e é possível reativar o e-mail na Minha área.');
  }

  async function avisos(req, env) {
    const c = await corpoDe(req);
    if (!endpointOk(c.endpoint)) return erro(req, 'Pedido inválido.');
    const id = await idAparelho(c.endpoint), k = `${A}avisos/${id}.json`;
    const lista = (await lerJ(env, k)) || [];
    if (lista.length) await env.R2.delete(k);
    return json(req, { avisos: lista });
  }

  async function teste(req, env) {
    const c = await corpoDe(req);
    if (!endpointOk(c.endpoint)) return erro(req, 'Pedido inválido.');
    const id = await idAparelho(c.endpoint), kd = `${A}disp/${id}.json`, d = await lerJ(env, kd);
    if (!d) return erro(req, 'Ative os avisos neste aparelho primeiro.', 404);
    if (d.ultimoTeste && Date.now() - Date.parse(d.ultimoTeste) < 10 * 60e3) return erro(req, 'Já enviamos um aviso de teste há pouco. Tente de novo em alguns minutos.', 429);
    d.ultimoTeste = new Date().toISOString(); await gravarJ(env, kd, d);
    const ka = `${A}avisos/${id}.json`;
    await gravarJ(env, ka, [...((await lerJ(env, ka)) || []), { k: 'teste', nome: 'Os exterminadores do futuro', titulo: 'Teste', tipo: 'teste', texto: 'Os avisos estão funcionando neste aparelho.', url: '/conta.html#acompanhamento' }].slice(-30));
    const st = await enviarPush(env, d.endpoint);
    if (st === 404 || st === 410) { await env.R2.delete(kd); await env.R2.delete(ka); return erro(req, 'O navegador desativou esta inscrição. Ative os avisos de novo.', 410); }
    return st < 300 ? json(req, { ok: true }) : erro(req, `O serviço de push do navegador recusou o aviso (código ${st}).`, 502);
  }

  // ---------------------------------------------------------------- tarefa agendada
  async function situacao(k) {
    const [casa, id] = k.split(':');
    if (casa === 'camara') {
      const d = (await (await fetch(`${CAM}/proposicoes/${id}`, { headers: UA })).json()).dados;
      const rel = ((await (await fetch(`${CAM}/proposicoes/${id}/relacionadas`, { headers: UA })).json()).dados || []).filter(x => TIPOS_CAM.has(x.siglaTipo));
      const s = d.statusProposicao || {};
      return { titulo: `${d.siglaTipo} ${d.numero}/${d.ano}`, url: `https://www.camara.leg.br/propostas-legislativas/${id}`,
        mov: { data: s.dataHora || '', texto: [s.descricaoTramitacao, s.despacho].filter(Boolean).join(': ').slice(0, 400), situacao: s.descricaoSituacao || '', orgao: s.siglaOrgao || '' },
        versoes: Object.fromEntries(rel.map(x => [String(x.id), +x.ano ? `${x.siglaTipo} ${x.numero}/${x.ano}` : `${x.siglaTipo} ${x.numero}`])) };
    }
    const d = await (await fetch(`${SEN}/processo/${id}`, { headers: UA })).json();
    let ult = { data: '', descricao: '' }; const versoes = {};
    for (const au of d.autuacoes || []) for (const inf of au.informesLegislativos || []) {
      if ((inf.data || '') > ult.data) ult = inf;
      for (const x of inf.documentosAssociados || []) if (x.url && TIPOS_SEN.test(x.siglaTipo || '')) versoes[x.url.split('/').pop()] = x.identificacao || x.tipo;
    }
    return { titulo: d.identificacao || `${d.sigla} ${d.numero}/${d.ano}`, url: d.codigoMateria ? `https://www25.senado.leg.br/web/atividade/materias/-/materia/${d.codigoMateria}` : 'https://www25.senado.leg.br/',
      mov: { data: String(ult.data || ''), texto: String(ult.descricao || '').slice(0, 400), situacao: d.situacaoAtual || '', orgao: (ult.colegiado && ult.colegiado.sigla) || '' }, versoes };
  }

  async function rodar(env, quando = Date.now()) {
    const ind = await lerJ(env, A + 'indice.json');
    const resumo = { projetos: 0, eventos: 0, push: 0, emails: 0, erros: 0 };
    const avisosPorDisp = new Map(), emailPorConta = new Map();
    const contas = new Map();
    const conta = async uid => { if (!contas.has(uid)) contas.set(uid, await lerJ(env, `contas/usuarios/${uid}.json`)); return contas.get(uid); };
    for (const [k, seg] of Object.entries((ind && ind.p) || {})) {
      resumo.projetos++;
      let atual;
      try { atual = await situacao(k); } catch (e) { resumo.erros++; continue; }
      const ke = `${A}estado/${seguro(k)}.json`, antes = await lerJ(env, ke);
      await gravarJ(env, ke, { ...atual, verificado: new Date(quando).toISOString() });
      if (!antes) continue; // primeira leitura: só guarda o estado
      const eventos = [];
      if (atual.mov.data && atual.mov.data !== antes.mov.data) eventos.push({ tipo: 'mov', texto: atual.mov.texto || atual.mov.situacao || 'Nova movimentação', data: atual.mov.data });
      for (const [vid, nome] of Object.entries(atual.versoes)) if (!(vid in (antes.versoes || {}))) eventos.push({ tipo: 'versao', texto: `Novo texto publicado: ${nome}`, data: atual.mov.data });
      if (!eventos.length) continue;
      resumo.eventos += eventos.length;
      const itens = eventos.map(e => ({ k, titulo: atual.titulo, nome: seg.t || atual.titulo, url: e.tipo === 'versao' ? 'https://exterminadores.com.br/comparador.html' : atual.url, tipo: e.tipo, texto: e.texto, data: e.data }));
      for (const d of seg.d) avisosPorDisp.set(d, [...(avisosPorDisp.get(d) || []), ...itens]);
      for (const uid of seg.u) {
        const u = await conta(uid); if (!u) continue;
        for (const d of u.dispositivos || []) avisosPorDisp.set(d, [...(avisosPorDisp.get(d) || []), ...itens]);
        if (u.avisosEmail !== false) emailPorConta.set(uid, [...(emailPorConta.get(uid) || []), ...itens]);
      }
    }
    // push: guarda os avisos e acorda o aparelho
    for (const [d, itens] of avisosPorDisp) {
      const disp = await lerJ(env, `${A}disp/${d}.json`); if (!disp) continue;
      const ka = `${A}avisos/${d}.json`;
      await gravarJ(env, ka, [...((await lerJ(env, ka)) || []), ...itens].slice(-30));
      try {
        const st = await enviarPush(env, disp.endpoint);
        if (st === 404 || st === 410) { await env.R2.delete(`${A}disp/${d}.json`); await env.R2.delete(ka); }
        else if (st < 300) resumo.push++;
      } catch (e) { resumo.erros++; }
    }
    // e-mail: acumula no dia e envia o resumo às 19h de Brasília
    for (const [uid, itens] of emailPorConta) {
      const ke = `${A}email/${uid}.json`;
      await gravarJ(env, ke, [...((await lerJ(env, ke)) || []), ...itens].slice(-200));
    }
    if (new Date(quando).getUTCHours() === 22) resumo.emails = await enviarResumos(env);
    await gravarJ(env, A + 'ultima-execucao.json', { ...resumo, em: new Date(quando).toISOString() });
    return resumo;
  }

  async function enviarResumos(env) {
    let n = 0, cursor;
    do {
      const l = await env.R2.list({ prefix: A + 'email/', cursor }); cursor = l.truncated ? l.cursor : undefined;
      for (const o of l.objects) {
        const uid = o.key.slice((A + 'email/').length, -5);
        const itens = (await lerJ(env, o.key)) || []; await env.R2.delete(o.key);
        const u = await lerJ(env, `contas/usuarios/${uid}.json`);
        if (!u || u.avisosEmail === false || !itens.length) continue;
        const porProj = new Map(); itens.forEach(i => porProj.set(i.k, [...(porProj.get(i.k) || []), i]));
        const e = s => String(s || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
        const saida = `https://comparador-exterminadores.gorgen-james.workers.dev/api/acomp/sair-email?u=${uid}&t=${await tokenSaida(env, uid)}`;
        const blocos = [...porProj.values()].map(lst => `<h3 style="font-size:17px;margin:18px 0 4px">${e(lst[0].nome)}</h3><ul style="margin:0;padding-left:18px">${lst.map(i => `<li style="margin:4px 0">${i.tipo === 'versao' ? '<b>Novo texto.</b> ' : ''}${e(i.texto)} <a href="${e(i.url)}">ver</a></li>`).join('')}</ul>`).join('');
        const texto = [...porProj.values()].map(lst => `${lst[0].nome}\n` + lst.map(i => `- ${i.texto} (${i.url})`).join('\n')).join('\n\n');
        try {
          await env.EMAIL.send({ to: u.email, from: { email: 'avisos@exterminadores.com.br', name: 'Os exterminadores do futuro' },
            subject: `Novidades em ${porProj.size} projeto${porProj.size > 1 ? 's' : ''} que você acompanha`,
            text: `Novidades de hoje nos projetos que você acompanha no observatório Os exterminadores do futuro:\n\n${texto}\n\nGerencie os seus projetos: https://exterminadores.com.br/conta.html\nParar de receber este resumo: ${saida}`,
            html: `<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#1B2523;max-width:600px"><p>Novidades de hoje nos projetos que você acompanha no observatório <b>Os exterminadores do futuro</b>:</p>${blocos}
<p style="margin-top:24px"><a href="https://exterminadores.com.br/conta.html">Gerenciar os meus projetos</a></p>
<p style="font-size:12px;color:#5F6B68">Você recebe este resumo porque acompanha projetos na sua conta. <a href="${saida}">Parar de receber por e-mail</a>.</p></div>`,
            headers: { 'List-Unsubscribe': `<${saida}>` } });
          n++;
        } catch (err) { console.log('resumo por e-mail falhou:', String(err && err.message || err).slice(0, 200)); }
      }
    } while (cursor);
    return n;
  }

  // apaga os dados de acompanhamento de uma conta excluída
  async function apagarConta(env, u) {
    if ((u.acomp || []).length) await mudarIndice(env, ind => u.acomp.forEach(p => tirar(ind, p.k, 'u', u.id)));
    for (const d of u.dispositivos || []) { await env.R2.delete(`${A}disp/${d}.json`); await env.R2.delete(`${A}avisos/${d}.json`); }
    await env.R2.delete(`${A}email/${u.id}.json`);
  }

  return { teste, chavePublica, inscrever, cancelar, lista, seguir, deixar, preferenciaEmail, sairEmail, avisos, rodar, apagarConta, LIM_ANON, LIM_CONTA };
}
