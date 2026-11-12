// Teste: onde a API da Câmara informa o relator de uma proposição.
// Uso: node robo/testar-relatores-camara.mjs "PL 2898/2025" "PL 5800/2026"
const API = 'https://dadosabertos.camara.leg.br/api/v2';
const alvos = process.argv.slice(2).length ? process.argv.slice(2) : ['PL 2898/2025', 'PL 1904/2024', 'PEC 66/2023', 'PL 5800/2026'];

async function pegar(url) {
  const r = await fetch(url, { headers: { accept: 'application/json', 'user-agent': 'exterminadores-teste' } });
  const t = await r.text();
  let j = null; try { j = JSON.parse(t); } catch (e) {}
  return { status: r.status, j, t };
}

for (const alvo of alvos) {
  const [, tipo, num, ano] = /^(\S+)\s+(\d+)\/(\d{4})$/.exec(alvo) || [];
  console.log(`\n==================== ${alvo}`);
  const busca = await pegar(`${API}/proposicoes?siglaTipo=${tipo}&numero=${num}&ano=${ano}`);
  const id = busca.j && busca.j.dados && busca.j.dados[0] && busca.j.dados[0].id;
  if (!id) { console.log('não encontrada', busca.status); continue; }
  console.log('id', id);

  const ficha = await pegar(`${API}/proposicoes/${id}`);
  const st = ficha.j && ficha.j.dados && ficha.j.dados.statusProposicao;
  console.log('-- statusProposicao:', JSON.stringify(st, null, 1));
  if (st && st.uriUltimoRelator) {
    const rel = await pegar(st.uriUltimoRelator);
    const d = rel.j && rel.j.dados;
    console.log('-- último relator:', d ? `${d.ultimoStatus && d.ultimoStatus.nome} (${d.ultimoStatus && d.ultimoStatus.siglaPartido}-${d.ultimoStatus && d.ultimoStatus.siglaUf}), id ${d.id}` : rel.status);
  }

  const rel2 = await pegar(`${API}/proposicoes/${id}/relatores`);
  console.log('-- /relatores:', rel2.status, rel2.t.slice(0, 600));

  const tram = await pegar(`${API}/proposicoes/${id}/tramitacoes`);
  const lista = (tram.j && tram.j.dados) || [];
  const comRelator = lista.filter(x => /relator/i.test(`${x.despacho || ''} ${x.descricaoTramitacao || ''}`));
  console.log(`-- tramitações: ${lista.length}, com "relator": ${comRelator.length}`);
  for (const x of comRelator.slice(0, 10)) console.log(`   ${String(x.dataHora).slice(0, 10)} | ${x.siglaOrgao} | ${x.descricaoTramitacao} | ${String(x.despacho || '').slice(0, 220)} | uriUltimoRelator=${x.uriUltimoRelator || ''}`);
}
