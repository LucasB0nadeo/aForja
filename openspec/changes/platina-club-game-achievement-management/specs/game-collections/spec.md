# Spec Delta

## Purpose

Permite que cada pessoa organize seus jogos em coleções privadas com nomes e descrições próprios, sem duplicar nem alterar os registros dos jogos.

## ADDED Requirements

### Requirement: Criar e consultar coleções pessoais
O sistema SHALL permitir que uma pessoa autenticada crie coleções e consulte somente as coleções de sua própria conta.

#### Scenario: Criar coleção
- **WHEN** a pessoa envia um nome válido e uma descrição para uma nova coleção
- **THEN** o sistema salva a coleção associada à conta dessa pessoa

#### Scenario: Consultar coleções
- **WHEN** a pessoa abre sua área de coleções
- **THEN** o sistema apresenta somente suas coleções e os jogos associados a cada uma

### Requirement: Editar coleção pessoal
O sistema SHALL permitir que a pessoa altere o nome e a descrição de uma coleção própria.

#### Scenario: Atualizar nome e descrição
- **WHEN** a pessoa envia um nome e uma descrição válidos para uma coleção própria
- **THEN** o sistema salva os novos valores sem alterar os jogos associados

### Requirement: Associar jogos próprios às coleções
O sistema SHALL permitir que um jogo da conta seja associado a várias coleções próprias e que uma coleção contenha vários jogos próprios.

#### Scenario: Associar jogos a coleções
- **WHEN** a pessoa adiciona seus jogos a uma ou mais de suas coleções
- **THEN** o sistema apresenta cada associação nas coleções correspondentes sem criar cópias dos jogos

#### Scenario: Remover jogo de coleção
- **WHEN** a pessoa remove um jogo próprio de uma coleção própria
- **THEN** o sistema remove somente a associação e mantém o jogo na biblioteca

#### Scenario: Associar jogo de outra conta
- **WHEN** a pessoa tenta adicionar a uma coleção um jogo que não pertence à sua conta
- **THEN** o sistema rejeita a associação sem revelar nem alterar os dados da outra conta

### Requirement: Excluir coleção pessoal
O sistema SHALL permitir que a pessoa exclua uma coleção própria sem excluir os jogos associados.

#### Scenario: Excluir coleção
- **WHEN** a pessoa confirma a exclusão de uma coleção própria
- **THEN** o sistema remove a coleção e suas associações, mantendo os jogos na biblioteca
