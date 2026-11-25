# Design

## Context

O repositório não contém aplicação, dependências ou dados existentes. O escopo aprovado é uma aplicação web local com dados isolados por conta. Consulte a proposta e as specs do change para os comportamentos completos.

## Goals / Non-Goals

**Goals:**
- Integrar a biblioteca Steam sem expor credenciais ou permitir que o Platina Club escreva na Steam.
- Manter os dados pessoais e de progresso em SQLite, com propriedade e privacidade verificadas no servidor.
- Dar suporte aos recursos de organização e perfil descritos nas specs, preservando uma implementação demonstrável localmente.

**Non-Goals:**
- Sincronização Steam em segundo plano ou implantação com alta disponibilidade.
- Publicar avaliações, coleções, lista de desejos, metas ou a biblioteca pessoal.
- Alterar conquistas, estatísticas ou outros dados na Steam.

## Decisions

### Aplicação web local renderizada no servidor

Manter Flask com templates Jinja e HTML/CSS simples para cadastro, login, biblioteca, recursos pessoais, perfil e Forja. A renderização no servidor permite a integração OpenID e chamadas Steam Web API em um único processo; uma SPA e uma API separada acrescentariam complexidade sem necessidade para a demonstração local.

### Persistência relacional com SQLite e `sqlite3`

Usar o módulo `sqlite3` do Python e SQL explícito, em vez de adicionar um ORM ou um servidor de banco. Isso deixa as relações e operações CRUD visíveis para fins acadêmicos. Usar consultas parametrizadas e habilitar `PRAGMA foreign_keys = ON` em cada conexão.

O esquema relacional deverá incluir:

- `users` e `profiles`: credenciais de conta separadas de nome de exibição, bio e caminho de foto personalizada.
- `steam_links`: cada conta Platina Club pode ter um SteamID, e o mesmo SteamID pode ser vinculado a várias contas Platina Club.
- `games`: registros por usuário com origem manual ou Steam; jogos Steam guardam AppID e metadados em cache, e jogos manuais guardam nome, plataforma, desenvolvedora e ano.
- `achievements`: conquistas vinculadas a um jogo; jogos manuais guardam estado editável, enquanto jogos Steam guardam chave/definição e estado importados.
- `badge_awards`: marcos permanentes por usuário, jogo e tipo; uma Brasa por jogo concluído.
- `forja_slots`: seleção ordenada de no máximo nove Brasas já conquistadas por perfil.
- `collections` e `collection_games`: coleções pertencentes ao usuário e associação muitos-para-muitos apenas entre registros do mesmo usuário.
- `game_reviews`: uma avaliação privada por usuário e AppID Steam, com texto e nota inteira de 1 a 5.
- `wishlist_entries`: uma entrada por usuário e AppID Steam, com prioridade de 1 a 5 e observação opcional; metadados vêm da Steam.
- `personal_goals`: objetivo, prazo opcional, AppID opcional e estado alterável manualmente.

Usar chaves estrangeiras, índices e restrições únicas para impedir duplicatas por usuário/AppID, avaliações duplicadas e mais de uma concessão do mesmo marco por jogo. A propriedade das conquistas é derivada do jogo; associações e operações ainda devem validar que o registro pai pertence à conta autenticada.

### Vínculo e sincronização Steam

Usar Steam OpenID no navegador para confirmar o SteamID e vinculá-lo à conta Platina Club autenticada; não solicitar nem armazenar senha Steam. Fazer chamadas à Steam Web API somente no servidor. Configurar a Web API key em `STEAM_API_KEY` no ambiente local, nunca no repositório, banco visível ao usuário ou navegador.

Ao vincular a conta, importar a lista de jogos retornada por `IPlayerService/GetOwnedGames`, guardando AppID e metadados Steam. Disponibilizar nova importação sob demanda. Buscar esquema e estados de conquistas (`ISteamUserStats/GetSchemaForGame` e `GetPlayerAchievements`) quando a pessoa abrir o progresso de um jogo ou pedir sincronização manual; não criar worker nem polling periódico.

