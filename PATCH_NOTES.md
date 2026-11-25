# Patch Notes - FORJA / Platina Club

> Histórico consolidado a partir da proposta OpenSpec, das migrações SQLite, da documentação e das sessões de desenvolvimento. O projeto não possui changelog versionado ou tags Git neste snapshot, portanto as entradas são organizadas por data conhecida e não representam números oficiais de versão.

## 24/11/2026

### Novidades

- Adicionados rankings públicos:
  - Brasas conquistadas no total, no mês atual e na semana atual.
  - Conquistas desbloqueadas no total, no mês atual e na semana atual.
- Adicionada a opção de privacidade da posição no ranking.
- Perfis privados, com privacidade de amigos ou sem acesso público, saíram dos rankings públicos.
- Implementados os melhores registros históricos e a posição atual nos rankings mundiais de Brasas e conquistas.
- Substituído o identificador textual “F” do cabeçalho pela foto do usuário.
- Integrado ao HowLongToBeat:
  - Estimativas de história principal, extras, complecionista e outros estilos.
  - Estatísticas carregadas automaticamente a partir da página de estatísticas do jogo.
- Unificada a pesquisa Steam com as estatísticas da comunidade da FORJA e do HowLongToBeat.
- Substituído o bloco de avaliações Steam por um botão direto **Abrir na Steam**.
- A listagem de amigos passou a incluir pedidos recebidos, envio de pedidos, aprovação, recusa, cancelamento e remoção.

### Correções

- Corrigida a quebra de layout da biografia com textos longos e sequências sem espaços.
- Corrigido o vazamento de caracteres para fora dos cartões do perfil.
- Corrigida a ausência de `g.user` na navegação da página inicial.
- Corrigido o erro de inicialização causado pela dependência `fake-useragent` não instalada no ambiente virtual do projeto.
- Removida a consulta a um endpoint de avaliações da Steam que devolvia HTML em vez de JSON, eliminando a mensagem falsa de avaliações indisponíveis.
- Corrigido o fluxo para localizar ou adicionar manualmente jogos gratuitos ausentes na importação da biblioteca Steam.

## 22/11/2026

### Novidades

- Expandida a aba **Metas** com resumo de metas totais, em andamento e concluídas.
- Cada meta passou a aceitar vários jogos.
- Adicionado CRUD individual de jogos associados a uma meta.
- Melhorados os cartões, prazos, estados vazios e layouts responsivos das metas.

### Correções

- Impedidas metas associadas a jogos duplicados.
- Reforçado o isolamento entre metas de contas diferentes.

## 24/11/2026 - Perfil e privacidade

### Novidades

- A aba **Perfil e Forja** passou a abrir diretamente o perfil público.
- O atalho foi movido para o topo da seção **Sua Oficina**, acima de **Painel**.
- Adicionadas opções de privacidade:
  - Todos.
  - Apenas amigos.
  - Ninguém.
- Adicionado o compartilhamento e a cópia discreta do link do perfil.
- Implementado o grid visual de nove posições da Forja.
- Adicionadas prévia ao vivo, contadores de caracteres e sincronização manual da foto Steam.
- Persistida a posição das Brasas dentro da Forja.
- Adicionadas estatísticas públicas ao perfil.

### Correções

- Corrigido o posicionamento do botão de copiar perfil no cabeçalho.
- Corrigida a referência usada pela navegação em páginas que não carregam o usuário completo no contexto global.

## 24/11/2026 - Pesquisa e estatísticas de jogos

### Novidades

- Criada a página **Pesquisar jogos**.
- Pesquisa de jogos no catálogo Steam com resultados locais da FORJA.
- Exibição da média das avaliações da comunidade da FORJA.
- Exibição da porcentagem de cada conquista desbloqueada pelos jogadores da FORJA.
- Exibição da taxa global de desbloqueio das conquistas quando fornecida pela Steam.
- Adicionado suporte para abrir o jogo na Steam.
- Permitida a adição manual de jogos ausentes da sincronização automática.

