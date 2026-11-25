// Acompanhamento de projetos no navegador: avisos por push, lista de projetos seguidos e busca de projetos.
// Usado por conta.html e comparador.html. Fala com o Worker cloudflare/comparador (rotas /api/acomp/* e /api/push/*).
(function () {
  'use strict';
  const API = 'https://comparador-exterminadores.gorgen-james.workers.dev';
  const CAM = 'https://dadosabertos.camara.leg.br/api/v2';
  const SEN = 'https://legis.senado.leg.br/dadosabertos';
  const sessao = () => { try { const s = JSON.parse(localStorage.getItem('ext-sessao')); return s && Date.parse(s.expira) > Date.now() ? s : null; } catch (_) { return null; } };
  async function api(path, corpo, metodo) {
    const s = sessao(), headers = {};
    if (s) headers.authorization = 'Bearer ' + s.token;
    if (corpo) headers['content-type'] = 'application/json';
    const r = await fetch(API + path, { method: metodo || (corpo ? 'POST' : 'GET'), headers, body: corpo ? JSON.stringify(corpo) : undefined });
    let j = {}; try { j = await r.json(); } catch (_) {}
    if (!r.ok) { const e = new Error(j.erro || 'O serviço não respondeu. Tente de novo em instantes.'); e.status = r.status; e.dados = j; throw e; }
    return j;
  }
  const suportado = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  const ios = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const instalado = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  async function registro() { return navigator.serviceWorker.register('/sw.js'); }
  async function inscricao() {
    if (!suportado()) return null;
    const reg = await navigator.serviceWorker.getRegistration('/');
    return reg ? reg.pushManager.getSubscription() : null;
  }
  const b64 = s => { const p = '='.repeat((4 - s.length % 4) % 4); const r = atob((s + p).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(r, c => c.charCodeAt(0)); };

  const Avisos = {
    sessao, suportado, ios, instalado,
    async estado() {
      if (!suportado()) return ios() && !instalado() ? 'ios-instalar' : 'sem-suporte';
      if (Notification.permission === 'denied') return 'negado';
      return (await inscricao()) ? 'ativo' : 'inativo';
    },
    async ativar(consentimento) {
      if (!suportado()) throw new Error(ios() ? 'No iPhone e no iPad, adicione o site à tela de início (botão Compartilhar > Adicionar à Tela de Início) e ative os avisos pelo ícone.' : 'Este navegador não recebe avisos.');
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') throw new Error('Os avisos foram bloqueados neste navegador. Libere as notificações do site nas configurações do navegador.');
      const reg = await registro(); await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) { const { chave } = await api('/api/push/chave'); sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(chave) }); }
      await api('/api/push/inscrever', { sub: sub.toJSON(), consentimento: consentimento === true });
      return sub;
    },
    async desativar() {
      const sub = await inscricao(); if (!sub) return;
      try { await api('/api/push/cancelar', { endpoint: sub.endpoint }); } catch (_) {}
      await sub.unsubscribe();
    },
    async lista() {
      if (sessao()) return api('/api/acomp/lista');
      const sub = await inscricao();
      return sub ? api('/api/acomp/lista', { endpoint: sub.endpoint }) : { conta: false, projetos: [], limite: 3, consentimento: false };
    },
    async seguir(k, t, consentimento) {
      const sub = sessao() ? null : await inscricao();
      return api('/api/acomp/seguir', { k, t, consentimento: consentimento === true, endpoint: sub ? sub.endpoint : undefined });
    },
    async deixar(k) {
      const sub = sessao() ? null : await inscricao();
      return api('/api/acomp/deixar', { k, endpoint: sub ? sub.endpoint : undefined });
    },
    email(ativo) { return api('/api/acomp/email', { ativo }); },
    async testar() { const sub = await inscricao(); if (!sub) throw new Error('Ative os avisos neste aparelho primeiro.'); return api('/api/push/teste', { endpoint: sub.endpoint }); },
    // "PL 4675/2025" na Câmara ou no Senado → {k, t, ementa}
    async resolver(q, casa) {
      const m = String(q || '').replace(/\./g, '').match(/^\s*([A-Za-z]{2,5})\s*n?[º°]?\s*(\d{1,5})\s*\/\s*(\d{2,4})\s*$/);
      if (!m) throw new Error('Informe a sigla, o número e o ano, por exemplo PL 4675/2025.');
      let [, sigla, numero, ano] = m; sigla = sigla.toUpperCase(); if (ano.length === 2) ano = (+ano > 50 ? '19' : '20') + ano;
      if (casa !== 'senado') {
        const r = await fetch(`${CAM}/proposicoes?siglaTipo=${encodeURIComponent(sigla)}&numero=${numero}&ano=${ano}`, { headers: { accept: 'application/json' } }).then(r => r.json()).catch(() => ({ dados: [] }));
        if (r.dados && r.dados.length) return { k: 'camara:' + r.dados[0].id, t: `${sigla} ${numero}/${ano}`, ementa: r.dados[0].ementa, casa: 'Câmara' };
        if (casa === 'camara') throw new Error(`Não há ${sigla} ${numero}/${ano} na Câmara${sigla === 'PLC' ? ' (lá, projeto de lei complementar é PLP)' : ''}.`);
      }
      const l = await fetch(`${SEN}/processo?sigla=${encodeURIComponent(sigla)}&numero=${numero}&ano=${ano}`, { headers: { accept: 'application/json' } }).then(r => r.json()).catch(() => []);
      if (l.length) return { k: 'senado:' + l[0].id, t: l[0].identificacao || `${sigla} ${numero}/${ano}`, ementa: l[0].ementa, casa: 'Senado' };
      throw new Error(`Não encontramos ${sigla} ${numero}/${ano}${casa === 'senado' ? ' no Senado' : ' na Câmara nem no Senado'}.`);
    },
  };
  window.Avisos = Avisos;
  if (suportado()) navigator.serviceWorker.getRegistration('/').then(r => { if (!r && Notification.permission === 'granted') registro(); }).catch(() => {});
})();
