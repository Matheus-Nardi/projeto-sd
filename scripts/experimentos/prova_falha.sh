#!/bin/sh
# Prova isolada (etapa 7): mata o processo de um worker no meio da execução
# e observa o comportamento real do Open MPI instalado. Executar no mestre como mpi.
set -u
cd /opt/projeto-sd/code
D=/opt/projeto-sd/dados/enem_2023_real.csv
R=/opt/projeto-sd/resultados
rm -f $R/falha.json
inicio=$(date +%s)
timeout --kill-after=5s 120s mpirun --hostfile /opt/projeto-sd/hostfile \
    --mca btl_tcp_if_include 192.168.56.0/24 --mca oob_tcp_if_include 192.168.56.0/24 \
    --map-by ppr:1:node -np 3 --wdir /opt/projeto-sd/code "$@" \
    /usr/bin/python3 -m src.distribuido $D --politica dinamica --saida $R/falha.json \
    > /tmp/falha.log 2>&1 &
sleep 6
ssh worker2 'pkill -KILL -u mpi -f src.distribuido; echo "kill em worker2: $?"'
wait $!
echo "codigo_mpirun=$? duracao=$(( $(date +%s) - inicio ))s"
grep -v setpgid /tmp/falha.log | head -20
ls $R/falha.json 2>&1
for no in master worker1 worker2; do
    echo "$no: $(ssh $no 'pgrep -u mpi -fc src.distribuido')"
done
