"""Testes do executor de experimentos, sem MPI real (rodar e relogio são falsos)."""

import contextlib
import csv
import io
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest

from scripts.experimentos.executar import (
    comando_mpi, comando_sequencial, construir_parser, executar_experimento, extrair_metricas,
    main, resumir)


REFERENCIA = {'contrato': 'enem-uf-escola-v1',
              'entrada': {'sha256': 'abc', 'linhas': 3, 'bytes': 10}, 'grupos': []}


class RodadorFalso:
    """Imita subprocess.run: grava a saída JSON no --saida e devolve stderr com métricas."""

    def __init__(self, divergente=None, codigo_falha=None):
        self.comandos = []
        self.divergente = divergente
        self.codigo_falha = codigo_falha

    def __call__(self, comando, capture_output, text):
        assert capture_output is True and text is True
        self.comandos.append(comando)
        if 'src.sequencial' in comando:
            nome = 'sequencial'
            metricas = {'modo': 'sequencial', 'bloco_linhas': 10000, 'tempo_total_s': 10.0}
        else:
            politica = comando[comando.index('--politica') + 1]
            workers = int(comando[comando.index('-np') + 1]) - 1
            nome = f'mpi-{politica}-{workers}w'
            metricas = {'modo': 'mpi', 'politica': politica, 'workers': workers,
                        'bloco_linhas': 10000, 'atrasos_s': {}, 'tempo_total_s': 10.0 / workers,
                        'blocos': 3, 'linhas': 3, 'bytes_enviados': 120,
                        'tarefas_por_worker': {'1': 3}, 'tempo_ocupado_por_worker_s': {'1': 1.0}}
        resultado = dict(REFERENCIA)
        if nome == self.divergente:
            resultado = dict(REFERENCIA, grupos=[{'uf': 'XX'}])
        Path(comando[comando.index('--saida') + 1]).write_text(
            json.dumps(resultado), encoding='utf-8')
        if nome == self.codigo_falha:
            return _Processo(1, 'Erro simulado\n')
        aviso = '[master:1] plm:rsh: Warning: setpgid falhou\n'
        return _Processo(0, aviso + json.dumps(metricas) + '\n')


class _Processo:
    def __init__(self, returncode, stderr):
        self.returncode = returncode
        self.stdout = ''
        self.stderr = stderr


def _relogio():
    contador = itertools.count()
    return lambda: float(next(contador))


def _execucao(cenario, modo, politica, workers, tempo, aquecimento=False):
    return {'cenario': cenario, 'modo': modo, 'politica': politica, 'workers': workers,
            'repeticao': 1, 'aquecimento': aquecimento, 'tempo_total_s': tempo,
            'tempo_externo_s': tempo, 'blocos': None, 'bytes_enviados': None,
            'tarefas_por_worker': None, 'tempo_ocupado_por_worker_s': None}


class ComandosTest(unittest.TestCase):
    def test_comando_sequencial(self):
        self.assertEqual(comando_sequencial('entrada.csv', 500, 'saida.json'), [
            sys.executable, '-m', 'src.sequencial', 'entrada.csv',
            '--bloco-linhas', '500', '--saida', 'saida.json'])

    def test_comando_mpi_sem_hostfile_nem_rede(self):
        comando = comando_mpi('entrada.csv', 10000, 'saida.json', 'dinamica', 2)
        self.assertEqual(comando, [
            'timeout', '--kill-after=5s', '600s', 'mpirun', '--oversubscribe',
            '-np', '3', sys.executable, '-m', 'src.distribuido', 'entrada.csv',
            '--politica', 'dinamica', '--bloco-linhas', '10000', '--saida', 'saida.json'])

    def test_comando_mpi_com_hostfile_rede_e_atrasos(self):
        comando = comando_mpi('entrada.csv', 10000, 'saida.json', 'estatica', 2,
                              atrasos=('2=0.5',), hostfile='hosts.txt',
                              rede='192.168.56.0/24', timeout=300)
        self.assertEqual(comando, [
            'timeout', '--kill-after=5s', '300s', 'mpirun',
            '--hostfile', 'hosts.txt', '--map-by', 'ppr:1:node',
            '--mca', 'btl_tcp_if_include', '192.168.56.0/24',
            '--mca', 'oob_tcp_if_include', '192.168.56.0/24',
            '-np', '3', sys.executable, '-m', 'src.distribuido', 'entrada.csv',
            '--politica', 'estatica', '--bloco-linhas', '10000', '--saida', 'saida.json',
            '--atraso', '2=0.5'])


