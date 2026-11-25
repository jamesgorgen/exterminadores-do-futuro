// API pública do site: comparador de textos (comparador.html) e área do usuário (conta.html).
// Guarda pedidos e PDFs enviados no bucket privado do R2 (prefixo comparador/); quem processa é o robô
// robo/comparador/fila.py (workflow "Comparador"). A busca de proposições é feita no navegador, direto nas APIs da Câmara e do Senado.
//
// GET  /api/lista                 comparações prontas (comparador/indice.json)
// GET  /api/comparacao?id=…       uma comparação pronta
// GET  /api/pedido?id=…           situação de um pedido (fila, processando, pronta, erro)
// GET  /api/cota                  se a pessoa (com sessão) ainda pode pedir uma comparação nova nesta semana
// PUT  /api/envio?sha=…           envio de um PDF (corpo = o arquivo; exige sessão); devolve a referência arquivo:<sha256>
// POST /api/comparar              cria o pedido {a:{ref,…}, b:{ref,…}, titulo, proposicao}
//
// Área do usuário (login por link no e-mail, sem senha; sessão no cabeçalho Authorization: Bearer <token>):
// POST   /api/conta/link          {email, consentimento:true} envia o link de acesso (vale 20 minutos, uma vez)
// POST   /api/conta/entrar        {token} troca o link por uma sessão (90 dias, renovados a cada uso)
// GET    /api/conta               dados da conta, cota e comparações pedidas
// POST   /api/conta/sair          encerra a sessão
// GET    /api/conta/dados         tudo o que a plataforma guarda sobre a conta (LGPD)
// DELETE /api/conta               apaga a conta e as sessões
// R2 (privado), prefixo contas/: usuarios/<id>.json, links/<hash>.json, sessoes/<hash>.json, limite/…
//
// Limites: comparação nova só com cadastro, uma por semana (segunda a domingo, horário de Brasília) por conta.
// Abrir comparações prontas e pedir uma comparação que já existe não exigem cadastro. Teto mensal geral
// (LIMITE_GLOBAL_MES), contado em comparador/global/AAAA-MM/. O e-mail é guardado para o login; o IP só como hash
// com sal, para limitar pedidos de link.

const P = 'comparador/';
const ORIGENS = ['https://exterminadores.com.br', 'https://www.exterminadores.com.br', 'https://jamesgorgen.github.io'];
const MAX_PDF = 15 * 1024 * 1024;

function cors(req) {
  const o = req.headers.get('origin') || '';
  return {
    'access-control-allow-origin': ORIGENS.includes(o) ? o : '*',
    'access-control-allow-methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'access-control-allow-headers': 'content-type, authorization',
    'access-control-max-age': '86400', 'vary': 'origin',
  };
}
const json = (req, obj, status = 200, cache = 'no-store') => new Response(JSON.stringify(obj), {
  status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': cache, 'x-robots-tag': 'noindex', ...cors(req) },
});
const erro = (req, msg, status = 400, extra = {}) => json(req, { erro: msg, ...extra }, status);

const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const sha256 = async s => hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)));
const limpa = (s, n) => String(s == null ? '' : s).replace(/[\u0000-\u001f<>]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, n);

// mês e semana (de segunda a domingo) no horário de Brasília (UTC-3)
const brasilia = () => new Date(Date.now() - 3 * 3600e3);
function mes() { return brasilia().toISOString().slice(0, 7); }
function segunda() { const d = brasilia(); d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7); return d; }
function semana() { return 'semana-' + segunda().toISOString().slice(0, 10); }
function proximaSemana() { const d = segunda(); d.setUTCDate(d.getUTCDate() + 7); return d.toISOString().slice(0, 10); }

async function sal(env) {
  const o = await env.R2.get(P + 'config/sal');
  if (o) return o.text();
  const s = hex(crypto.getRandomValues(new Uint8Array(32)));
  await env.R2.put(P + 'config/sal', s);
  return s;
}
async function hashIp(req, env) {
  return (await sha256((await sal(env)) + '|' + (req.headers.get('cf-connecting-ip') || 'sem-ip'))).slice(0, 32);
}
async function cotaLivre(usuario, env) {
  const k = `cota/${semana()}/u-${usuario.id}`;
  return { k, livre: !(await env.R2.head(P + k)) };
}

