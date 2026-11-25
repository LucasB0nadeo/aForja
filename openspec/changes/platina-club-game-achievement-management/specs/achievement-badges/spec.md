# Spec Delta

## Purpose

Recompensa o progresso de conquistas oficiais em cada jogo Steam com marcos graduais e uma Brasa do Ferreiro própria para cada jogo concluído.

## ADDED Requirements

### Requirement: Calcular progresso percentual por jogo
O sistema SHALL calcular o progresso de cada jogo Steam pela razão entre conquistas desbloqueadas e o total de conquistas definidas para aquele jogo.

#### Scenario: Jogo com conquistas definidas
- **WHEN** o progresso de um jogo Steam é atualizado
- **THEN** o sistema apresenta a porcentagem usando as conquistas definidas pela Steam como total

#### Scenario: Jogo sem conquistas definidas
- **WHEN** a Steam informa que um jogo não possui conquistas definidas
- **THEN** o sistema não divide por zero nem concede marcos percentuais para esse jogo

### Requirement: Conceder martelos por limiar de progresso
O sistema SHALL conceder para cada jogo Steam os martelos de 25%, 50%, 75% e 100% quando o progresso atingir ou ultrapassar cada limiar.

#### Scenario: Alcançar 25 por cento
- **WHEN** o progresso de um jogo atinge ou ultrapassa 25%
- **THEN** o sistema concede a insígnia “Faíscas de Cobre” para esse jogo

#### Scenario: Alcançar 50 por cento
- **WHEN** o progresso de um jogo atinge ou ultrapassa 50%
- **THEN** o sistema concede a insígnia “Martelo de Bronze do Aprendiz” para esse jogo

#### Scenario: Alcançar 75 por cento
- **WHEN** o progresso de um jogo atinge ou ultrapassa 75%
- **THEN** o sistema concede a insígnia “Martelo de Prata do Ferreiro” para esse jogo

#### Scenario: Alcançar 100 por cento
- **WHEN** o progresso de um jogo atinge 100%
- **THEN** o sistema concede a insígnia “Martelo de Ouro do Mestre” para esse jogo

#### Scenario: Sincronização salta vários limiares
- **WHEN** uma sincronização eleva o progresso de um jogo para além de mais de um limiar ainda não concedido
- **THEN** o sistema concede todos os martelos cujos limiares foram atingidos

### Requirement: Manter martelos já conquistados
O sistema SHALL manter permanentemente cada martelo concedido, mesmo que o progresso sincronizado do jogo diminua depois.

#### Scenario: Progresso diminui após concessão
- **WHEN** uma sincronização posterior mostra progresso abaixo de um limiar já conquistado
- **THEN** o sistema mantém a insígnia correspondente como conquistada

### Requirement: Conceder uma Brasa por jogo concluído
O sistema SHALL conceder uma Brasa do Ferreiro permanente para cada jogo Steam em que a pessoa alcance 100% das conquistas.

#### Scenario: Concluir um jogo pela primeira vez
- **WHEN** o progresso de um jogo alcança 100% e o Martelo de Ouro do Mestre é concedido
- **THEN** o sistema concede uma Brasa do Ferreiro associada àquele jogo

#### Scenario: Sincronizar novamente um jogo completo
- **WHEN** a pessoa sincroniza novamente um jogo que já possui 100% de progresso
- **THEN** o sistema mantém a Brasa existente sem criar uma duplicata para o mesmo jogo

#### Scenario: Sincronizar conquistas de todos os jogos
- **WHEN** a pessoa autenticada solicita a sincronização em lote pela biblioteca
- **THEN** o sistema tenta atualizar as conquistas de cada jogo Steam da conta e informa os sucessos e falhas sem descartar snapshots válidos

#### Scenario: Sincronizar toda a integração Steam
- **WHEN** a pessoa usa o botão único da biblioteca
- **THEN** o sistema atualiza a lista de jogos e, depois, tenta sincronizar as conquistas de todos os jogos Steam da conta

#### Scenario: Exibir raridade global e ícones Steam
- **WHEN** a Steam fornece o percentual global e os ícones das conquistas de um jogo
- **THEN** o sistema salva esses dados e mostra o percentual, o ícone desbloqueado ou cinza e mantém os dados ausentes como não disponíveis