class ExtrairMetricasTest(unittest.TestCase):
    def test_ignora_avisos_antes_do_json(self):
        stderr = 'Warning do Open MPI\n{"modo": "mpi", "tempo_total_s": 1.5}\n'
        self.assertEqual(extrair_metricas(stderr)['tempo_total_s'], 1.5)

    def test_sem_json_levanta_erro(self):
        with self.assertRaises(ValueError):
            extrair_metricas('apenas um aviso\n')


class ResumirTest(unittest.TestCase):
    def test_medianas_speedups_e_eficiencias(self):
        execucoes = [
            _execucao('sequencial', 'sequencial', None, 0, 100.0, aquecimento=True),
            _execucao('sequencial', 'sequencial', None, 0, 9.0),
            _execucao('sequencial', 'sequencial', None, 0, 10.0),
            _execucao('sequencial', 'sequencial', None, 0, 11.0),
            _execucao('mpi-dinamica-1w', 'mpi', 'dinamica', 1, 12.0),
            _execucao('mpi-dinamica-2w', 'mpi', 'dinamica', 2, 5.0),
            _execucao('mpi-dinamica-2w', 'mpi', 'dinamica', 2, 6.0),
            _execucao('mpi-dinamica-2w', 'mpi', 'dinamica', 2, 7.0),
        ]
        resumos = resumir(execucoes)
        self.assertEqual([r['cenario'] for r in resumos],
                         ['sequencial', 'mpi-dinamica-1w', 'mpi-dinamica-2w'])
        seq, um, dois = resumos

        self.assertEqual(seq['repeticoes'], 3)
        self.assertAlmostEqual(seq['mediana_s'], 10.0)
        self.assertAlmostEqual(seq['min_s'], 9.0)
        self.assertAlmostEqual(seq['max_s'], 11.0)
        self.assertAlmostEqual(seq['desvio_padrao_s'], 1.0)
        self.assertAlmostEqual(seq['speedup_vs_sequencial'], 1.0)
        self.assertIsNone(seq['speedup_vs_mpi_1'])
        self.assertIsNone(seq['eficiencia_vs_sequencial'])

        self.assertEqual(um['desvio_padrao_s'], 0.0)
        self.assertAlmostEqual(um['speedup_vs_sequencial'], 10 / 12)
        self.assertAlmostEqual(um['speedup_vs_mpi_1'], 1.0)
        self.assertAlmostEqual(um['eficiencia_vs_mpi_1'], 1.0)

        self.assertAlmostEqual(dois['mediana_s'], 6.0)
        self.assertAlmostEqual(dois['speedup_vs_sequencial'], 10 / 6)
        self.assertAlmostEqual(dois['speedup_vs_mpi_1'], 2.0)
        self.assertAlmostEqual(dois['eficiencia_vs_sequencial'], (10 / 6) / 2)
        self.assertAlmostEqual(dois['eficiencia_vs_mpi_1'], 1.0)

    def test_sem_sequencial_e_sem_um_worker(self):
        execucoes = [_execucao('mpi-estatica-2w', 'mpi', 'estatica', 2, 6.0)]
        (dois,) = resumir(execucoes)
        self.assertIsNone(dois['speedup_vs_sequencial'])
        self.assertIsNone(dois['speedup_vs_mpi_1'])
        self.assertIsNone(dois['eficiencia_vs_mpi_1'])


class ExecutarExperimentoTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def _args(self, *opcoes):
        return construir_parser().parse_args(
            ['entrada.csv', '--saida-dir', str(self.dir / 'saida')] + list(opcoes))

    def _executar(self, args, rodar):
        with contextlib.redirect_stdout(io.StringIO()):
            return executar_experimento(args, rodar=rodar, relogio=_relogio())

    def test_ponta_a_ponta(self):
        args = self._args('--workers', '1', '2', '--repeticoes', '2', '--aquecimento', '1')
        rodar = RodadorFalso()
        self._executar(args, rodar)
        saida = self.dir / 'saida'

        with open(saida / 'execucoes.csv', encoding='utf-8', newline='') as arquivo:
            linhas = list(csv.DictReader(arquivo, delimiter=';'))
        # 1 sequencial + 2 políticas x 2 valores de W = 5 cenários; (1 aquecimento + 2) cada
        self.assertEqual(len(linhas), 5 * 3)
        self.assertEqual(len(rodar.comandos), 5 * 3)
        self.assertEqual(sum(1 for l in linhas if l['aquecimento'] == '1'), 5)
        sequencial = [l for l in linhas if l['cenario'] == 'sequencial'][0]
        self.assertEqual((sequencial['politica'], sequencial['workers'],
                          sequencial['tarefas_por_worker']), ('', '0', ''))

        dados = json.loads((saida / 'resumo.json').read_text(encoding='utf-8'))
        self.assertEqual(dados['ambiente'], 'local')
        self.assertEqual(dados['commit'], 'desconhecido')
        self.assertEqual(dados['entrada']['sha256'], 'abc')
        self.assertEqual(dados['entrada']['arquivo'], 'entrada.csv')
        self.assertEqual(dados['repeticoes'], 2)
        self.assertEqual(dados['aquecimento'], 1)
        self.assertIsNone(dados['hostfile'])
        self.assertEqual(len(dados['cenarios']), 5)
        self.assertFalse((saida / '_saida.json').exists())

    def test_hostfile_e_atrasos_vao_para_o_resumo_e_o_comando(self):
        hostfile = self.dir / 'hosts.txt'
        hostfile.write_text('master\nworker1\n\nworker2\n', encoding='utf-8')
        args = self._args('--workers', '2', '--politicas', 'estatica', '--repeticoes', '1',
                          '--aquecimento', '0', '--hostfile', str(hostfile),
                          '--atraso', '2=0.5')
        rodar = RodadorFalso()
        self._executar(args, rodar)
        dados = json.loads((self.dir / 'saida' / 'resumo.json').read_text(encoding='utf-8'))
        self.assertEqual(dados['hostfile'], ['master', 'worker1', 'worker2'])
        self.assertEqual(dados['atrasos'], ['2=0.5'])
        self.assertIn('--atraso', rodar.comandos[1])
        self.assertIn('--hostfile', rodar.comandos[1])

    def test_resultado_divergente_nao_grava_resumo(self):
        args = self._args('--workers', '2', '--politicas', 'dinamica', '--repeticoes', '1',
                          '--aquecimento', '0')
        with self.assertRaisesRegex(RuntimeError, 'Resultado divergente em mpi-dinamica-2w'):
            self._executar(args, RodadorFalso(divergente='mpi-dinamica-2w'))
        self.assertFalse((self.dir / 'saida' / 'resumo.json').exists())
        self.assertFalse((self.dir / 'saida' / 'execucoes.csv').exists())

    def test_returncode_diferente_de_zero_levanta_erro(self):
        args = self._args('--workers', '1', '--politicas', 'estatica', '--repeticoes', '1',
                          '--aquecimento', '0')
        with self.assertRaisesRegex(RuntimeError, 'mpi-estatica-1w'):
            self._executar(args, RodadorFalso(codigo_falha='mpi-estatica-1w'))
        self.assertFalse((self.dir / 'saida' / 'resumo.json').exists())

    def test_main_valida_repeticoes(self):
        erro = io.StringIO()
        with contextlib.redirect_stderr(erro), self.assertRaises(SystemExit) as saida:
            main(['entrada.csv', '--saida-dir', str(self.dir / 'saida'), '--repeticoes', '0'])
        self.assertEqual(saida.exception.code, 1)
        self.assertIn('Erro:', erro.getvalue())


if __name__ == '__main__':
    unittest.main()
