#!/bin/sh
# Executar no mestre como mpi. $1 = "kill" mata o processo do worker2 aos 6 s;
# qualquer outro valor apenas roda (a falha é provocada de fora, pelo host).
set -u
cd /opt/projeto-sd/code
R=/opt/projeto-sd/resultados
rm -f $R/retomada.json $R/retomada.jsonl
/usr/bin/python3 -m scripts.experimentos.com_retomada /opt/projeto-sd/dados/enem_2023_real.csv \
    --saida $R/retomada.json --checkpoint $R/retomada.jsonl \
    --hostfile /opt/projeto-sd/hostfile --rede 192.168.56.0/24 --timeout 90 \
    2> /tmp/retomada.log &
if [ "${1:-}" = kill ]; then
    sleep 6
    ssh worker2 'pkill -KILL -u mpi -f src.distribuido'
fi
wait $!
echo "codigo_supervisor=$?"
cat /tmp/retomada.log
echo "identico=$(cmp -s $R/sequencial.json $R/retomada.json && echo sim || echo NAO)"
