"""Smoke test MPI: broadcast, ponto a ponto e ranks em hosts distintos."""

import argparse
import json
import socket
import sys


def main():
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    rank, tamanho = comm.Get_rank(), comm.Get_size()
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--hosts', nargs='+', required=True)
        parser.add_argument('--master', default='master')
        args = parser.parse_args()
        if tamanho != len(args.hosts) or tamanho < 2:
            raise ValueError('Use um processo por nó, incluindo o mestre dedicado')
        if len(set(args.hosts)) != tamanho or args.master not in args.hosts:
            raise ValueError('Informe hosts distintos e inclua o mestre esperado')
        token = comm.bcast('projeto-sd-mpi-ok' if rank == 0 else None, root=0)
        if token != 'projeto-sd-mpi-ok':
            raise ValueError('Broadcast incorreto')
        if rank == 0:
            for worker in range(1, tamanho):
                comm.send(worker, dest=worker, tag=10)
                if comm.recv(source=worker, tag=11) != worker * 2:
                    raise ValueError('Resposta ponto a ponto incorreta')
        else:
            valor = comm.recv(source=0, tag=10)
            comm.send(valor * 2, dest=0, tag=11)
        nos = comm.gather({'rank': rank, 'hostname': socket.gethostname()}, root=0)
        if rank == 0:
            if sorted(n['hostname'] for n in nos) != sorted(args.hosts):
                raise ValueError(f'Distribuição de processos incorreta: {nos}')
            if nos[0]['hostname'] != args.master:
                raise ValueError('Rank zero não está no mestre esperado')
            print(json.dumps({'ok': True, 'processos': nos}), flush=True)
        comm.Barrier()
    except Exception as erro:
        print(f'Rank {rank}: {erro}', file=sys.stderr, flush=True)
        comm.Abort(1)


if __name__ == '__main__':
    main()
