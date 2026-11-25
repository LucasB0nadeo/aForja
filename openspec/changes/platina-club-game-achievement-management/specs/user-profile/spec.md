# Spec Delta

## Purpose

Permite que cada pessoa apresente uma identidade própria no Platina Club, escolha quem pode visualizar o perfil e compartilhe seu link.

## ADDED Requirements

### Requirement: Customizar perfil pessoal
O sistema SHALL permitir que a pessoa altere seu nome de exibição, bio curta e foto de perfil.

#### Scenario: Perfil vinculado à Steam sem foto personalizada
- **WHEN** a pessoa vinculou uma conta Steam e não definiu uma foto própria
- **THEN** o sistema usa como foto de perfil a imagem retornada pela Steam

#### Scenario: Substituir foto padrão
- **WHEN** a pessoa envia uma foto de perfil válida
- **THEN** o sistema usa a foto escolhida pela pessoa em vez da imagem Steam

#### Scenario: Editar nome e bio
- **WHEN** a pessoa altera seu nome de exibição ou bio
- **THEN** o sistema salva os dados no perfil próprio sem expor o e-mail da conta

### Requirement: Exibir perfil público de apresentação
O sistema SHALL permitir que pessoas autenticadas visualizem o perfil de apresentação de outra conta quando a configuração de privacidade permitir, sem expor seus dados pessoais privados.

#### Scenario: Consultar perfil de outra pessoa
- **WHEN** uma pessoa autenticada abre um perfil configurado para Todos
- **THEN** o sistema apresenta somente nome de exibição, bio, foto e Forja selecionada

#### Scenario: Dados privados não são exibidos
- **WHEN** uma pessoa consulta o perfil público de outra conta
- **THEN** o sistema não apresenta avaliações, coleções, lista de desejos, metas ou biblioteca privada

### Requirement: Controlar privacidade do perfil
O sistema SHALL permitir que a pessoa escolha entre Todos os usuários conectados, Apenas Amigos ou Ninguém, mantendo o acesso da própria pessoa ao seu perfil.

#### Scenario: Perfil disponível para todos
- **WHEN** uma pessoa escolhe Todos
- **THEN** qualquer usuário conectado pode visualizar seu perfil

#### Scenario: Perfil disponível somente para amigos
- **WHEN** uma pessoa escolhe Apenas Amigos
- **THEN** somente a própria pessoa e contas com amizade aceita podem visualizar o perfil

#### Scenario: Perfil privado
- **WHEN** uma pessoa escolhe Ninguém
- **THEN** somente a própria pessoa pode visualizar o perfil

#### Scenario: Bloquear acesso a perfil e avatar
- **WHEN** uma pessoa sem permissão tenta abrir um perfil ou o arquivo de avatar correspondente
- **THEN** o sistema não revela os dados do perfil nem serve o avatar

### Requirement: Compartilhar perfil e gerenciar amizades
O sistema SHALL permitir copiar o link do perfil e enviar, aceitar, recusar, cancelar ou remover amizades para controlar o acesso de perfis configurados como Apenas Amigos.

#### Scenario: Copiar link do perfil
- **WHEN** a pessoa usa a opção de compartilhar em um perfil visível
- **THEN** o sistema copia o endereço do perfil para a área de transferência ou permite copiá-lo manualmente

#### Scenario: Solicitar amizade
- **WHEN** uma pessoa envia um pedido de amizade
- **THEN** o destinatário pode aceitar ou recusar o pedido, e a amizade só é estabelecida após aceitação

#### Scenario: Remover amizade
- **WHEN** uma das pessoas remove uma amizade aceita
- **THEN** a relação deixa de conceder acesso a perfis configurados como Apenas Amigos

### Requirement: Exibir Forja de Brasas
O sistema SHALL exibir no perfil uma Forja que contém somente Brasas do Ferreiro já conquistadas e selecionadas pela pessoa, limitada a nove itens.

#### Scenario: Selecionar Brasas conquistadas
- **WHEN** a pessoa seleciona até nove Brasas associadas a jogos que completou em 100%
- **THEN** o sistema salva a seleção e apresenta essas Brasas na Forja pública

#### Scenario: Tentar selecionar Brasa não conquistada
- **WHEN** a pessoa tenta colocar na Forja uma Brasa ainda não conquistada
- **THEN** o sistema rejeita a seleção e mantém a Forja inalterada

#### Scenario: Ultrapassar o limite da Forja
- **WHEN** a pessoa tenta selecionar mais de nove Brasas
- **THEN** o sistema rejeita a seleção excedente e mantém no máximo nove itens

#### Scenario: Remover Brasa da Forja
- **WHEN** a pessoa remove uma Brasa selecionada
- **THEN** o sistema atualiza a Forja sem revogar a Brasa conquistada