Steam pode não disponibilizar a biblioteca se os detalhes de jogos estiverem privados. A interface deve mostrar o estado “não sincronizado”/“desatualizado” e uma mensagem de correção; uma falha depois de sincronização bem-sucedida preserva o último snapshot, e uma falha inicial nunca aparece como zero conquistas. Registrar status e horário da última sincronização. Se a conta for desvinculada, parar novas chamadas e manter snapshots e Brasas; os snapshots locais podem ser removidos pelo CRUD após o desvínculo.

Tratar dados da Steam como somente leitura enquanto vinculados. Não atualizar snapshots com respostas parciais ou falhas. Cachear resultados para evitar chamadas repetidas desnecessárias; sincronização manual deve permitir nova tentativa.

### Cálculo de marcos e Brasas

Calcular progresso por jogo Steam como conquistas desbloqueadas divididas pelo total de conquistas da definição Steam. Ao sincronizar, conceder todos os marcos cujos limites foram atingidos ou ultrapassados: 25%, 50%, 75% e 100%. Com zero conquistas definidas, não calcular percentual nem conceder martelos. Concessões são idempotentes e permanentes; cada jogo com 100% gera uma Brasa própria. A Forja apenas seleciona quais até nove Brasas conquistadas serão apresentadas.

Se a pessoa desvincular a Steam e depois excluir o snapshot local de um jogo, manter seus martelos e sua Brasa como recompensas permanentes. A concessão deve conservar AppID e nome do jogo como identificação histórica e não depender da existência do registro em `games`; uma seleção dessa Brasa na Forja continua válida.

### Perfil, recursos pessoais e privacidade

Armazenar a foto enviada pelo usuário como substituição da foto Steam; sem substituição, usar a imagem do perfil Steam vinculado (ou imagem padrão quando não houver vínculo). Validar tipo e tamanho de imagem e guardar o arquivo localmente fora de caminhos fornecidos diretamente pelo usuário.

Exibir para pessoas autenticadas somente nome de exibição, bio, foto e Brasas selecionadas na Forja do perfil de outra pessoa. Avaliações, coleções, desejos, metas e biblioteca continuam privados. Coleções usam tabela de junção; avaliações e desejos referenciam AppID sem permitir editar metadados Steam; metas usam estado manual e nunca atualizam conquistas oficiais.

### Autenticação, validação e isolamento

Usar sessões Flask e guardar somente hashes de senha. A chave de sessão deve vir de configuração externa ao código. Filtrar cada consulta e mutação pelos IDs da conta autenticada; não confiar em IDs do navegador como prova de propriedade.

Validar no servidor todos os campos: entradas textuais obrigatórias após remoção de espaços, nota e prioridade como inteiros no intervalo 1–5, e datas de prazo válidas. Respostas externas da Steam também devem ser tratadas explicitamente; não persistir conteúdo parcial como se fosse uma sincronização bem-sucedida.

## Risks / Trade-offs

- [Biblioteca ou estatísticas Steam privadas, chave ausente ou API indisponível] → Mostrar estado de sincronização, conservar snapshot anterior e documentar requisitos de visibilidade e configuração.
- [Respostas Steam podem estar incompletas ou variar entre jogos] → Validar respostas, distinguir ausência de dados de zero progresso e cobrir jogos sem conquistas em testes.
- [Chamadas excessivas podem sofrer limites ou aumentar a espera] → Sincronizar sob demanda, cachear resultados e não fazer varredura periódica.
- [Dados de perfil ou avaliações podem escapar para outras contas] → Separar perfil público de tabelas privadas e testar acessos cruzados.
- [Exclusão em cascata pode remover dados pessoais] → Exigir confirmação para jogos com conquistas e testar confirmação/cancelamento.
- [SQLite permite concorrência de escrita limitada] → Adequado ao escopo local e acadêmico; não declarar suporte a operação hospedada de alta concorrência.

## Migration Plan

Não há aplicação nem dados existentes a migrar. Criar o banco SQLite local com esquema versionado para permitir evolução durante a implementação. Antes de qualquer migração destrutiva futura, preservar cópia do arquivo do banco; rollback inicial consiste em restaurar essa cópia e manter a conta Steam vinculada para nova sincronização.
