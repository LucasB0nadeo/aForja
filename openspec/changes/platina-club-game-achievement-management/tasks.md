# Tasks

## 1. Aplicação e esquema SQLite

- [x] 1.1 Criar a estrutura inicial Flask, dependências e configuração local; verificar que a aplicação inicia com o guia de desenvolvimento.
- [x] 1.2 Criar o esquema SQLite versionado para contas, perfis, vínculo Steam, jogos, conquistas, marcos, Forja, coleções, avaliações, desejos e metas; verificar chaves estrangeiras, índices e restrições únicas em testes.

## 2. Contas e vínculo Steam

- [x] 2.1 Implementar cadastro, login, logout e sessão com hash de senha; verificar credenciais, e-mail duplicado e acesso não autenticado em testes.
- [x] 2.2 Implementar vínculo/desvínculo Steam por OpenID, validação do SteamID único e configuração de `STEAM_API_KEY`; verificar os fluxos com respostas Steam simuladas e documentar os requisitos de chave e privacidade.

## 3. Biblioteca e jogos Steam

- [x] 3.1 Implementar CRUD de jogos manuais e isolamento por conta; verificar validação, operações CRUD e rejeição de acessos cruzados em testes.
- [x] 3.2 Importar e atualizar sob demanda a lista de jogos Steam por AppID, sem duplicatas; verificar metadados somente para leitura, biblioteca privada, falha inicial e preservação de snapshots em testes com API simulada.
- [x] 3.3 Implementar CRUD de conquistas manuais e exclusão confirmada em cascata; verificar edição manual, confirmação/cancelamento e integridade referencial em testes.
- [x] 3.4 Documentar a biblioteca manual e Steam; verificar instruções para configurar a chave, vincular a conta e atualizar a lista importada.

## 4. Sincronização e recompensas

- [x] 4.1 Sincronizar definições e estados de conquistas Steam ao abrir o jogo ou por ação explícita; verificar snapshots, erros, dados desatualizados e jogos sem conquistas em testes.
- [x] 4.2 Calcular progresso e conceder martelos nos limiares de 25%, 50%, 75% e 100%; verificar ultrapassagem de limiares, permanência após queda e uma única Brasa por jogo 100% em testes.
- [x] 4.3 Documentar o fluxo de progresso e recompensas; verificar que as instruções distinguem dados oficiais Steam de conquistas manuais.

## 5. Coleções, avaliações e desejos

- [x] 5.1 Implementar CRUD de coleções e associações muitos-para-muitos com jogos próprios; verificar múltiplas coleções por jogo, remoção de associação, privacidade e exclusão sem apagar jogos em testes.
- [x] 5.2 Implementar avaliação privada única por usuário/AppID, com texto e nota de 1 a 5; verificar criação, consulta, edição, exclusão, duplicatas e isolamento em testes.
- [x] 5.3 Implementar lista de desejos por AppID com metadados Steam, prioridade 1–5 e observação; verificar duplicatas, atualização, exclusão e acesso cruzado em testes.
- [x] 5.4 Documentar coleções, avaliações e lista de desejos; verificar fluxos de uso e explicar que dados descritivos de jogos vêm da Steam.

## 6. Metas, perfil e Forja

- [x] 6.1 Implementar metas privadas com prazo e AppID opcionais e estado manual; verificar CRUD e que alterações não modificam conquistas Steam em testes.
- [x] 6.2 Implementar perfil com nome, bio e foto Steam padrão ou imagem substituta; verificar validação de arquivo, substituição da foto e privacidade do e-mail em testes.
- [x] 6.3 Implementar perfil de apresentação e Forja com seleção de até 9 Brasas conquistadas; verificar acesso público autenticado, limite, seleção e remoção sem revogar Brasas em testes.
- [x] 6.4 Documentar metas, perfil e Forja; verificar que o guia lista os dados visíveis e os que permanecem privados.

## 7. Integração final

- [x] 7.1 Executar os testes de integração com Steam simulada para cadastro → vínculo → importação → progresso → marcos → Brasa → Forja; verificar persistência, recuperação de falhas e isolamento.
- [x] 7.2 Executar a suíte completa e revisar o guia de inicialização local; verificar que os fluxos descritos funcionam sem sincronização em segundo plano ou serviços fora do escopo.
