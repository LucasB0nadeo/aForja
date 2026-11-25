# Spec Delta

## Purpose

Permite que cada pessoa organize sua própria biblioteca de jogos e conquistas, mantendo os dados persistentes e o progresso de desbloqueio associado à conquista correta.

## ADDED Requirements

### Requirement: CRUD de jogos pessoais
O sistema SHALL permitir CRUD de jogos gerenciados manualmente e consulta dos jogos importados da Steam, usando os campos nome, plataforma, desenvolvedora e ano de lançamento para jogos manuais.

#### Scenario: Criar jogo
- **WHEN** a pessoa envia dados válidos para um novo jogo gerenciado manualmente
- **THEN** o sistema persiste o jogo associado à conta dessa pessoa

#### Scenario: Consultar jogos
- **WHEN** a pessoa autenticada abre sua biblioteca
- **THEN** o sistema apresenta os jogos pertencentes à conta dessa pessoa em cartões com capa acima do nome, organizados em cinco colunas em telas largas e ajustados a telas menores

#### Scenario: Jogo sem capa disponível
- **WHEN** um jogo não possui uma capa Steam disponível
- **THEN** o sistema apresenta uma capa substituta sem ocultar o nome nem as ações do jogo

#### Scenario: Exibir progresso de conquistas na biblioteca
- **WHEN** um jogo possui um snapshot de conquistas
- **THEN** o cartão apresenta uma barra com o percentual desbloqueado e a contagem de conquistas desbloqueadas sobre o total

#### Scenario: Jogo sem snapshot de conquistas
- **WHEN** um jogo Steam ainda não foi sincronizado ou não possui conquistas definidas
- **THEN** o cartão informa o estado sem apresentar um percentual de progresso incorreto

#### Scenario: Editar jogo
- **WHEN** a pessoa envia alterações válidas para um jogo próprio gerenciado manualmente
- **THEN** o sistema persiste as alterações sem modificar os dados de outras contas

#### Scenario: Consultar jogo importado da Steam
- **WHEN** a pessoa consulta um jogo Steam enquanto sua conta Steam está vinculada
- **THEN** o sistema apresenta os dados recebidos da Steam sem permitir sua edição ou exclusão manual

#### Scenario: Tentar excluir jogo Steam vinculado
- **WHEN** a pessoa tenta excluir um jogo importado enquanto sua conta Steam está vinculada
- **THEN** o sistema rejeita a exclusão e mantém o snapshot sincronizado

#### Scenario: Excluir jogo sem conquistas
- **WHEN** a pessoa confirma a exclusão de um jogo próprio gerenciado manualmente sem conquistas associadas
- **THEN** o sistema remove o jogo de sua biblioteca

#### Scenario: Excluir snapshot Steam após desvincular
- **WHEN** a pessoa desvincula a Steam e confirma a exclusão de um jogo importado mantido como snapshot local
- **THEN** o sistema remove somente os dados locais do jogo e suas conquistas, sem alterar dados na Steam

### Requirement: CRUD de conquistas pessoais
O sistema SHALL permitir CRUD manual de conquistas para jogos gerenciados manualmente e consulta das conquistas importadas da Steam.

#### Scenario: Criar conquista
- **WHEN** a pessoa envia nome, descrição e raridade válidos para um jogo próprio gerenciado manualmente
- **THEN** o sistema persiste a conquista vinculada ao jogo selecionado e com seu estado de desbloqueio inicial

#### Scenario: Consultar conquistas
- **WHEN** a pessoa consulta as conquistas de um de seus jogos
- **THEN** o sistema apresenta as conquistas vinculadas àquele jogo e seus estados de desbloqueio

#### Scenario: Editar conquista
- **WHEN** a pessoa envia alterações válidas para uma conquista de um jogo próprio gerenciado manualmente
- **THEN** o sistema persiste as alterações na conquista selecionada

