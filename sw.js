// Service worker do site: recebe os avisos de projetos acompanhados (Web Push sem conteúdo) e busca o texto dos
// avisos na API do Worker (cloudflare/comparador), que entrega e apaga os avisos pendentes deste aparelho.
const API = 'https://comparador-exterminadores.gorgen-james.workers.dev';
const ICONE = '/imagens/icone-512.png';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', e => e.waitUntil((async () => {
  let avisos = [];
  try {
    const sub = await self.registration.pushManager.getSubscription();
    if (sub) {
      const r = await fetch(API + '/api/avisos', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }) });
      avisos = (await r.json()).avisos || [];
    }
  } catch (_) {}
  if (!avisos.length) {
    return self.registration.showNotification('Os exterminadores do futuro', { body: 'Há novidades nos projetos que você acompanha.', icon: ICONE, badge: ICONE, data: { url: '/conta.html' } });
  }
  const porProj = new Map();
  for (const a of avisos) porProj.set(a.k, [...(porProj.get(a.k) || []), a]);
  if (porProj.size === 1) {
    const [lst] = porProj.values();
    return self.registration.showNotification(lst[0].nome || lst[0].titulo, {
      body: lst.map(a => a.texto).join('\n').slice(0, 300), icon: ICONE, badge: ICONE, tag: lst[0].k,
      data: { url: lst.some(a => a.tipo === 'versao') ? '/comparador.html' : (lst[0].url || '/conta.html') } });
  }
  return self.registration.showNotification(`Novidades em ${porProj.size} projetos que você acompanha`, {
    body: [...porProj.values()].map(l => `${l[0].nome || l[0].titulo}: ${l[0].texto}`).join('\n').slice(0, 300), icon: ICONE, badge: ICONE, tag: 'varios',
    data: { url: '/conta.html#acompanhamento' } });
})()));

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/conta.html';
  e.waitUntil(self.clients.openWindow(url));
});
