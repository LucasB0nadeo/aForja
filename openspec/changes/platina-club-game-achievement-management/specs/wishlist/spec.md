# Spec Delta

## Purpose

Permite que cada pessoa mantenha uma lista privada de jogos Steam que pretende comprar ou jogar, usando os dados oficiais do catálogo Steam.

## ADDED Requirements

### Requirement: Adicionar e consultar itens da lista de desejos
O sistema SHALL permitir que uma pessoa autenticada adicione jogos identificados por AppID Steam à sua lista privada e consulte seus itens.

#### Scenario: Buscar e adicionar jogo Steam pelo nome
- **WHEN** a pessoa pesquisa pelo nome e seleciona um jogo Steam válido que ainda não está em sua lista
- **THEN** o sistema salva o AppID correspondente e apresenta os dados descritivos obtidos da Steam

#### Scenario: Consultar lista de desejos
- **WHEN** a pessoa abre sua lista de desejos
- **THEN** o sistema apresenta somente seus itens e os respectivos dados Steam

#### Scenario: Adicionar jogo já listado
- **WHEN** a pessoa tenta adicionar novamente o mesmo AppID
- **THEN** o sistema mantém um único item para esse jogo e informa que ele já está na lista

### Requirement: Atualizar prioridade e observação
O sistema SHALL permitir que a pessoa altere a prioridade e a observação de um item próprio sem alterar os dados do jogo obtidos da Steam.

#### Scenario: Atualizar item da lista
- **WHEN** a pessoa altera a prioridade para um inteiro entre 1 e 5 e atualiza a observação
- **THEN** o sistema salva os dados pessoais e mantém os dados Steam do jogo inalterados

### Requirement: Excluir item da lista de desejos
O sistema SHALL permitir que a pessoa remova um item de sua própria lista sem excluir o jogo da biblioteca Steam ou do Platina Club.

#### Scenario: Remover item
- **WHEN** a pessoa solicita remover um item de sua lista de desejos
- **THEN** o sistema remove somente esse item da lista

### Requirement: Validar itens e manter privacidade
O sistema SHALL rejeitar AppIDs ou prioridades inválidos e SHALL impedir que uma pessoa consulte ou altere a lista de outra conta.

#### Scenario: AppID ou prioridade inválida
- **WHEN** a pessoa envia um AppID inexistente ou prioridade fora do intervalo de 1 a 5
- **THEN** o sistema rejeita a operação e mantém a lista sem alterações

#### Scenario: Acesso à lista de outra pessoa
- **WHEN** uma pessoa tenta consultar ou alterar um item de outra conta
- **THEN** o sistema nega o acesso sem revelar os dados pessoais da lista
