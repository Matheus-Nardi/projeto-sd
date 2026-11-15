# Cluster de validação

O caminho principal usa Windows com Vagrant e VirtualBox, VMs Ubuntu 24.04
e Ansible executado dentro de cada VM (`ansible_local`). O WSL não é necessário
para subir as VMs. O cluster em containers usa a mesma role Ansible.

## Preparação no host

Instale Vagrant e VirtualBox para Windows e valide a virtualização do provedor.
No host de desenvolvimento, VirtualBox 7.2.22 e Vagrant 2.4.9 foram instalados
via WinGet em 15/11/2026. Ambos responderam à consulta de versão e
`vagrant validate` aprovou o projeto no Windows. O instalador do Vagrant pediu
reinicialização, que foi adiada; as VMs subiram normalmente mesmo assim.
A configuração padrão está em `infra/cluster.json`: mestre e dois workers,
1 vCPU e 2048 MiB por VM, total de 3 vCPUs e 6144 MiB.
A box candidata é `bento/ubuntu-24.04`, versão `202510.26.0`, com provedor
VirtualBox amd64; o boot foi validado (ver evidências).

Na raiz do projeto, no PowerShell:

```powershell
python -m scripts.cluster.preparar
vagrant validate
vagrant up --provider=virtualbox
python -m scripts.cluster.conectar
python -m scripts.cluster.validar
```

O primeiro comando verifica rotas IPv4, RAM disponível, CPUs e espaço livre antes
de gerar arquivos em `.cluster/`. Reserva 2 GiB de RAM para o host e exige ao
menos 10 GiB livres por VM nos volumes consultados (repositório, boxes e pasta de
VMs). Consulta a pasta padrão no VBoxManage quando disponível; sem ele, assume
`~/VirtualBox VMs`, que deve ser conferido se a instalação usar outro local.
A rota padrão é ignorada na busca de conflitos.
Em Linux, o verificador usa `ip` e `/proc/meminfo`.

Para escolher outra topologia **antes de criar as VMs**:

```powershell
python -m scripts.cluster.preparar --workers 1 --cpus 1 --memory-mb 2048
python -m scripts.cluster.preparar --workers 4 --subnet 192.168.57.0/24
```

Execute apenas o comando da topologia desejada. Depois de subir as VMs, preserve
a configuração gerada. O verificador acusa a rede do próprio VirtualBox como
conflito se for executado novamente; ele não tenta assumir propriedade de uma
rede existente. Alterar o JSON não remove VMs de uma topologia anterior.

`vagrant up` configura cada nó independentemente. A etapa `scripts.cluster.conectar` só
deve rodar depois que todos terminarem. Ela usa `vagrant ssh` para obter as chaves
públicas de host e da conta exclusiva `mpi`, grava somente material público em
`.cluster/trust.json` e aplica `infra/ansible/conectar.yml` localmente em cada nó.
Chaves privadas ficam em `/home/mpi/.ssh/id_ed25519` de cada nó; não são copiadas
ao host. As chaves de gerenciamento do próprio Vagrant ficam em `.vagrant/`,
que não é compartilhado com as VMs. Apenas `infra`, `src`, `scripts`, `tests`,
`.cluster` e `dados` (quando existente) são montados sob `/vagrant`, somente leitura.

A conta `mpi` autoriza as contas do cluster, usa `BatchMode` e verificação estrita
dos hosts conhecidos. `authorized_keys`, `known_hosts` e o arquivo de configuração
SSH dessa conta são gerenciados integralmente. Não use essa conta para acesso pessoal.
Ao recriar uma VM, repita a coleta explícita de confiança.

## Diretórios e entrada

- `/vagrant`: diretórios selecionados do projeto, somente leitura, incluindo dados do host.
- `/opt/projeto-sd/code`: cópia do código em disco Linux.
- `/opt/projeto-sd/dados`: entradas preparadas em disco Linux.
- `/opt/projeto-sd/resultados`: resultados locais.
- `/opt/projeto-sd/hostfile`: mestre primeiro, depois workers; slots conforme vCPUs.
- `/opt/projeto-sd/versions.json`: versões efetivamente instaladas.

Todos usam `/usr/bin/python3` e os pacotes Ubuntu `openmpi-bin` e `python3-mpi4py`.
O validador exige versões iguais nos nós; o repositório não fixa versões de pacotes
APT nem garante instalações idênticas em datas diferentes. Não use a pasta
compartilhada para medir leitura dos dados.

Entre no mestre com `vagrant ssh master`. Execute **dentro da VM**:

```bash
sudo ansible-playbook /vagrant/infra/ansible/dados.yml \
  -i /vagrant/.cluster/inventory-local/master.ini \
  -e cluster_data_source=/vagrant/dados/enem_2023_real.csv
cd /opt/projeto-sd/code
sudo -u mpi /usr/bin/python3 -m src.sequencial \
  /opt/projeto-sd/dados/enem_2023_real.csv \
  --saida /opt/projeto-sd/resultados/sequencial.json
```

A preparação mostra SHA-256 e tamanho; deve ficar fora das medições.
Para coletar o resultado, volte ao PowerShell e execute:

```powershell
vagrant ssh master -c 'cat /opt/projeto-sd/resultados/sequencial.json' > .cluster/sequencial.json
```

O PowerShell 5 pode gravar essa redireção em UTF-16; a saída original da aplicação
na VM é UTF-8. Para verificar a idempotência das VMs, repita `vagrant provision`
e `python -m scripts.cluster.conectar`. Nenhuma chave deve ser recriada.

## Validação isolada com Docker

Estes comandos são para o shell Linux/WSL, com Docker funcionando:

```bash
docker build -t projeto-sd-infra-test -f infra/tests/Dockerfile infra/tests
python3 -m scripts.cluster.testar_infra --workers 2
```

O executor congela as fontes em um diretório temporário ignorado pelo Git,
cria uma rede e containers com nomes exclusivos, aplica os playbooks
duas vezes, exige `changed=0` na segunda execução, compara versões, verifica SSH
por nome/IP entre todos os nós, prepara a fixture em disco Linux e executa o smoke MPI.
Remove apenas os containers e a rede
criados por essa execução, inclusive quando um teste falha.

O smoke testa broadcast, envio/resposta ponto a ponto, rank zero no mestre e
um processo em cada hostname esperado. O lançamento tem limite de 45 segundos
e mais 5 segundos para encerramento forçado. Um caso negativo deve retornar
erro sem atingir o timeout. Containers têm SSH iniciado diretamente; o teste
não cobre o serviço systemd, VirtualBox, pasta compartilhada do Vagrant ou boot.
O limite de execução detecta travamentos; não constitui recuperação de falhas.
Em VMs, após um timeout, confira os processos da conta dedicada antes de repetir
a execução. A limpeza de containers do teste isolado encerra seus processos.

## Evidências nas VMs (15/11/2026)

- `vagrant up` concluído com a box `bento/ubuntu-24.04` `202510.26.0`: mestre e
  dois workers em execução. `python -m scripts.cluster.validar` aprovado: versões
  iguais (Python 3.12.3, mpi4py 3.1.5, Open MPI 4.1.6), SSH entre todos os nós e
  smoke MPI com um rank por VM.
- O aviso `plm:rsh: Warning: setpgid failed` do Open MPI aparece no stderr e é
  inofensivo. O PowerShell 5 o exibe como erro (`NativeCommandError`) quando a
  saída é redirecionada; o código de saída continua zero.
- Suíte completa dentro do mestre, incluindo processos MPI reais: 44 testes aprovados.
- CSV real (3.933.955 registros, 119 MB) em disco Linux, blocos de 10.000 linhas,
  um processo por VM. Todas as saídas idênticas byte a byte à sequencial:

  | Execução | Tempo (s) | Tarefas por worker |
  |---|---|---|
  | Sequencial | 28,8 | n/a |
  | MPI, 1 worker | 34,5 | 394 |
  | MPI estática, 2 workers | 18,3 | 197 / 197 |
  | MPI dinâmica, 2 workers | 17,5 | 198 / 196 |
  | Estática, worker 1 com atraso de 50 ms por tarefa | 27,5 | 197 / 197 |
  | Dinâmica, mesmo atraso | 21,1 | 150 / 244 |

  Medição única e exploratória: as VMs dividem a CPU do mesmo computador. Os
  números mostram funcionamento, não speedup.
- Arquivo inexistente entre nós: erro imediato e nenhum processo pendurado.

Depois de alterar o código, copie-o novamente para os nós com
`vagrant provision --provision-with ansible_local`.

## Cluster em containers Docker (WSL)

Ambiente rápido para desenvolver e ensaiar experimentos neste computador. Usa a
imagem `infra/docker/Dockerfile` (Ubuntu 24.04 com Open MPI e mpi4py já
instalados) e a mesma role Ansible das VMs. Comandos no shell Linux/WSL:

```bash
python3 -m scripts.cluster.docker subir --workers 8      # recria o cluster (menos de 3 min)
python3 -m scripts.cluster.docker dados dados/enem_2023_real.csv
python3 -m scripts.cluster.docker executar -- python3 -m unittest discover -s tests
python3 -m scripts.cluster.docker atualizar              # recopia o código para os nós
python3 -m scripts.cluster.docker derrubar
```

