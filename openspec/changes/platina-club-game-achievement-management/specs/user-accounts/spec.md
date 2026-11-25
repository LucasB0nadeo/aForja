# Spec Delta

## Purpose

Permite que cada pessoa tenha uma conta própria na Platina Club e que seus dados de jogos e conquistas permaneçam privados e separados dos dados das demais contas.

## ADDED Requirements

### Requirement: Cadastro de conta
O sistema SHALL permitir que uma pessoa crie uma conta usando um endereço de e-mail válido e uma senha, mantendo cada endereço de e-mail único.

#### Scenario: Cadastro válido
- **WHEN** uma pessoa envia um e-mail válido ainda não cadastrado e uma senha não vazia
- **THEN** o sistema cria uma conta persistente e autentica a pessoa nessa conta

#### Scenario: E-mail já cadastrado
- **WHEN** uma pessoa tenta se cadastrar com um endereço de e-mail já associado a uma conta
- **THEN** o sistema rejeita o cadastro e informa que os dados enviados precisam ser corrigidos

### Requirement: Autenticação e encerramento de sessão
O sistema SHALL permitir que uma pessoa autenticada acesse sua conta e encerre explicitamente a sessão.

#### Scenario: Credenciais válidas
- **WHEN** uma pessoa envia o e-mail e a senha correspondentes a uma conta existente
- **THEN** o sistema inicia uma sessão autenticada para essa conta

#### Scenario: Credenciais inválidas
- **WHEN** uma pessoa envia credenciais que não correspondem a uma conta
- **THEN** o sistema rejeita a autenticação e não inicia uma sessão

#### Scenario: Encerrar sessão
- **WHEN** uma pessoa autenticada solicita sair da conta
- **THEN** o sistema encerra a sessão e exige nova autenticação para acessar áreas protegidas

### Requirement: Isolamento dos dados da conta
O sistema SHALL restringir cada pessoa aos jogos e às conquistas associados à sua própria conta.

#### Scenario: Acesso aos próprios dados
- **WHEN** uma pessoa autenticada consulta sua biblioteca
- **THEN** o sistema apresenta somente jogos e conquistas pertencentes à conta dessa pessoa

#### Scenario: Tentativa de acesso aos dados de outra conta
- **WHEN** uma pessoa autenticada tenta consultar ou alterar um jogo ou conquista pertencente a outra conta
- **THEN** o sistema nega a operação sem revelar nem modificar os dados da outra conta

#### Scenario: Acesso sem autenticação
- **WHEN** uma pessoa sem sessão autenticada solicita uma área protegida da biblioteca
- **THEN** o sistema não apresenta nem altera dados da biblioteca e solicita autenticação
