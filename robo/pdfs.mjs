// Gera em PDF os dossiês dos 27 estados, a partir da própria página dossie.html.
// Uso: node robo/pdfs.mjs <pasta de saída>
// Sobe um servidor local com o site, abre cada dossiê no Chromium e imprime em A4.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)('playwright');
const RAIZ = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const SAIDA = path.resolve(process.argv[2] || 'pdfs');
const UFS = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'];
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png' };

const servidor = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/+/, '') || 'index.html';
  const arq = path.join(RAIZ, rel);
  if (!arq.startsWith(RAIZ) || !fs.existsSync(arq) || fs.statSync(arq).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': TIPOS[path.extname(arq)] || 'application/octet-stream' });
  fs.createReadStream(arq).pipe(res);
});
await new Promise(r => servidor.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${servidor.address().port}`;

fs.mkdirSync(SAIDA, { recursive: true });
const navegador = await chromium.launch();
const falhas = [];
const ALVOS = [...UFS.map(uf => [uf, `tipo=estado&uf=${uf}`]), ['Congresso', 'tipo=balanco&casa=T']];
for (const [uf, consulta] of ALVOS) {
  const pagina = await navegador.newPage({ viewport: { width: 1200, height: 1600 } });
  const erros = [];
  pagina.on('pageerror', e => erros.push(e.message));
  try {
    await pagina.goto(`${base}/dossie.html?${consulta}`, { waitUntil: 'networkidle', timeout: 180000 });
    await pagina.waitForSelector('#folha .cab h1', { timeout: 120000 });
    await pagina.waitForTimeout(1500);
    const texto = await pagina.$eval('#folha', el => el.textContent);
    if (/não foi possível|erro/i.test(texto.slice(0, 400))) throw new Error('a página mostrou erro');
    await pagina.emulateMedia({ media: 'print' });
    await pagina.pdf({ path: path.join(SAIDA, `Dossie-${uf}.pdf`), format: 'A4', printBackground: true, preferCSSPageSize: true });
    const kb = Math.round(fs.statSync(path.join(SAIDA, `Dossie-${uf}.pdf`)).size / 1024);
    console.log(`${uf} ok, ${kb} KB${erros.length ? ' (avisos: ' + erros.join('; ').slice(0, 200) + ')' : ''}`);
  } catch (e) {
    falhas.push(uf);
    console.log(`${uf} FALHOU: ${e.message}`);
  }
  await pagina.close();
}
await navegador.close();
servidor.close();
if (falhas.length) { console.log('Estados com falha:', falhas.join(', ')); if (falhas.length > 3) process.exit(1); }