#### Scenario: Consultar conquista importada da Steam
- **WHEN** a pessoa consulta uma conquista de jogo Steam enquanto sua conta Steam está vinculada
- **THEN** o sistema apresenta a definição e o estado sincronizados sem permitir edição manual

#### Scenario: Excluir conquista
- **WHEN** a pessoa confirma a exclusão de uma conquista de um jogo próprio gerenciado manualmente
- **THEN** o sistema remove somente a conquista selecionada

#### Scenario: Tentar excluir conquista Steam vinculada
- **WHEN** a pessoa tenta excluir uma conquista importada enquanto sua conta Steam está vinculada
- **THEN** o sistema rejeita a exclusão e mantém os dados sincronizados

### Requirement: Relacionamento entre jogos e conquistas
O sistema SHALL associar cada conquista a exatamente um jogo e SHALL permitir que um jogo tenha várias conquistas.

#### Scenario: Associar conquista a jogo próprio
- **WHEN** a pessoa cria uma conquista e seleciona um jogo de sua biblioteca
- **THEN** a conquista fica vinculada àquele jogo

#### Scenario: Tentar associar conquista a jogo de outra conta
- **WHEN** a pessoa tenta associar uma conquista a um jogo que não pertence à sua conta
- **THEN** o sistema rejeita a operação e mantém os dados inalterados

### Requirement: Exclusão de jogo com conquistas
O sistema SHALL solicitar confirmação antes de excluir um jogo manual ou snapshot Steam desvinculado que possua conquistas e SHALL remover essas conquistas somente quando a exclusão for confirmada.

#### Scenario: Confirmar exclusão em cascata
- **WHEN** a pessoa confirma a exclusão de um jogo manual ou snapshot Steam desvinculado que possui conquistas
- **THEN** o sistema remove o jogo e todas as conquistas vinculadas a ele

#### Scenario: Cancelar exclusão em cascata
- **WHEN** a pessoa cancela a confirmação para excluir um jogo manual ou snapshot Steam desvinculado que possui conquistas
- **THEN** o sistema mantém o jogo e todas as suas conquistas sem alterações

### Requirement: Validação dos dados da biblioteca
O sistema SHALL rejeitar dados incompletos ou inválidos para jogos e conquistas e SHALL informar que a pessoa precisa corrigir a entrada.

#### Scenario: Dados inválidos de jogo
- **WHEN** a pessoa envia um jogo sem nome, plataforma, desenvolvedora ou com ano de lançamento que não seja um inteiro positivo
- **THEN** o sistema rejeita o cadastro ou edição e não persiste os dados inválidos

#### Scenario: Dados inválidos de conquista
- **WHEN** a pessoa envia uma conquista sem nome, descrição ou raridade
- **THEN** o sistema rejeita o cadastro ou edição e não persiste os dados inválidos

### Requirement: Persistência da biblioteca
O sistema SHALL manter jogos, conquistas e estados de desbloqueio persistidos entre sessões da aplicação.

#### Scenario: Retomar biblioteca após nova sessão
- **WHEN** a pessoa encerra sua sessão e depois autentica novamente
- **THEN** o sistema apresenta seus jogos, conquistas e estados de desbloqueio anteriormente salvos

### Requirement: Estado de desbloqueio da conquista
O sistema SHALL permitir alteração manual do estado de conquistas de jogos gerenciados manualmente e consulta do estado sincronizado para jogos Steam.

#### Scenario: Atualizar estado de desbloqueio
- **WHEN** a pessoa marca uma conquista de jogo gerenciado manualmente como desbloqueada ou bloqueada
- **THEN** o sistema salva e apresenta o novo estado sem alterar as demais conquistas

#### Scenario: Consultar estado Steam sem edição manual
- **WHEN** a pessoa consulta o estado de uma conquista importada enquanto sua conta Steam está vinculada
- **THEN** o sistema apresenta o último estado sincronizado e não permite alterá-lo manualmente
