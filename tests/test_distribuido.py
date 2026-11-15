"""Mestre/workers testados com um comunicador simulado por threads e, quando
mpirun e mpi4py existem (nós do cluster), também com processos MPI reais."""

import importlib.util
import json
from pathlib import Path
import pickle
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

from src.distribuido import (TAG_RESULT, TAG_STOP, TAG_TASK, ErroProtocolo,
                             destino_estatico, mestre, worker)
from src.sequencial import executar, montar_resultado


FIXTURE = Path(__file__).parent / 'fixtures' / 'enem_manual.csv'
TEM_MPI = bool(shutil.which('mpirun')) and importlib.util.find_spec('mpi4py') is not None


class Status:
    def Get_source(self):
        return self.origem

    def Get_tag(self):
        return self.tag


class Comunicador:
    """Subconjunto do comunicador mpi4py usado pelo algoritmo, sobre filas."""

    def __init__(self, rede, rank):
        self.rede, self.rank = rede, rank

    def Get_rank(self):
        return self.rank

    def Get_size(self):
        return len(self.rede['filas'])

    def send(self, objeto, dest, tag):
        self.rede['filas'][dest].put((self.rank, tag, pickle.dumps(objeto)))

    def recv(self, source=None, tag=None, status=None):
        origem, etiqueta, dados = self.rede['filas'][self.rank].get(timeout=10)
        assert source in (None, origem) and tag in (None, etiqueta)
        if status is not None:
            status.origem, status.tag = origem, etiqueta
        return pickle.loads(dados)

    def bcast(self, objeto, root):
        if self.rank == root:
            for fila in self.rede['finais'][1:]:
                fila.put(objeto)
            return objeto
        return self.rede['finais'][self.rank].get(timeout=10)


def criar_rede(processos):
    return {'filas': [queue.Queue() for _ in range(processos)],
            'finais': [queue.Queue() for _ in range(processos)]}


def rodar(caminho, workers, bloco, politica, atrasos=None):
    """Executa mestre e workers; exige que todos os workers encerrem."""
    rede = criar_rede(workers + 1)
    estados = {}

    def alvo(rank):
        estados[rank] = worker(Comunicador(rede, rank), Status, (atrasos or {}).get(rank, 0.0))

    threads = [threading.Thread(target=alvo, args=(r,), daemon=True)
               for r in range(1, workers + 1)]
    for thread in threads:
        thread.start()
    try:
        return mestre(Comunicador(rede, 0), Status, caminho, bloco, politica), estados
    finally:
        for thread in threads:
            thread.join(timeout=10)
        if any(t.is_alive() for t in threads) or len(estados) != workers:
            raise AssertionError('Workers não encerraram')