### Correções

- Corrigida a inicialização da página quando o usuário não estava carregado em `g.user`.
- Removida a dependência funcional das avaliações Steam em JSON para não bloquear os dados da FORJA.
- Mantidos os dados Steam e os dados da FORJA disponíveis mesmo com falha no HowLongToBeat.

## Base funcional inicial

### Contas e segurança

- Cadastro, login, logout e sessões Flask.
- Senhas armazenadas com hash.
- Validação de e-mail duplicado e credenciais.
- Bloqueio de acesso anônimo e isolamento dos dados por conta.
- Consultas parametrizadas e chaves estrangeiras SQLite habilitadas.

### Biblioteca e Steam

- CRUD de jogos manuais por conta.
- Identificação de jogos Steam por AppID.
- Vinculação e desvinculação de conta Steam por OpenID.
- Compartilhamento seguro do mesmo SteamID entre contas sem compartilhar bibliotecas ou progresso.
- Importação da biblioteca Steam sem duplicar jogos.
- Sincronização sob demanda da biblioteca e das conquistas.
- Preservação do último snapshot válido em caso de falha.
- Estado explícito para dados não sincronizados ou desatualizados.
- Proteção da chave Steam Web API em variável de ambiente.

### Conquistas e recompensas

- CRUD de conquistas manuais.
- Importação das definições e estados oficiais de conquistas Steam.
- Cálculo de progresso por porcentagem desbloqueada.
- Concessão permanente nos marcos de 25%, 50%, 75% e 100%.
- Uma Brasa por jogo concluído em 100%.
- Permanência dos martelos e da Brasa após queda de progresso ou retirada do snapshot.
- Exclusão em cascata de jogos com confirmação.

### Recursos pessoais

- Coleções privadas com associação muitos-para-muitos entre jogos.
- Avaliações privadas únicas por usuário e jogo, com nota de 1 a 5.
- Lista de desejos por AppID Steam, prioridade de 1 a 5 e observação opcional.
- Metas pessoais com prazo e jogo opcional.
- Atualização manual de metas sem alterar conquistas da Steam.

### Perfil e Forja

- Nome de exibição, biografia e foto personalizável.
- Foto da Steam como padrão e imagem substituta quando não houver foto.
- Perfil de apresentação visível apenas para usuários autenticados conforme a privacidade.
- Biblioteca, avaliações, coleções, desejos e metas mantidos privados.
- Seleção de até nove Brasas já conquistadas.
- A remoção da Forja não revoga recompensas.

## Migrações estruturais

- `001_initial_schema.sql`: base inicial de contas, jogos, conquistas e dados pessoais.
- `002_steam_catalog.sql`: catálogo e integração inicial da Steam.
- `003_steam_avatar.sql`: avatar da Steam no perfil.
- `004_shared_steam_accounts.sql`: vínculo do mesmo SteamID a várias contas FORJA.
- `005_achievement_global_stats.sql`: estatísticas globais de conquistas.
- `006_refresh_achievement_metadata.sql`: atualização dos metadados de conquistas.
- `007_goal_games.sql`: relação de vários jogos com uma meta.
- `008_profile_privacy_and_friendships.sql`: privacidade e sistema de amizades.
- `009_ember_ranking_records.sql`: melhor posição histórica no ranking de Brasas.
- `010_profile_ranking_visibility.sql`: opção de mostrar ou ocultar a posição no ranking.
- `011_achievement_ranking_records.sql`: melhor posição histórica no ranking de conquistas.

## Validações registradas

- O histórico de sessões registra a suíte completa com 105 testes após a integração inicial do HowLongToBeat.
- Adições posteriores registraram validações com até 107 testes.
- Os testes cobrem isolamento por usuário, privacidade, sincronização simulada da Steam, falhas e preservação de snapshots, rankings, amizades e operações CRUD.