`executar` roda no mestre, como `mpi`, em `/opt/projeto-sd/code`; o hostfile é o
mesmo `/opt/projeto-sd/hostfile`. Para copiar resultados de volta:
`docker cp projeto-sd-cluster-master:/opt/projeto-sd/resultados/NOME resultados/NOME`.
Só os containers e a rede com o rótulo `projeto-sd-cluster` são removidos.

Limites: containers dividem o kernel e a CPU do computador e a rede é uma ponte
virtual. Servem para funcionamento, ensaio e curvas de speedup; falha de
máquina inteira continua sendo assunto das VMs.

### Por que o VirtualBox é lento neste host

Com o WSL2 ativo, o Windows mantém o Hyper-V ligado e o VirtualBox não acessa a
virtualização do processador diretamente: o log da VM registra
`HM: Attempting fall back to NEM: VT-x is not available`. Nesse modo, VMs com
1 vCPU funcionaram de forma estável (48 execuções), mas com 2 vCPUs uma VM travou
no boot e outra perdeu a conexão durante um job MPI. Mantenha 1 vCPU por VM.
A topologia foi ampliada para mestre + 4 workers com
`python -m scripts.cluster.preparar --workers 4 --memory-mb 4096 --rede-existente`
(a opção nova pula a verificação de rotas quando a sub-rede já é do cluster);
essa topologia de 5 VMs foi provisionada, mas ainda não validada nem medida.
`vagrant up` cria as VMs em série; para ganhar tempo, lance um
`vagrant up NOME --provision` por VM, com alguns segundos de intervalo.

### Experimentos em Docker (15/11/2026)

CSV real, blocos de 10.000 linhas, 1 aquecimento + 5 repetições, um processo por
container, host com 16 núcleos/32 threads. Todas as execuções produziram o mesmo
JSON. As duas séries rodaram ao mesmo tempo, o que acrescenta algum ruído. Dados
em `resultados/docker-escalabilidade/` e `resultados/docker-heterogeneo/`.

| Cenário | Mediana (s) | Speedup vs. sequencial | Speedup vs. MPI 1 worker | Eficiência |
|---|---|---|---|---|
| Sequencial | 29,94 | 1,00 | n/a | n/a |
| Estática, 1 worker | 29,48 | 1,02 | 1,00 | 1,00 |
| Estática, 2 workers | 15,02 | 1,99 | 1,96 | 0,98 |
| Estática, 4 workers | 7,84 | 3,82 | 3,76 | 0,94 |
| Estática, 8 workers | 4,39 | 6,82 | 6,71 | 0,84 |
| Dinâmica, 1 worker | 29,38 | 1,02 | 1,00 | 1,00 |
| Dinâmica, 2 workers | 14,96 | 2,00 | 1,96 | 0,98 |
| Dinâmica, 4 workers | 7,59 | 3,94 | 3,87 | 0,97 |
| Dinâmica, 8 workers | 4,16 | 7,20 | 7,06 | 0,88 |

A eficiência (speedup vs. MPI 1 worker dividido pelo número de workers) cai de
0,98 para 0,84 a 0,88 com 8 workers: a parte que só o mestre faz (ler, serializar,
enviar e agregar) passa a pesar, como prevê a Lei de Amdahl.

Com 8 workers e o worker 1 atrasado em 50 ms por tarefa: estática 6,78 s
(speedup 4,36) e dinâmica 4,74 s (speedup 6,23). Na dinâmica o worker lento
recebeu cerca de 33 dos 394 blocos e os demais, cerca de 50 cada; na estática
todos recebem 49 ou 50 e o job espera o lento.

## Experimentos nas VMs (15/11/2026)

Feitos com `scripts/experimentos/executar.py` na topologia original (mestre + 2
workers, 1 vCPU e 2 GiB por VM): CSV real, blocos de 10.000 linhas,
1 aquecimento + 5 repetições por cenário, um processo por VM.
Todas as 48 execuções produziram o mesmo JSON. Dados completos em
`resultados/vm-escalabilidade/` e `resultados/vm-heterogeneo/` (`execucoes.csv`
e `resumo.json`). O speedup divide a mediana de referência pela do cenário.

