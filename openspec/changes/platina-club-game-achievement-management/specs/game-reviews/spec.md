# Spec Delta

## Purpose

Permite que cada pessoa mantenha uma opinião privada sobre os jogos Steam, com texto e nota próprios, sem modificar os dados oficiais do jogo.

## ADDED Requirements

### Requirement: Criar e consultar avaliação pessoal
O sistema SHALL permitir que uma pessoa autenticada crie e consulte uma avaliação privada por jogo Steam e por conta Platina Club.

#### Scenario: Criar avaliação válida
- **WHEN** a pessoa pesquisa pelo nome, seleciona um jogo Steam e envia uma avaliação não vazia e uma nota inteira entre 1 e 5
- **THEN** o sistema salva a avaliação associada à conta e ao AppID correspondente

#### Scenario: Consultar avaliações próprias
- **WHEN** a pessoa consulta suas avaliações
- **THEN** o sistema apresenta somente as avaliações da conta autenticada

#### Scenario: Criar avaliação duplicada para o mesmo jogo
- **WHEN** a pessoa tenta criar outra avaliação para um AppID que já avaliou
- **THEN** o sistema rejeita a duplicata e permite que a pessoa edite a avaliação existente

### Requirement: Editar e excluir avaliação pessoal
O sistema SHALL permitir que a pessoa edite ou exclua sua avaliação sem alterar os dados descritivos do jogo obtidos da Steam.

#### Scenario: Atualizar avaliação
- **WHEN** a pessoa altera o texto ou a nota de uma avaliação própria com dados válidos
- **THEN** o sistema salva as alterações sem modificar o jogo Steam associado

#### Scenario: Excluir avaliação
- **WHEN** a pessoa solicita excluir uma avaliação própria
- **THEN** o sistema remove a avaliação e mantém os dados do jogo

### Requirement: Validar nota e privacidade da avaliação
O sistema SHALL rejeitar avaliações sem texto ou com nota fora do intervalo de 1 a 5 e SHALL manter avaliações privadas.

#### Scenario: Nota inválida
- **WHEN** a pessoa envia nota não inteira, menor que 1 ou maior que 5
- **THEN** o sistema rejeita a alteração e não persiste a avaliação inválida

#### Scenario: Outra pessoa tenta consultar avaliação
- **WHEN** uma pessoa tenta consultar uma avaliação pertencente a outra conta
- **THEN** o sistema nega o acesso sem revelar o texto nem a nota
