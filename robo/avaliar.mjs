// Mede quanto a IA concorda com a equipe, usando as correções já feitas como gabarito.
// Metade das correções vira exemplo e a outra metade vira prova, e depois se inverte.
// Uso: node robo/avaliar.mjs   (precisa de ANTHROPIC_API_KEY)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chamarClaude, instrucoesGrau, induzirRegras } from './coletar.mjs';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ler = f => JSON.parse(fs.readFileSync(path.join(RAIZ, f), 'utf8'));
const correcoes = ler('correcoes.json').correcoes;
const ia = ler('dados/classificacoes.json').c;
const ementa = new Map();
for (const f of fs.readdirSync(path.join(RAIZ, 'dados')).filter(f => /^proposicoes-\d{4}\.json$/.test(f)))
  for (const x of ler('dados/' + f).itens) ementa.set(x.c, x.e || '');

const gabarito = (k, c) => {
  const a = ia[k] || {};
  const s = c.s !== undefined ? c.s : (a.s || (a.fora || c.g || c.p ? 'avanca' : ''));
  if (s !== 'avanca') return 'fora';
  return (c.g || a.g || 'direita') === 'extrema' ? 'extrema' : 'direita';
};
const descreve = (k, c) => {
  const g = gabarito(k, c);
  if (g === 'fora') return c.s === 'barra' ? 'contra a pauta da direita' : 'não é pauta da direita';
  const pp = Array.isArray(c.p) ? c.p : [];
  return `${g === 'extrema' ? 'extrema-direita' : 'direita'}${pp.length ? ', pautas ' + pp.join(', ') : ''}`;
};
const casos = Object.entries(correcoes).filter(([k, c]) => c && typeof c === 'object' && ementa.get(k))
  .map(([k, c], i) => ({ k, c, g: gabarito(k, c), dobra: i % 2 }));
console.log(`Casos com gabarito: ${casos.length}`, JSON.stringify(casos.reduce((o, x) => (o[x.g] = (o[x.g] || 0) + 1, o), {})));

const CONFIGS = (process.env.CONFIGS || 'haiku-antigas,haiku-novas,sonnet-novas,opus-novas').split(',');
const MODELOS = { haiku: 'claude-haiku-5-5', sonnet: 'claude-sonnet-5-5', opus: 'claude-opus-5-5' };
const saida = {}; const induzidas = {}; let mostrou = false;
for (const cfg of CONFIGS) {
  const [m, r] = cfg.split('-'); const res = saida[cfg] = {};
  for (const dobra of [0, 1]) {
    const exemplos = casos.filter(x => x.dobra !== dobra).map(x => `- ${x.k}. ${String(ementa.get(x.k)).slice(0, 260)} => ${descreve(x.k, x.c)}`).join('\n');
    let regras = r === 'novas';
    if (r === 'induzidas' || r === 'so') {
      induzidas[dobra] = induzidas[dobra] || await induzirRegras(exemplos);
      regras = induzidas[dobra];
      if (dobra === 0 && !mostrou) { mostrou = true; console.log('\nREGRAS DEDUZIDAS (dobra 0)\n' + regras + '\n'); }
    }
    const sistema = instrucoesGrau(r === 'so' ? '' : exemplos, regras);
    const prova = casos.filter(x => x.dobra === dobra);
    const lotes = []; for (let i = 0; i < prova.length; i += 25) lotes.push(prova.slice(i, i + 25));
    for (let i = 0; i < lotes.length; i += 3) await Promise.all(lotes.slice(i, i + 3).map(async l => {
      const lista = l.map((x, n) => `${n + 1}. ${x.k}. ${String(ementa.get(x.k)).slice(0, 700)}`).join('\n');
      const out = await chamarClaude(sistema, 'ITENS\n' + lista, 1500 + l.length * 160, MODELOS[m]).catch(e => (console.log('erro', cfg, e.message), null));
      for (const x of out || []) { const it = l[(+x.n) - 1]; if (it) res[it.k] = { g: x.g === 'fora' ? 'fora' : x.g === 'extrema' ? 'extrema' : 'direita', c: x.c === 'alta' ? 'alta' : 'baixa' }; }
    }));
  }
  const fez = casos.filter(x => res[x.k]); const ok = fez.filter(x => res[x.k].g === x.g);
  const alta = fez.filter(x => res[x.k].c === 'alta'); const okAlta = alta.filter(x => res[x.k].g === x.g);
  console.log(`\n== ${cfg}: respondidos ${fez.length}, acordo ${ok.length} (${(100 * ok.length / fez.length).toFixed(1)}%)`);
  console.log(`   certeza alta ${alta.length} (${(100 * alta.length / fez.length).toFixed(0)}% dos casos), acordo dentro da alta ${okAlta.length} (${(100 * okAlta.length / (alta.length || 1)).toFixed(1)}%)`);
  const conf = {}; for (const x of fez) { const q = x.g + '>' + res[x.k].g; conf[q] = (conf[q] || 0) + 1; }
  console.log('   equipe>IA', JSON.stringify(conf));
}
// Consenso entre pares de modelos: quando dois concordam, quanto acertam e quanto sobra para a revisão.
const nomes = Object.keys(saida);
for (let i = 0; i < nomes.length; i++) for (let j = i + 1; j < nomes.length; j++) {
  const A = saida[nomes[i]], B = saida[nomes[j]];
  const amb = casos.filter(x => A[x.k] && B[x.k]); const cons = amb.filter(x => A[x.k].g === B[x.k].g); const ok = cons.filter(x => A[x.k].g === x.g);
  const forte = cons.filter(x => A[x.k].c === 'alta' || B[x.k].c === 'alta'); const okF = forte.filter(x => A[x.k].g === x.g);
  console.log(`\n== consenso ${nomes[i]} + ${nomes[j]}: concordam em ${cons.length} de ${amb.length} (${(100 * cons.length / amb.length).toFixed(0)}%), acordo com a equipe ${(100 * ok.length / (cons.length || 1)).toFixed(1)}%`);
  console.log(`   concordam e ao menos um com certeza alta ${forte.length} (${(100 * forte.length / amb.length).toFixed(0)}%), acordo ${(100 * okF.length / (forte.length || 1)).toFixed(1)}%`);
}
fs.writeFileSync(path.join(RAIZ, 'avaliacao.json'), JSON.stringify({ casos: casos.map(x => ({ k: x.k, g: x.g })), saida }));
