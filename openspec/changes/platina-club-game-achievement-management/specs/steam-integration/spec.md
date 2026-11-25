# Spec Delta

## Purpose

Conecta uma conta Platina Club a uma conta Steam e usa dados oficiais da Steam para importar jogos e acompanhar conquistas sem alterar o progresso original.

## ADDED Requirements

### Requirement: Vincular e desvincular conta Steam
O sistema SHALL permitir que uma pessoa autenticada vincule sua própria conta Steam sem solicitar nem armazenar sua senha Steam.

#### Scenario: Vínculo confirmado pela Steam
- **WHEN** a pessoa conclui a confirmação de identidade no fluxo Steam
- **THEN** o sistema associa o SteamID confirmado à conta Platina Club autenticada

#### Scenario: Conta Steam vinculada a várias contas Platina Club
- **WHEN** a pessoa confirma um SteamID já associado a outra conta Platina Club
- **THEN** o sistema associa o SteamID à conta autenticada sem expor dados das outras contas

#### Scenario: Desvincular conta Steam
- **WHEN** a pessoa solicita desvincular sua conta Steam
- **THEN** o sistema interrompe futuras sincronizações e preserva os jogos, conquistas importados e Brasas já conquistadas como dados locais
- **AND** mantém inalterados os vínculos desse SteamID com outras contas Platina Club

### Requirement: Importar biblioteca de jogos Steam
O sistema SHALL importar para a biblioteca da pessoa os jogos retornados pela Steam, identificando cada jogo pelo AppID e usando a Steam como fonte dos dados descritivos.

#### Scenario: Importação inicial da biblioteca
- **WHEN** a pessoa conclui o vínculo Steam e a biblioteca está visível para a integração
- **THEN** o sistema importa os jogos disponíveis e apresenta seus dados Steam na biblioteca da pessoa

#### Scenario: Atualizar lista da biblioteca sob demanda
- **WHEN** a pessoa solicita uma nova importação da biblioteca Steam
- **THEN** o sistema atualiza a lista importada sem duplicar jogos com o mesmo AppID

#### Scenario: Dados da biblioteca Steam indisponíveis
- **WHEN** a Steam não disponibiliza a lista de jogos da conta vinculada
- **THEN** o sistema informa que a biblioteca não pôde ser sincronizada e mantém os dados locais já existentes

### Requirement: Sincronizar conquistas de jogo Steam
O sistema SHALL obter da Steam a definição das conquistas e o estado desbloqueado de cada jogo importado, sem permitir edição manual desses dados enquanto o vínculo estiver ativo.

#### Scenario: Abrir progresso de jogo Steam
- **WHEN** a pessoa abre o progresso de um jogo importado que ainda não foi sincronizado ou cuja sincronização está vencida
- **THEN** o sistema solicita os dados atuais de conquistas à Steam e apresenta o progresso sincronizado

#### Scenario: Solicitar sincronização de jogo
- **WHEN** a pessoa solicita atualizar as conquistas de um jogo Steam
- **THEN** o sistema busca novamente as conquistas e estados daquele jogo e atualiza o snapshot local

#### Scenario: Falha após sincronização anterior
- **WHEN** a Steam ou a Web API falha ao sincronizar um jogo que possui dados salvos
- **THEN** o sistema mantém o último snapshot, informa que os dados estão desatualizados e permite nova tentativa

#### Scenario: Falha antes da primeira sincronização
- **WHEN** a Steam ou a Web API falha antes de haver dados de conquistas salvos para um jogo
- **THEN** o sistema informa que o jogo ainda não foi sincronizado e não apresenta a falha como progresso zero

#### Scenario: Conquista de jogo não vinculado à Steam
- **WHEN** a pessoa consulta ou atualiza uma conquista de um jogo sem vínculo Steam
- **THEN** o sistema mantém o comportamento de gerenciamento manual definido para a biblioteca pessoal

### Requirement: Proteger a configuração da Steam Web API
O sistema SHALL manter a chave necessária para chamadas da Web API fora dos dados visíveis ao usuário e SHALL informar quando ela não estiver configurada.

#### Scenario: Chave Web API ausente
- **WHEN** a integração tenta sincronizar dados sem uma chave Web API configurada
- **THEN** o sistema não executa a chamada e apresenta uma indicação de configuração ausente sem revelar segredos
