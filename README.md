# aForja

# FORJA

Aplicação web local para organizar jogos, acompanhar conquistas e registrar a jornada de cada pessoa. O projeto usa Flask e SQLite.

## Requisitos

- Python 3.11 ou superior
- PowerShell no Windows

## Executar localmente

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
$env:STEAM_API_KEY = "SUA_CHAVE_REAL_DA_STEAM"
python -m flask --app platina_club:create_app init-db
python -m flask --app platina_club:create_app run --debug
```

Abra `http://127.0.0.1:5000/` no navegador. Gere uma nova `SECRET_KEY` para cada ambiente; não a salve no repositório. O banco SQLite local será armazenado em `instance/platina-club.sqlite3` por padrão. Para escolher outro caminho, defina `PLATINA_DATABASE`.

## Configuração da Steam

O vínculo usa Steam OpenID e não solicita nem armazena a senha Steam. Para o desenvolvimento local, o callback padrão é `http://127.0.0.1:5000/steam/callback`. Se o endereço ou a porta da aplicação forem diferentes, configure `STEAM_OPENID_RETURN_URL` para o callback correspondente.

A chave da Steam Web API é necessária para importar a biblioteca (e será usada pela sincronização de conquistas), mas não para iniciar o vínculo OpenID. Defina-a no mesmo ambiente PowerShell antes de iniciar o servidor:

```powershell
$env:STEAM_API_KEY = "SUA_CHAVE_DA_STEAM"
```

Mantenha a chave somente no ambiente local; não a coloque no repositório, no banco visível ao usuário ou no navegador. Sem a chave, a aplicação informa que a sincronização Web API não está configurada.

A mesma conta Steam pode ser vinculada a mais de uma conta FORJA. A biblioteca e o progresso são importados separadamente para cada conta FORJA e continuam privados.

## Biblioteca de jogos

Depois de entrar, abra a biblioteca para cadastrar jogos manualmente ou consultar os jogos importados da Steam. Os jogos aparecem em cartões com a capa acima do nome, cinco por linha em telas largas. Abaixo do nome, jogos com conquistas mostram o percentual concluído e a contagem desbloqueada/total. A biblioteca pode ser ordenada por nome A-Z, porcentagem de conclusão ou data da última conquista, em ordem crescente ou decrescente. Quando o progresso ainda não foi sincronizado ou não há conquistas, o cartão informa o estado sem inventar um percentual. Jogos Steam usam as capas públicas do catálogo; jogos manuais sem capa exibem um substituto. Jogos manuais podem ser editados e excluídos; suas conquistas manuais podem ser criadas, editadas e excluídas na página do jogo.

Para importar jogos da Steam:

1. Configure `STEAM_API_KEY` e inicie a aplicação.
2. Na área da conta, escolha vincular a Steam e conclua a autorização no site da Steam.
3. A biblioteca é importada após o vínculo. No final da página da biblioteca, use **Sincronizar Steam** para atualizar a biblioteca e todas as conquistas em uma única operação.

Os jogos importados são identificados pelo AppID e seus dados Steam são somente para leitura enquanto vinculados. Se uma sincronização falhar, a aplicação mantém o último snapshot válido e informa o erro/estado desatualizado, em vez de substituir a biblioteca por uma lista vazia. Desvincular a Steam não apaga os snapshots importados.

Na aba **Pesquisar jogos**, busque um jogo Steam para consultar a média das avaliações da comunidade da Forja, as estatísticas de conquistas e as estimativas de conclusão do HowLongToBeat. Os tempos do HowLongToBeat são carregados automaticamente em segundo plano por uma fonte comunitária não oficial, que pode ficar indisponível. A página também permite abrir o jogo na loja Steam ou adicioná-lo manualmente à biblioteca quando a sincronização automática não o incluir. As insígnias mostram a porcentagem entre jogadores da Forja com conquistas sincronizadas para aquele jogo; a tabela de conquistas também pode mostrar a taxa global de desbloqueio informada pela Steam.

## Progresso e recompensas

Ao abrir os detalhes de um jogo Steam, a aplicação sincroniza as conquistas se ainda não houver um snapshot ou se a última sincronização bem-sucedida tiver mais de 15 minutos. Também é possível solicitar uma atualização manual. Uma falha mantém o snapshot anterior como desatualizado; uma falha inicial é mostrada como erro, não como progresso zero. Jogos sem conquistas definidas não recebem percentual nem marcos.

Na página de conquistas, cada conquista Steam pode mostrar seu ícone desbloqueado ou cinza e o percentual aproximado de jogadores globais que a desbloquearam. Esses dados vêm da Steam e ficam vazios quando a API não os disponibiliza.

O progresso é calculado somente com as conquistas oficiais importadas da Steam. Conquistas cadastradas manualmente não contam para os marcos. Os limiares por jogo são:

- 25%: Faíscas de Cobre
- 50%: Martelo de Bronze do Aprendiz
- 75%: Martelo de Prata do Ferreiro
- 100%: Martelo de Ouro do Mestre e uma Brasa do Ferreiro

Os martelos e Brasas são permanentes: sincronizações posteriores que indiquem menos progresso não removem recompensas, e novas sincronizações não duplicam uma Brasa do mesmo jogo. As recompensas também são preservadas se o snapshot do jogo for removido depois do desvínculo Steam.

## Recursos pessoais

No painel, use **Minhas coleções** para criar coleções privadas, editar nome/descrição e selecionar jogos da sua biblioteca. Um jogo pode aparecer em várias coleções; excluir uma coleção remove somente as associações, não o jogo.

Em **Minhas avaliações**, pesquise pelo nome do jogo, selecione a opção correta, escreva uma opinião e dê uma nota de 1 a 5. Cada conta mantém uma avaliação privada por jogo e pode editá-la ou removê-la. A aplicação valida o jogo no catálogo público da Steam; título e outros metadados são somente leitura.

Em **Lista de desejos**, pesquise pelo nome do jogo, selecione a opção correta e registre prioridade de 1 a 5 e uma observação opcional. A lista é privada; duplicatas mantêm um único item e exibem uma mensagem. Os dados descritivos vêm do catálogo Steam e não podem ser alterados pela pessoa usuária.

## Metas, perfil e Forja

Em **Minhas metas**, crie objetivos pessoais, como concluir um jogo, com prazo e jogo opcional pesquisado pelo nome. O andamento é atualizado manualmente e não altera as conquistas sincronizadas da Steam.

O perfil usa o nome de exibição, bio e foto definidos pela pessoa. Quando não há foto personalizada, usa a imagem da Steam vinculada ou a imagem padrão. Em **Editar perfil**, é possível substituir a foto; o e-mail da conta não é exibido no perfil.

Perfis de apresentação são visíveis para pessoas autenticadas e mostram somente o nome de exibição, bio, foto e Brasas selecionadas. Biblioteca, avaliações, coleções, lista de desejos e metas permanecem privadas. Em **Gerenciar Forja**, selecione até nove Brasas do Ferreiro já conquistadas. Remover uma Brasa da Forja altera apenas a seleção de destaque: não revoga a recompensa conquistada.

## Testes

```powershell
python -m unittest discover -s tests
```
