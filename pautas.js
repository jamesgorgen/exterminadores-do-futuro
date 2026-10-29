// Pautas da direita e da extrema-direita monitoradas pelo observatório.
// O mesmo arquivo é usado pela página (window.PAUTAS) e pelo robô de coleta (require).
//
// Cada pauta tem
// - id, nome curto e descrição do que entra
// - extrema: o que faz uma proposição ou votação dessa pauta ser classificada como extrema-direita
//
// Grau
// - direita: agenda conservadora ou liberal na economia, defendida dentro das regras democráticas
// - extrema-direita: ataca a democracia e as instituições, suprime direitos fundamentais de grupos,
//   propõe punições cruéis, armamentismo amplo, criminalização de opositores e movimentos, ou negacionismo científico
//
// O grau vale para a proposição ou para a votação, nunca para a pessoa.

(function (raiz) {
  'use strict';

  const PAUTAS = {
    versao: '2026-10-29',

    // Partidos que formam o núcleo do campo monitorado. A posição do bloco em cada votação
    // é a da maioria dos votos dos parlamentares desses partidos.
    nucleo: ['PL', 'NOVO', 'PP', 'UNIAO', 'REPUBLICANOS', 'PODE'],
    // Partido usado como referência do campo do governo para identificar votações disputadas.
    referenciaGoverno: ['PT'],
    // Regras do índice de alinhamento.
    indice: {
      coesaoMinima: 0.6,       // o bloco e a referência precisam votar ao menos 60% num mesmo sentido
      votacoesMinimas: 10,     // abaixo disso o índice não é exibido
      alinhado: 0.8,           // 80% ou mais de votos com o bloco = alinhado
      proximo: 0.6             // de 60% a 80% = próximo
    },

    lista: [
      { id: 'armas', nome: 'Armas e munições',
        descricao: 'Flexibilização do porte e da posse de armas, ampliação de categorias com direito a arma, CACs e clubes de tiro, redução de controle e rastreamento de armas e munições.',
        extrema: 'Armamento amplo da população, fim do Estatuto do Desarmamento, arma como instrumento de defesa política ou contra o Estado.' },
      { id: 'punitivismo', nome: 'Punitivismo e militarização da segurança',
        descricao: 'Endurecimento penal como resposta principal e redução de garantias. Redução da maioridade penal, fim da saída temporária, restrição de progressão de regime e de audiência de custódia, prisão preventiva como regra, aumento genérico de penas, ampliação de poderes e de excludentes para policiais, militarização da segurança. Não entram novos crimes ou penas para proteger mulheres, crianças, idosos, pessoas com deficiência, minorias ou vítimas de crimes digitais, nem medidas de prevenção e de inteligência.',
        extrema: 'Pena de morte, prisão perpétua, castração química, excludente de ilicitude amplo, licença para matar, uso das Forças Armadas na segurança pública como regra.' },
      { id: 'instituicoes', nome: 'Anistia e ataque às instituições',
        descricao: 'Limitação de poderes do STF e do TSE, impeachment de ministros, mudanças nas regras eleitorais que favorecem o próprio campo, voto impresso.',
        extrema: 'Anistia aos atos golpistas de 8 de janeiro e a quem tentou o golpe, intervenção militar, uso do art. 142 como poder moderador, descrédito das urnas, perseguição a juízes.' },
      { id: 'costumes', nome: 'Gênero, sexualidade, aborto e família',
        descricao: 'Projetos contra a chamada ideologia de gênero, linguagem neutra, banheiros e esportes para pessoas trans, restrições ao aborto legal, Estatuto do Nascituro, definição restritiva de família.',
        extrema: 'Proibição do casamento homoafetivo, criminalização da identidade de gênero, fim do aborto em caso de estupro ou risco de vida, terapia de conversão.' },
      { id: 'religiao', nome: 'Religião e Estado',
        descricao: 'Benefícios fiscais e imunidades para igrejas, ensino religioso, símbolos religiosos em espaços públicos, criação de crimes por ofensa religiosa.',
        extrema: 'Subordinação de leis e políticas públicas a preceitos religiosos, perseguição a religiões de matriz africana.' },
      { id: 'educacao', nome: 'Escola sem partido e militarização da educação',
        descricao: 'Escola sem partido, escolas cívico-militares, educação domiciliar, controle de conteúdo pedagógico, vouchers e transferência de recursos públicos para escolas privadas.',
        extrema: 'Censura e punição de professores, denúncia de docentes por alunos e famílias, proibição de temas como gênero e racismo.' },
      { id: 'ambiente', nome: 'Desregulação ambiental e climática',
        descricao: 'Flexibilização do licenciamento ambiental, liberação de agrotóxicos, enfraquecimento do Código Florestal e da fiscalização, anistia a desmatadores, incentivo ao garimpo.',
        extrema: 'Negação da crise climática, desmonte de órgãos ambientais, liberação de garimpo e mineração em áreas protegidas.' },
      { id: 'povos', nome: 'Povos indígenas e comunidades tradicionais',
        descricao: 'Marco temporal, abertura de terras indígenas à mineração, ao garimpo e ao agronegócio, restrições a demarcações e a territórios quilombolas.',
        extrema: 'Fim das demarcações, suspensão de homologações e revisão de terras já demarcadas, marco temporal, retirada da consulta prévia e de direitos constitucionais dos povos indígenas.' },
      { id: 'movimentos', nome: 'Criminalização de movimentos sociais',
        descricao: 'Endurecimento contra ocupações de terra e de imóveis, restrições ao direito de greve e de protesto, controle de ONGs e entidades da sociedade civil.',
        extrema: 'Tipificação de movimentos sociais ou de ocupações de terra como terrorismo, prisão de manifestantes, proibição de protestos.' },
      { id: 'trabalho', nome: 'Direitos trabalhistas e previdenciários',
        descricao: 'Retirada de direitos trabalhistas, negociado sobre o legislado, enfraquecimento de sindicatos e da fiscalização, oposição à redução da jornada, cortes em aposentadorias e benefícios.',
        extrema: 'Fim da Justiça do Trabalho, flexibilização do combate ao trabalho escravo e infantil.' },
      { id: 'estado', nome: 'Privatização e desmonte do Estado',
        descricao: 'Privatização de estatais e serviços públicos, reforma administrativa que reduz servidores e serviços, cortes de gasto social, regras fiscais que limitam políticas públicas.',
        extrema: 'Entrega de empresas e setores estratégicos sem controle nacional, extinção de órgãos de fiscalização e controle.' },
      { id: 'privilegios', nome: 'Privilégios fiscais e econômicos',
        descricao: 'Desonerações e benefícios fiscais sem contrapartida, perdão de dívidas de setores econômicos, proteção de grandes fortunas, de dividendos e de setores como o agronegócio e o sistema financeiro.',
        extrema: 'Anistia a sonegadores e a crimes contra a ordem tributária em larga escala.' },
      { id: 'plataformas', nome: 'Plataformas digitais e desinformação',
        descricao: 'Oposição à moderação de conteúdo e à responsabilização das plataformas por conteúdos ilegais, enfraquecimento do combate à desinformação e ao discurso de ódio em nome da liberdade de expressão. Temas de dados, nuvem, infraestrutura e poder econômico das big techs ficam na pauta de soberania nacional e digital.',
        extrema: 'Proteção legal à desinformação eleitoral e ao discurso de ódio, punição a quem combate a desinformação.' },
      { id: 'igualdade', nome: 'Cotas e igualdade racial',
        descricao: 'Fim ou restrição das cotas raciais e de ações afirmativas, enfraquecimento de políticas de igualdade racial.',
        extrema: 'Negação do racismo estrutural com retirada de proteções legais contra o racismo.' },
      { id: 'drogas', nome: 'Política de drogas proibicionista',
        descricao: 'Endurecimento da Lei de Drogas, criminalização do porte para uso, internação compulsória, financiamento de comunidades terapêuticas.',
        extrema: 'Internação forçada em massa e punição penal de usuários como política principal.' },
      { id: 'soberania', nome: 'Soberania nacional e digital',
        descricao: 'Entrega de recursos estratégicos ao controle estrangeiro (petróleo e pré-sal, minerais críticos e terras raras, energia, água, terras, Alcântara e bases militares), alinhamento automático a governos estrangeiros em política externa, comercial e de defesa, oposição à integração regional e aos BRICS, fim de exigências de conteúdo local e de política industrial nacional. Inclui soberania digital, como oposição a dados e nuvem sob jurisdição brasileira, à tributação e à regulação econômica das big techs estrangeiras, a infraestrutura digital e inteligência artificial nacionais, e a dependência tecnológica do exterior. Privatizações e concessões em geral ficam na pauta de privatização; marque esta só quando o projeto entregar explicitamente o controle a estrangeiros ou abrir mão de controle nacional sobre recurso ou tecnologia estratégica.',
        extrema: 'Defesa de sanções, tarifas ou interferência estrangeira contra o próprio país ou suas instituições, apoio a governos estrangeiros contra decisões da Justiça brasileira, venda de terras, recursos ou infraestrutura estratégica sem nenhum controle nacional.' }
    ]
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = PAUTAS;
  else raiz.PAUTAS = PAUTAS;
})(typeof window !== 'undefined' ? window : globalThis);