// ---------------------------------------------------------------- contas
const C = 'contas/';
const CONSENTIMENTO = '2026-11-25';
const SITE = 'https://exterminadores.com.br';
const REMETENTE = { email: 'acesso@exterminadores.com.br', name: 'Os exterminadores do futuro' };
const novoToken = () => hex(crypto.getRandomValues(new Uint8Array(32)));
const lerJ = async (env, k) => { const o = await env.R2.get(k); return o ? o.json() : null; };
const gravarJ = (env, k, v) => env.R2.put(k, JSON.stringify(v), { httpMetadata: { contentType: 'application/json' } });
const agoraIso = () => new Date().toISOString().slice(0, 19) + '+00:00';
const EMAIL_OK = /^[^\s@<>()",;:]{1,64}@[a-z0-9.-]{1,190}\.[a-z]{2,24}$/;
async function idDoEmail(email) { return (await sha256('conta|' + email)).slice(0, 32); }

async function sessao(req, env) {
  const m = (req.headers.get('authorization') || '').match(/^Bearer ([0-9a-f]{64})$/);
  if (!m) return null;
  const sh = await sha256(m[1]), ks = `${C}sessoes/${sh}.json`;
  const s = await lerJ(env, ks);
  if (!s || Date.parse(s.expira) < Date.now()) return null;
  const u = await lerJ(env, `${C}usuarios/${s.usuario}.json`);
  if (!u) return null;
  // sessão deslizante: cada uso devolve a validade a 90 dias (no máximo uma gravação por dia)
  if (Date.parse(s.expira) - Date.now() < 89 * 864e5) { s.expira = new Date(Date.now() + 90 * 864e5).toISOString(); await gravarJ(env, ks, s); }
  return { ...u, sessaoHash: sh, sessaoExpira: s.expira };
}

// conta pedidos numa janela (ex.: por hora) e diz se passou do limite
async function excedeu(env, chave, max) {
  const k = `${C}limite/${new Date().toISOString().slice(0, 13)}/${chave}`;
  const o = await env.R2.get(k); const n = o ? Number(await o.text()) || 0 : 0;
  if (n >= max) return true;
  await env.R2.put(k, String(n + 1));
  return false;
}

async function pedirLink(req, env) {
  let corpo; try { corpo = await req.json(); } catch { return erro(req, 'Pedido inválido.'); }
  const email = String(corpo.email || '').trim().toLowerCase();
  if (!EMAIL_OK.test(email)) return erro(req, 'Informe um e-mail válido.');
  const id = await idDoEmail(email);
  const existe = await env.R2.head(`${C}usuarios/${id}.json`);
  if (!existe && corpo.consentimento !== true) return erro(req, 'Para criar a conta, é preciso concordar com a política de privacidade.');
  if (await excedeu(env, 'ip-' + await hashIp(req, env), 10) || await excedeu(env, 'em-' + id, 4))
    return erro(req, 'Muitos pedidos de link em pouco tempo. Tente de novo em uma hora.', 429);
  const token = novoToken();
  await gravarJ(env, `${C}links/${await sha256(token)}.json`, { email, id, consentimento: existe ? null : CONSENTIMENTO, criado: agoraIso(), expira: new Date(Date.now() + 20 * 60e3).toISOString() });
  const link = `${SITE}/conta.html#entrar=${token}`;
  try {
    await env.EMAIL.send({
      to: email, from: REMETENTE, subject: 'Seu link de acesso aos Exterminadores do futuro',
      text: `Para entrar na sua área no observatório Os exterminadores do futuro, abra este link (vale por 20 minutos e só uma vez):\n\n${link}\n\nSe você não pediu este acesso, ignore esta mensagem.\n\nexterminadores.com.br`,
      html: `<div style="font-family:Arial,sans-serif;font-size:16px;line-height:1.5;color:#1B2523;max-width:560px">
<p>Para entrar na sua área no observatório <b>Os exterminadores do futuro</b>, use o botão abaixo. O link vale por 20 minutos e só uma vez.</p>
<p><a href="${link}" style="display:inline-block;background:#123B40;color:#ffffff;text-decoration:none;font-weight:bold;padding:12px 20px;border-radius:4px">Entrar na minha área</a></p>
<p style="font-size:13px;color:#5F6B68">Se o botão não funcionar, copie este endereço no navegador:<br>${link}</p>
<p style="font-size:13px;color:#5F6B68">Se você não pediu este acesso, ignore esta mensagem.</p></div>`,
    });
  } catch (e) {
    // a mensagem da Cloudflare (sem dados pessoais) ajuda a diagnosticar problemas de configuração do envio
    const motivo = String(e && (e.code || e.message) || e).replace(/[^\w .:,;()\/-]/g, ' ').replace(/\S+@\S+/g, '[e-mail]').slice(0, 200);
    console.log('falha no envio do e-mail:', motivo);
    return erro(req, 'Não foi possível enviar o e-mail agora. Tente de novo em alguns minutos.', 503, { motivo });
  }
  return json(req, { ok: true });
}

async function entrar(req, env) {
  let corpo; try { corpo = await req.json(); } catch { return erro(req, 'Pedido inválido.'); }
  const token = String(corpo.token || '');
  if (!/^[0-9a-f]{64}$/.test(token)) return erro(req, 'Link inválido.');
  const kl = `${C}links/${await sha256(token)}.json`;
  const l = await lerJ(env, kl);
  if (!l) return erro(req, 'Este link já foi usado ou não existe. Peça um novo.', 410);
  await env.R2.delete(kl);
  if (Date.parse(l.expira) < Date.now()) return erro(req, 'Este link expirou. Peça um novo.', 410);
  const ku = `${C}usuarios/${l.id}.json`;
  let u = await lerJ(env, ku);
  const agora = agoraIso();
  if (!u) u = { id: l.id, email: l.email, criado: agora, consentimento: { versao: l.consentimento || CONSENTIMENTO, data: agora }, sessoes: [], pedidos: [] };
  const sessaoTok = novoToken(), sh = await sha256(sessaoTok);
  const expira = new Date(Date.now() + 90 * 864e5).toISOString();
  await gravarJ(env, `${C}sessoes/${sh}.json`, { usuario: u.id, criado: agora, expira });
  u.sessoes = [...(u.sessoes || []).slice(-9), sh]; u.ultimoAcesso = agora;
  await gravarJ(env, ku, u);
  return json(req, { sessao: sessaoTok, email: u.email, expira });
}

async function minhaConta(req, env, u) {
  const { livre } = await cotaLivre(u, env);
  return json(req, { email: u.email, sessaoExpira: u.sessaoExpira, criado: u.criado, consentimento: u.consentimento, cota: { disponivel: livre, renova: proximaSemana(), porSemana: 1 }, pedidos: (u.pedidos || []).slice(-30).reverse() });
}

async function sair(req, env, u) {
  await env.R2.delete(`${C}sessoes/${u.sessaoHash}.json`);
  const { sessaoHash, sessaoExpira, ...resto } = u;
  await gravarJ(env, `${C}usuarios/${u.id}.json`, { ...resto, sessoes: (u.sessoes || []).filter(x => x !== sessaoHash) });
  return json(req, { ok: true });
}

async function exportar(req, env, u) {
  const { sessaoHash, sessaoExpira, ...dados } = u;
  return json(req, { geradoEm: agoraIso(), conta: { ...dados, sessoes: `${(u.sessoes || []).length} sessão(ões) ativa(s)` },
    observacao: 'Além disso, as comparações pedidas ficam públicas na lista do comparador, sem o seu e-mail. Para limitar abusos, a plataforma guarda por uma hora um código derivado do seu IP, nunca o endereço em si.' });
}

async function excluir(req, env, u) {
  for (const sh of u.sessoes || []) await env.R2.delete(`${C}sessoes/${sh}.json`);
  await env.R2.delete(`${C}usuarios/${u.id}.json`);
  return json(req, { ok: true });
}
async function totalMes(env) {
  let n = 0, cursor;
  do {
    const r = await env.R2.list({ prefix: `${P}global/${mes()}/`, cursor, limit: 1000 });
    n += r.objects.length; cursor = r.truncated ? r.cursor : undefined;
  } while (cursor);
  return n;
}

const REF = /^(camara:\d{1,9}|senado:\d{1,12}:[0-9a-f-]{36}|arquivo:[0-9a-f]{64})$/;
const ID = /^[0-9a-f]{16}$/;

function lado(x) {
  if (!x || typeof x !== 'object' || !REF.test(String(x.ref || ''))) return null;
  return { ref: String(x.ref), nome: limpa(x.nome, 120), autor: limpa(x.autor, 120), data: limpa(x.data, 10) };
}

async function comparar(req, env) {
  let corpo;
  try { corpo = await req.json(); } catch { return erro(req, 'Pedido inválido.'); }
  const a = lado(corpo.a), b = lado(corpo.b);
  if (!a || !b) return erro(req, 'Escolha duas versões válidas.');
  if (a.ref === b.ref) return erro(req, 'Escolha duas versões diferentes.');
  for (const x of [a, b]) {
    if (x.ref.startsWith('arquivo:') && !(await env.R2.head(`${P}envios/${x.ref.slice(8)}.pdf`))) return erro(req, 'Um dos PDFs não chegou. Envie de novo.');
  }
  const id = (await sha256(`${a.ref}|${b.ref}`)).slice(0, 16);
  // já existe? não conta para o limite
  if (await env.R2.head(`${P}resultados/${id}.json`)) return json(req, { id, estado: 'pronta', existente: true });
  const antigo = await env.R2.get(`${P}pedidos/${id}.json`);
  if (antigo) {
    const p = await antigo.json();
    if (p.estado === 'fila' || p.estado === 'processando') return json(req, { id, estado: p.estado, existente: true });
    if (p.estado === 'removida') return erro(req, 'Esta comparação foi retirada da plataforma pela equipe.', 410);
  }
  const u = await sessao(req, env);
  if (!u) return erro(req, 'Para pedir uma comparação nova, entre com o seu e-mail na Minha área. As comparações prontas continuam abertas a todos.', 401);
  const { k, livre } = await cotaLivre(u, env);
  if (!livre) return erro(req, 'Você já usou a sua comparação desta semana. As comparações prontas continuam abertas.', 429, { renova: proximaSemana() });
  if ((await totalMes(env)) >= Number(env.LIMITE_GLOBAL_MES || 300)) return erro(req, 'O limite geral de comparações novas deste mês foi atingido. Tente no mês que vem.', 429);
  const agora = new Date().toISOString().slice(0, 19) + '+00:00';
  await env.R2.put(P + k, JSON.stringify({ id, criado: agora }));
  await env.R2.put(`${P}global/${mes()}/${id}`, agora);
  const pedido = { id, estado: 'fila', criado: agora, atualizado: agora, origem: 'site', a, b, titulo: limpa(corpo.titulo, 140), proposicao: limpa(corpo.proposicao, 60), tentativas: 0, cota: k, usuario: u.id };
  await env.R2.put(`${P}pedidos/${id}.json`, JSON.stringify(pedido), { httpMetadata: { contentType: 'application/json' } });
  const { sessaoHash, sessaoExpira, ...semSessao } = u;
  await gravarJ(env, `${C}usuarios/${u.id}.json`, { ...semSessao, pedidos: [...(u.pedidos || []), { id, titulo: pedido.titulo || pedido.proposicao, criado: agora }].slice(-100) });
  return json(req, { id, estado: 'fila' }, 201);
}

async function envio(req, env, url) {
  const sha = url.searchParams.get('sha') || '';
  if (!/^[0-9a-f]{64}$/.test(sha)) return erro(req, 'Envio inválido.');
  const tam = Number(req.headers.get('content-length') || 0);
  if (!tam) return erro(req, 'Arquivo vazio.');
  if (tam > MAX_PDF) return erro(req, 'O PDF passa de 15 MB.', 413);
  const chave = `${P}envios/${sha}.pdf`;
  if (await env.R2.head(chave)) return json(req, { ref: 'arquivo:' + sha });
  const u = await sessao(req, env);
  if (!u) return erro(req, 'Para enviar PDFs, entre com o seu e-mail na Minha área.', 401);
  const { livre } = await cotaLivre(u, env);
  if (!livre) return erro(req, 'Você já usou a sua comparação desta semana.', 429, { renova: proximaSemana() });
  await env.R2.put(chave, req.body, { httpMetadata: { contentType: 'application/pdf' } });
  return json(req, { ref: 'arquivo:' + sha }, 201);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors(req) });
    const o = req.headers.get('origin');
    if ((req.method === 'POST' || req.method === 'PUT' || req.method === 'DELETE') && o && !ORIGENS.includes(o)) return erro(req, 'Origem não autorizada.', 403);
    try {
      if (req.method === 'GET' && url.pathname === '/api/lista') {
        const r = await env.R2.get(P + 'indice.json');
        return new Response(r ? r.body : '{"itens":[]}', { headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'public, max-age=60', ...cors(req) } });
      }
      if (req.method === 'GET' && url.pathname === '/api/comparacao') {
        const id = url.searchParams.get('id') || '';
        if (!ID.test(id)) return erro(req, 'Identificador inválido.');
        const r = await env.R2.get(`${P}resultados/${id}.json`);
        if (!r) return erro(req, 'Comparação não encontrada.', 404);
        return new Response(r.body, { headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'public, max-age=300', ...cors(req) } });
      }
      if (req.method === 'GET' && url.pathname === '/api/pedido') {
        const id = url.searchParams.get('id') || '';
        if (!ID.test(id)) return erro(req, 'Identificador inválido.');
        const r = await env.R2.get(`${P}pedidos/${id}.json`);
        if (!r) return erro(req, 'Pedido não encontrado.', 404);
        const p = await r.json();
        return json(req, { id, estado: p.estado, erro: p.erro || null, criado: p.criado, atualizado: p.atualizado, titulo: p.titulo || p.proposicao || '' });
      }
      if (req.method === 'GET' && url.pathname === '/api/cota') {
        const u = await sessao(req, env);
        if (!u) return json(req, { logado: false, disponivel: false, renova: proximaSemana() });
        const { livre } = await cotaLivre(u, env);
        return json(req, { logado: true, email: u.email, sessaoExpira: u.sessaoExpira, disponivel: livre, renova: proximaSemana() });
      }
      if (req.method === 'POST' && url.pathname === '/api/conta/link') return pedirLink(req, env);
      if (req.method === 'POST' && url.pathname === '/api/conta/entrar') return entrar(req, env);
      if (url.pathname === '/api/conta' || url.pathname.startsWith('/api/conta/')) {
        const u = await sessao(req, env);
        if (!u) return erro(req, 'Sessão encerrada. Entre de novo com o seu e-mail.', 401);
        if (req.method === 'GET' && url.pathname === '/api/conta') return minhaConta(req, env, u);
        if (req.method === 'POST' && url.pathname === '/api/conta/sair') return sair(req, env, u);
        if (req.method === 'GET' && url.pathname === '/api/conta/dados') return exportar(req, env, u);
        if (req.method === 'DELETE' && url.pathname === '/api/conta') return excluir(req, env, u);
      }
      if (req.method === 'PUT' && url.pathname === '/api/envio') return envio(req, env, url);
      if (req.method === 'POST' && url.pathname === '/api/comparar') return comparar(req, env);
      return erro(req, 'Não encontrado.', 404);
    } catch (e) {
      return erro(req, 'Erro interno. Tente de novo em instantes.', 500);
    }
  },
};
