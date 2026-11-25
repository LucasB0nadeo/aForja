# Proposal

## Why

A Platina Club precisa permitir que cada pessoa organize sua biblioteca, acompanhe conquistas oficiais da Steam e construa uma jornada pessoal de jogos. Esta mudança amplia o CRUD acadêmico inicial com integração Steam, organização pessoal e um perfil de apresentação, mantendo os dados em SQLite.

## What Changes

- Manter contas próprias e importar a biblioteca Steam vinculada, com dados e conquistas oficiais sincronizados da Steam.
- Manter CRUD manual para jogos sem vínculo Steam e não permitir que dados importados alterem a fonte oficial.
- Conceder, por jogo, marcos permanentes ao atingir 25%, 50%, 75% e 100% das conquistas; cada jogo concluído em 100% concede uma Brasa do Ferreiro.
- Permitir coleções pessoais, avaliações privadas, lista de desejos baseada em dados Steam e metas acompanhadas manualmente.
- Oferecer perfil público customizável com nome, bio e foto; usar a foto Steam por padrão e permitir substituição pelo usuário.
- Criar a Forja do perfil para selecionar até 9 Brasas já conquistadas; manter avaliações, coleções, lista de desejos e metas privados.
- Persistir e validar os novos dados relacionais em SQLite, mantendo isolamento por conta e tratamento explícito de falhas de sincronização.

## Capabilities

### New Capabilities
- `user-accounts`: cadastro, autenticação e isolamento dos dados por conta.
- `game-library`: CRUD de jogos e conquistas pessoais, relacionamento entre eles e acompanhamento do desbloqueio.
- `steam-integration`: vínculo de conta Steam, importação da biblioteca e sincronização de conquistas.
- `achievement-badges`: marcos percentuais por jogo e concessão permanente de Brasas.
- `game-collections`: coleções pessoais e associação de vários jogos a várias coleções.
- `game-reviews`: avaliações privadas, uma por jogo e por usuário, com nota de 1 a 5.
- `wishlist`: lista pessoal de jogos Steam com prioridade e observação.
- `personal-goals`: objetivos pessoais com atualização manual, sem alterar dados oficiais da Steam.
- `user-profile`: perfil público customizável e Forja com seleção de Brasas.

### Modified Capabilities
- Nenhuma. O projeto ainda não possui capacidades arquivadas; todas as capacidades deste change são novas.

## Impact

- Aplicação web local Flask, templates HTML e esquema relacional SQLite.
- Steam OpenID e Steam Web API para SteamID, biblioteca, perfil e conquistas; a Web API key fica em variável de ambiente no servidor local.
- Novas telas para coleções, avaliações, desejos, metas, perfil e Forja.
- A visibilidade de jogos Steam depende das configurações de privacidade da biblioteca; falhas mantêm o último snapshot e informam o estado de sincronização.
- Nenhuma sincronização em segundo plano, catálogo social de avaliações ou alteração de conquistas na Steam.