| Cenário | Mediana (s) | Desvio (s) | Speedup vs. sequencial | Speedup vs. MPI 1 worker |
|---|---|---|---|---|
| Sequencial | 28,51 | 0,16 | 1,00 | n/a |
| Estática, 1 worker | 33,30 | 0,31 | 0,86 | 1,00 |
| Estática, 2 workers | 17,36 | 0,29 | 1,64 | 1,92 |
| Dinâmica, 1 worker | 33,29 | 0,68 | 0,86 | 1,00 |
| Dinâmica, 2 workers | 17,21 | 0,26 | 1,66 | 1,93 |

Com 1 worker o MPI é mais lento que o sequencial: paga-se serialização e rede
sem ganhar paralelismo. Com workers iguais, estática e dinâmica empatam.

Worker 1 com atraso artificial de 50 ms por tarefa (`--atraso 1=0.05`), 2 workers:

| Política | Mediana (s) | Tarefas worker 1 / worker 2 |
|---|---|---|
| Estática | 27,48 | 197 / 197 |
| Dinâmica | 21,04 | cerca de 150 / 244 |

A divisão estática espera o worker lento a cada rodada; a fila dinâmica entrega
mais blocos ao worker rápido e termina 23% antes.

Estes números são **exploratórios**: as VMs dividem a CPU do mesmo computador.

## Falhas demonstradas nas VMs (15/11/2026)

| Situação | Comportamento observado |
|---|---|
| Processo do worker2 morto (`kill -9`), sem checkpoint | `mpirun` aborta o job em poucos segundos, código 137, nenhum resultado escrito |
| O mesmo, com `mpirun --enable-recovery` | job parado até o timeout externo (código 124); não há recuperação |
| Processo morto, com `com_retomada` | 1ª tentativa falha (137); a 2ª reaproveita 92 blocos do checkpoint, processa os 302 restantes e o resultado é idêntico ao sequencial |
| VM worker2 desligada durante o job, com `com_retomada` | 1ª tentativa falha em cerca de 18 s (código 255); a 2ª roda só com mestre + worker1, reaproveita 174 blocos e o resultado é idêntico |

Na primeira tentativa de desligar a VM, o `ssh` aberto pelo `mpirun` para o nó
morto ficou preso e travou o supervisor. Foi corrigido com `ServerAliveInterval 5`
e `ServerAliveCountMax 2` na configuração SSH da conta `mpi` (`conectar.yml`) e com
um supervisor que não depende do fechamento de pipes. Depois de religar uma VM
(`vagrant up worker2`), ela volta a ser usada na execução seguinte. A queda do
mestre não é tratada: o relançamento é manual, com o mesmo comando e checkpoint.

## Evidências anteriores, em containers (15/11/2026)

- Preflight aprovado no Windows para 3 nós: 3 vCPUs, 6144 MiB; rede
  `192.168.56.0/24` sem sobreposição com as rotas naquele momento.
- Sintaxe Ruby do `Vagrantfile` aprovada com `ruby -c` no WSL.
- Playbooks `node.yml` e `conectar.yml` aprovados em syntax-check e execução
  real em três containers Ubuntu 24.04; segunda aplicação sem mudanças.
- Repetição completa com mestre + 1 worker aprovada após a revisão: SSH por
  nome/IP, preparação idempotente de dados, smoke positivo e distribuição
  esperada incorreta com a mesma quantidade de hosts. Os três playbooks passaram.
- `python -m unittest discover -s tests -v`: 14 testes aprovados.
- SSH entre todos os nós aprovado; MPI com ranks em `master`, `worker1` e
  `worker2` aprovado, assim como o caso negativo de configuração incorreta.
- Versões dos containers: Python 3.12.3, mpi4py 3.1.5, Open MPI 4.1.6.
- `vagrant validate` tentado com Vagrant 2.4.9 em container, mas bloqueado
  antes da validação pela detecção do WSL e ausência de `cmd.exe` nesse ambiente.
  O pacote foi obtido de releases.hashicorp.com e teve SHA-256 verificado.
- Posteriormente, instalação no Windows concluída via WinGet: VirtualBox
  `7.2.22r175245` e Vagrant `2.4.9`. `VBoxManage list hostinfo` reconheceu
  suporte à virtualização de hardware. `vagrant validate` aprovado e
  `vagrant status` confirmou mestre e dois workers ainda não criados.
  Reinicialização solicitada pelo instalador do Vagrant e não executada.

Referências: [Ansible Local no Vagrant](https://developer.hashicorp.com/vagrant/docs/provisioning/ansible_local),
[opções de inventário](https://developer.hashicorp.com/vagrant/docs/provisioning/ansible_common),
[redes VirtualBox](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox/networking),
[box candidata](https://portal.cloud.hashicorp.com/vagrant/discover/bento/ubuntu-24.04).
