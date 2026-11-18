// Triagem das bancadas: página e API, atrás do Cloudflare Access.
// Dados (com vínculos de familiares e terceiros) e decisões da equipe ficam no bucket privado do R2:
//   bancadas/bancadas.json   gerado pelo robô robo/bancadas.py
//   bancadas/decisoes.json   decisões e votações-chave da equipe
//   bancadas/historico/...   uma cópia de cada gravação, com autor e data
import PAGINA from './index.html';

const DADOS = 'bancadas/bancadas.json';
const DECISOES = 'bancadas/decisoes.json';
const json = (obj, status = 200, extra = {}) => new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...extra } });
const SEG = { 'x-frame-options': 'DENY', 'referrer-policy': 'no-referrer', 'x-robots-tag': 'noindex, nofollow', 'cache-control': 'no-store' };

// ---------- verificação do token do Cloudflare Access (JWT RS256)
let certs = null, certsEm = 0;
const b64url = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), c => c.charCodeAt(0));
const txt = u8 => new TextDecoder().decode(u8);
async function chaves(team) {
  if (certs && Date.now() - certsEm < 3600e3) return certs;
  const r = await fetch(`https://${team}.cloudflareaccess.com/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error('certificados do Access indisponíveis');
  certs = (await r.json()).keys || []; certsEm = Date.now();
  return certs;
}
function cookie(req, nome) {
  const c = req.headers.get('cookie') || '';
  const m = c.match(new RegExp('(?:^|; )' + nome + '=([^;]+)'));
  return m ? m[1] : null;
}
async function usuario(req, env) {
  if (!env.ACCESS_TEAM || !env.ACCESS_AUD) return { erro: 'configuracao' };
  const jwt = req.headers.get('cf-access-jwt-assertion') || cookie(req, 'CF_Authorization');
  if (!jwt) return { erro: 'sem-token' };
  const [h, p, s] = jwt.split('.');
  if (!h || !p || !s) return { erro: 'token' };
  const head = JSON.parse(txt(b64url(h))), pay = JSON.parse(txt(b64url(p)));
  const jwk = (await chaves(env.ACCESS_TEAM)).find(k => k.kid === head.kid);
  if (!jwk || head.alg !== 'RS256') return { erro: 'token' };
  const chave = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
  const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', chave, b64url(s), new TextEncoder().encode(h + '.' + p));
  const aud = Array.isArray(pay.aud) ? pay.aud : [pay.aud];
  if (!ok || !aud.includes(env.ACCESS_AUD) || pay.iss !== `https://${env.ACCESS_TEAM}.cloudflareaccess.com` || (pay.exp || 0) * 1000 < Date.now()) return { erro: 'token' };
  return { email: pay.email || pay.common_name || 'desconhecido' };
}

// ---------- decisões: mescla no servidor, com gravação condicional para não perder alterações simultâneas
async function lerDecisoes(env) {
  const o = await env.R2.get(DECISOES);
  if (!o) return { etag: null, dados: { decisoes: {}, votacoes: {} } };
  return { etag: o.etag, dados: await o.json() };
}
async function gravar(env, mudancas, email) {
  const agora = new Date().toISOString();
  for (let t = 0; t < 5; t++) {
    const { etag, dados } = await lerDecisoes(env);
    const dec = dados.decisoes || {}, vot = dados.votacoes || {};
    for (const [c, v] of Object.entries(mudancas.decisoes || {})) {
      if (!/^[CS]\d+\|[a-z]+$/.test(c)) continue;
      if (v === null) delete dec[c];
      else if (['nucleo', 'aliado', 'fora', 'incerto'].includes(v.d)) dec[c] = { d: v.d, m: String(v.m || '').slice(0, 2000), por: email, data: agora.slice(0, 10) };
    }
    for (const [b, o] of Object.entries(mudancas.votacoes || {})) {
      if (!/^[a-z]+$/.test(b)) continue;
      vot[b] = vot[b] || {};
      for (const [id, v] of Object.entries(o || {})) { if (v === 'S' || v === 'N') vot[b][id] = v; else delete vot[b][id]; }
      if (!Object.keys(vot[b]).length) delete vot[b];
    }
    const novo = { atualizado: agora, decisoes: dec, votacoes: vot };
    const corpo = JSON.stringify(novo);
    const r = await env.R2.put(DECISOES, corpo, etag ? { onlyIf: { etagMatches: etag }, httpMetadata: { contentType: 'application/json' } } : { httpMetadata: { contentType: 'application/json' } });
    if (r) {
      await env.R2.put(`bancadas/historico/${agora.replace(/[:.]/g, '-')}-${email.replace(/[^a-z0-9@._-]/gi, '_')}.json`, JSON.stringify({ por: email, em: agora, mudancas }));
      return novo;
    }
  }
  throw new Error('conflito com outra gravação');
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    let u;
    try { u = await usuario(req, env); } catch (e) { u = { erro: 'token' }; }
    if (u.erro === 'configuracao') return new Response('A triagem ainda não está configurada: faltam ACCESS_TEAM e ACCESS_AUD no wrangler.toml.', { status: 503, headers: SEG });
    if (u.erro) return new Response('Acesso restrito à equipe. Entre pelo endereço da triagem e use o seu e-mail cadastrado.', { status: 403, headers: SEG });

    if (url.pathname === '/' || url.pathname === '/index.html') return new Response(PAGINA, { headers: { 'content-type': 'text/html; charset=utf-8', ...SEG } });
    if (url.pathname === '/api/eu') return json({ email: u.email });
    if (url.pathname === '/api/dados') {
      const o = await env.R2.get(DADOS);
      if (!o) return json({ erro: 'Os dados ainda não foram gerados pelo robô.' }, 404);
      return new Response(o.body, { headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });
    }
    if (url.pathname === '/api/decisoes' && req.method === 'GET') return json((await lerDecisoes(env)).dados);
    if (url.pathname === '/api/decisoes' && req.method === 'POST') {
      if (req.headers.get('content-type') !== 'application/json' || req.headers.get('x-triagem') !== '1') return json({ erro: 'formato' }, 415);
      let m; try { m = await req.json(); } catch (e) { return json({ erro: 'formato' }, 400); }
      try { return json(await gravar(env, m, u.email)); } catch (e) { return json({ erro: e.message }, 409); }
    }
    return new Response('Não encontrado.', { status: 404, headers: SEG });
  }
};
