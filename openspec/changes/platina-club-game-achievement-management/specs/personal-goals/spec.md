# Spec Delta

## Purpose

Permite que cada pessoa defina objetivos pessoais para sua jornada de jogos e acompanhe manualmente seu andamento sem modificar conquistas oficiais importadas da Steam.

## ADDED Requirements

### Requirement: Criar e consultar metas pessoais
O sistema SHALL permitir que uma pessoa autenticada crie metas privadas com objetivo, prazo opcional e estado inicial de andamento.

#### Scenario: Criar meta com jogo opcional
- **WHEN** a pessoa envia uma descrição válida e, opcionalmente, um prazo e um jogo Steam selecionado pela busca de nome
- **THEN** o sistema salva a meta com o AppID correspondente e estado inicial “em andamento”

#### Scenario: Consultar metas
- **WHEN** a pessoa abre sua área de metas
- **THEN** o sistema apresenta somente as metas da conta autenticada e seus prazos e estados

### Requirement: Atualizar meta manualmente
O sistema SHALL permitir que a pessoa altere o objetivo, o prazo opcional e o estado de uma meta própria.

#### Scenario: Alterar objetivo ou prazo
- **WHEN** a pessoa edita o objetivo ou o prazo de uma meta própria com dados válidos
- **THEN** o sistema salva as alterações sem modificar as conquistas importadas do jogo

#### Scenario: Atualizar andamento
- **WHEN** a pessoa marca uma meta própria como “em andamento” ou “concluída”
- **THEN** o sistema atualiza somente o estado manual da meta

### Requirement: Excluir meta pessoal
O sistema SHALL permitir que a pessoa exclua uma meta própria sem alterar jogos ou conquistas associados.

#### Scenario: Remover meta
- **WHEN** a pessoa solicita excluir uma meta própria
- **THEN** o sistema remove somente a meta

### Requirement: Manter metas privadas
O sistema SHALL impedir que uma pessoa consulte ou altere metas pertencentes a outra conta.

#### Scenario: Acesso a meta de outra pessoa
- **WHEN** uma pessoa tenta consultar ou alterar uma meta de outra conta
- **THEN** o sistema nega o acesso sem revelar os dados da meta