class TestDistribuido(unittest.TestCase):
    def test_atribuicao_estatica(self):
        self.assertEqual([destino_estatico(i, 1) for i in range(3)], [1, 1, 1])
        self.assertEqual([destino_estatico(i, 2) for i in range(5)], [1, 2, 1, 2, 1])
        self.assertEqual([destino_estatico(i, 4) for i in range(6)], [1, 2, 3, 4, 1, 2])

    def test_mesma_saida_da_referencia(self):
        esperado = executar(FIXTURE)
        for politica in ('estatica', 'dinamica'):
            for workers in (1, 2, 4):
                for bloco in (1, 2, 3, 100):
                    with self.subTest(politica=politica, workers=workers, bloco=bloco):
                        (grupos, m), estados = rodar(FIXTURE, workers, bloco, politica)
                        self.assertEqual(montar_resultado(FIXTURE, m['linhas'], grupos), esperado)
                        self.assertEqual(m['blocos'], -(-8 // bloco))
                        self.assertEqual(sum(m['tarefas_por_worker'].values()), m['blocos'])
                        self.assertTrue(all(e == {'ok': True, 'erro': None}
                                            for e in estados.values()))
                        if politica == 'estatica':
                            self.assertEqual(m['tarefas_por_worker'], {
                                r: sum(destino_estatico(i, workers) == r
                                       for i in range(m['blocos']))
                                for r in range(1, workers + 1)})

    def test_bloco_grande_linhas_vazias_e_fim_de_linha_windows(self):
        cabecalho, *linhas = FIXTURE.read_text(encoding='utf-8').splitlines()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'entrada.csv'
            # Tarefas de cerca de 1 MiB, acima do limite eager usual do MPI.
            p.write_bytes(('\r\n'.join([cabecalho, ''] + linhas * 12000) + '\r\n\r\n').encode())
            esperado = executar(p)
            self.assertEqual(esperado['entrada']['linhas'], 96000)
            for politica in ('estatica', 'dinamica'):
                (grupos, m), _ = rodar(p, 2, 50000, politica)
                self.assertEqual(montar_resultado(p, m['linhas'], grupos), esperado)
                self.assertEqual(m['blocos'], 2)
                self.assertGreater(m['bytes_enviados'], 1024 * 1024)

    def test_sem_registros_e_erros_encerram_os_workers(self):
        cabecalho, *linhas = FIXTURE.read_text(encoding='utf-8').splitlines()
        ruim = linhas[:5] + ['9;XX;2;1;1;500;600'] + linhas[5:]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'entrada.csv'
            for politica in ('estatica', 'dinamica'):
                p.write_text(cabecalho + '\n', encoding='utf-8')
                (grupos, m), _ = rodar(p, 2, 10, politica)
                self.assertEqual((grupos, m['blocos'], m['linhas']), ({}, 0, 0))
                for texto, mensagem in (('', 'Cabeçalho'),
                                        ('\n'.join([cabecalho] + ruim), 'Bloco 5: Linha 1'),
                                        ('\n'.join([cabecalho, '1;TO;2;1;1;"5";6']), 'aspas')):
                    p.write_text(texto, encoding='utf-8')
                    with self.subTest(politica=politica, mensagem=mensagem), \
                            self.assertRaisesRegex(ValueError, mensagem):
                        rodar(p, 2, 1, politica)

    def test_fila_dinamica_poupa_o_worker_lento(self):
        (_, estatica), _ = rodar(FIXTURE, 2, 1, 'estatica', {1: 0.05})
        (_, dinamica), _ = rodar(FIXTURE, 2, 1, 'dinamica', {1: 0.05})
        self.assertEqual(estatica['tarefas_por_worker'], {1: 4, 2: 4})
        self.assertLess(dinamica['tarefas_por_worker'][1], 4)
        self.assertGreaterEqual(dinamica['tempo_ocupado_por_worker_s'][1], 0.05)

    def test_checkpoint_retoma_sem_repetir_blocos(self):
        esperado = executar(FIXTURE)
        with tempfile.TemporaryDirectory() as d:
            ck = Path(d) / 'checkpoint.jsonl'

            def retomar(bloco=1):
                rede = criar_rede(3)
                threads = [threading.Thread(target=worker, daemon=True,
                                            args=(Comunicador(rede, r), Status))
                           for r in (1, 2)]
                for thread in threads:
                    thread.start()
                try:
                    return mestre(Comunicador(rede, 0), Status, FIXTURE, bloco, 'dinamica', ck)
                finally:
                    for thread in threads:
                        thread.join(timeout=10)

            grupos, m = retomar()
            self.assertEqual((m['blocos'], m['blocos_retomados']), (8, 0))
            completo = ck.read_text(encoding='utf-8').splitlines(keepends=True)
            self.assertEqual(len(completo), 9)  # identificação + 8 blocos
            # Queda simulada: sobram 3 blocos gravados e uma linha cortada no fim.
            ck.write_text(''.join(completo[:4]) + completo[4][:10], encoding='utf-8')
            grupos, m = retomar()
            self.assertEqual((m['blocos'], m['blocos_retomados']), (5, 3))
            self.assertEqual(montar_resultado(FIXTURE, m['linhas'], grupos), esperado)
            # Checkpoint completo: nada é reenviado e o resultado não muda.
            grupos, m = retomar()
            self.assertEqual((m['blocos'], m['blocos_retomados']), (0, 8))
            self.assertEqual(montar_resultado(FIXTURE, m['linhas'], grupos), esperado)
            with self.assertRaisesRegex(ValueError, 'outro tamanho de bloco'):
                retomar(bloco=2)
            ck.write_text(''.join(completo + completo[1:2]), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'repetido'):
                retomar()

    def test_violacoes_de_protocolo(self):
        def resposta(tarefa, **mudancas):
            bloco_id = pickle.loads(tarefa)[0]
            return dict({'bloco_id': bloco_id, 'rank': 1, 'linhas': 1, 'parcial': {},
                         'tempo_s': 0.0}, **mudancas)

        casos = {'duplicado': lambda t: [resposta(t), resposta(t)],
                 'id divergente': lambda t: [resposta(t, bloco_id=7)],
                 'rank divergente': lambda t: [resposta(t, rank=2)],
                 'linhas divergentes': lambda t: [resposta(t, linhas=2)]}
        for nome, respostas in casos.items():
            rede = criar_rede(2)
            falso = Comunicador(rede, 1)

            def alvo(falso=falso, respostas=respostas):
                status = Status()
                tarefa = falso.recv(status=status)
                if status.tag == TAG_TASK:
                    for r in respostas(tarefa):
                        falso.send(r, 0, TAG_RESULT)

            threading.Thread(target=alvo, daemon=True).start()
            with self.subTest(caso=nome), self.assertRaises(ErroProtocolo):
                mestre(Comunicador(rede, 0), Status, FIXTURE, 1, 'dinamica')


@unittest.skipUnless(TEM_MPI, 'requer mpirun e mpi4py (execute nos nós do cluster)')
class TestMPIReal(unittest.TestCase):
    def mpirun(self, n, *args):
        return subprocess.run(
            ['timeout', '--kill-after=5s', '60s', 'mpirun', '--oversubscribe', '-n', str(n),
             sys.executable, '-m', 'src.distribuido', *map(str, args)],
            capture_output=True, text=True)

    def test_politicas_com_processos_reais(self):
        esperado = executar(FIXTURE)
        for politica in ('estatica', 'dinamica'):
            for n, bloco in ((2, 3), (3, 1), (5, 2), (5, 100)):
                with self.subTest(politica=politica, n=n, bloco=bloco):
                    r = self.mpirun(n, FIXTURE, '--politica', politica, '--bloco-linhas', bloco)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(json.loads(r.stdout), esperado)
                    metricas = json.loads(r.stderr.strip().splitlines()[-1])
                    self.assertEqual(metricas['workers'], n - 1)

    def test_erros_terminam_sem_resultado(self):
        cabecalho, *linhas = FIXTURE.read_text(encoding='utf-8').splitlines()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'entrada.csv'
            p.write_text('\n'.join([cabecalho] + linhas[:4] + ['9;XX;2;1;1;5;6']),
                         encoding='utf-8')
            for args in ((3, p, '--bloco-linhas', 1), (3, p, '--bloco-linhas', 0),
                         (3, Path(d) / 'ausente.csv'), (1, FIXTURE)):
                with self.subTest(args=args):
                    r = self.mpirun(*args)
                    self.assertNotIn(r.returncode, (0, 124, 137), r.stderr)
                    self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()
