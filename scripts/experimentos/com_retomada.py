"""Reinício supervisionado: relança o job MPI com os nós que ainda respondem.

O Open MPI instalado encerra o job inteiro quando um processo morre; não há
continuidade automática. Este supervisor, executado no mestre, repete o
lançamento a partir do checkpoint, de modo que blocos concluídos não são refeitos.

    python3 -m scripts.experimentos.com_retomada ENTRADA --saida R.json \
        --checkpoint C.jsonl --hostfile /opt/projeto-sd/hostfile [--rede SUBREDE]
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def nos_do_hostfile(texto):
    return [linha.split()[0] for linha in texto.splitlines() if linha.strip()]


def responde(no):
    return subprocess.run(['ssh', '-o', 'ConnectTimeout=3', no, 'true'],
                          capture_output=True).returncode == 0


def lancar(comando):
    """Executa e retorna (código, stderr) sem depender do fechamento de pipes.

    Com um nó desligado, o ssh que o mpirun abriu para ele pode sobreviver ao
    mpirun e manter um pipe aberto; por isso o stderr vai para um arquivo.
    """
    with tempfile.TemporaryFile('w+', encoding='utf-8') as erros:
        codigo = subprocess.run(comando, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=erros).returncode
        erros.seek(0)
        return codigo, erros.read()


def comando(args, nos, hostfile):
    rede = ['--mca', 'btl_tcp_if_include', args.rede,
            '--mca', 'oob_tcp_if_include', args.rede] if args.rede else []
    return ['timeout', '--kill-after=5s', f'{args.timeout}s', 'mpirun',
            '--hostfile', str(hostfile), '--map-by', 'ppr:1:node', *rede,
            '-np', str(len(nos)), sys.executable, '-m', 'src.distribuido',
            str(args.entrada), '--politica', args.politica,
            '--bloco-linhas', str(args.bloco_linhas), '--saida', str(args.saida),
            '--checkpoint', str(args.checkpoint)]


def supervisionar(args, responde=responde, lancar=lancar, relogio=time.perf_counter):
    """Retorna a lista de tentativas; a última tem código zero em caso de sucesso."""
    nos = nos_do_hostfile(Path(args.hostfile).read_text(encoding='utf-8'))
    hostfile = Path(str(args.checkpoint) + '.hostfile')
    tentativas = []
    for numero in range(1, args.tentativas + 1):
        # O primeiro nó é o mestre, onde este supervisor está rodando.
        vivos = nos[:1] + [no for no in nos[1:] if responde(no)]
        if len(vivos) < 2:
            raise RuntimeError('Nenhum worker responde; não há como retomar')
        hostfile.write_text(''.join(f'{no} slots=1\n' for no in vivos), encoding='utf-8')
        inicio = relogio()
        codigo, erros = lancar(comando(args, vivos, hostfile))
        metricas = None
        for linha in reversed(erros.splitlines()):
            if linha.startswith('{') and 'tempo_total_s' in linha:
                metricas = json.loads(linha)
                break
        tentativas.append({'tentativa': numero, 'nos': vivos, 'codigo': codigo,
                           'duracao_s': relogio() - inicio, 'metricas': metricas})
        print(json.dumps(tentativas[-1]), file=sys.stderr, flush=True)
        if codigo == 0:
            hostfile.unlink()
            return tentativas
    raise RuntimeError(f'Job não concluído após {args.tentativas} tentativas')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('entrada', type=Path)
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--hostfile', type=Path, required=True)
    parser.add_argument('--rede')
    parser.add_argument('--politica', choices=('estatica', 'dinamica'), default='dinamica')
    parser.add_argument('--bloco-linhas', type=int, default=10000)
    parser.add_argument('--tentativas', type=int, default=3)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    try:
        supervisionar(args)
    except (OSError, RuntimeError) as erro:
        parser.exit(1, f'Erro: {erro}\n')


if __name__ == '__main__':
    main()
