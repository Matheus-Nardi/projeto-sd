from contextlib import redirect_stderr
from pathlib import Path
import argparse
import io
import json
import tempfile
import unittest

from scripts.experimentos.com_retomada import comando, nos_do_hostfile, supervisionar

HOSTFILE = 'master slots=1\nworker1 slots=1\nworker2 slots=2\n'


def argumentos(pasta, **extra):
    base = dict(entrada=Path(pasta) / 'dados.csv', saida=Path(pasta) / 'saida.json',
                checkpoint=Path(pasta) / 'ckpt.jsonl', hostfile=Path(pasta) / 'hostfile',
                rede=None, politica='dinamica', bloco_linhas=10000, tentativas=3,
                timeout=600)
    base.update(extra)
    return argparse.Namespace(**base)


def sem_saida(funcao, *args, **kwargs):
    with redirect_stderr(io.StringIO()):
        return funcao(*args, **kwargs)


class TestRetomada(unittest.TestCase):
    def test_nos_do_hostfile(self):
        texto = 'master slots=1\nworker1 slots=1\n\nworker2 slots=2\n'
        self.assertEqual(nos_do_hostfile(texto), ['master', 'worker1', 'worker2'])

    def test_comando_com_e_sem_rede(self):
        with tempfile.TemporaryDirectory() as pasta:
            args = argumentos(pasta)
            hostfile = Path(pasta) / 'ckpt.jsonl.hostfile'
            nos = ['master', 'worker1']
            cmd = comando(args, nos, hostfile)
            self.assertEqual(cmd[cmd.index('-np') + 1], '2')
            self.assertEqual(cmd[cmd.index('--hostfile') + 1], str(hostfile))
            self.assertEqual(cmd[cmd.index('--checkpoint') + 1], str(args.checkpoint))
            self.assertIn('--politica', cmd)
            self.assertIn('--bloco-linhas', cmd)
            self.assertNotIn('--mca', cmd)

            args.rede = '192.168.56.0/24'
            cmd = comando(args, nos, hostfile)
            self.assertEqual(cmd.count('--mca'), 2)
            self.assertIn('btl_tcp_if_include', cmd)
            self.assertIn('oob_tcp_if_include', cmd)
            self.assertEqual(cmd[cmd.index('btl_tcp_if_include') + 1], '192.168.56.0/24')
            self.assertEqual(cmd[cmd.index('oob_tcp_if_include') + 1], '192.168.56.0/24')

    def test_sucesso_na_primeira_tentativa(self):
        with tempfile.TemporaryDirectory() as pasta:
            args = argumentos(pasta)
            args.hostfile.write_text(HOSTFILE, encoding='utf-8')
            metricas = {'tempo_total_s': 1.5, 'blocos': 3}
            chamadas = []
            relogio = iter([10.0, 12.5]).__next__

            def lancar(comando_):
                chamadas.append(comando_)
                saida = 'aviso: algo aconteceu\n' + json.dumps(metricas) + '\n'
                return 0, saida

            tentativas = sem_saida(supervisionar, args, responde=lambda no: True,
                                   lancar=lancar, relogio=relogio)

            self.assertEqual(len(tentativas), 1)
            self.assertEqual(len(chamadas), 1)
            self.assertEqual(tentativas[0]['codigo'], 0)
            self.assertEqual(tentativas[0]['nos'], ['master', 'worker1', 'worker2'])
            self.assertEqual(tentativas[0]['metricas'], metricas)
            self.assertEqual(tentativas[0]['duracao_s'], 2.5)
            self.assertFalse(Path(str(args.checkpoint) + '.hostfile').exists())

    def test_falha_e_retomada_com_no_perdido(self):
        with tempfile.TemporaryDirectory() as pasta:
            args = argumentos(pasta)
            args.hostfile.write_text(HOSTFILE, encoding='utf-8')
            estado = {'primeira_chamada': False}
            chamadas = []
            hostfiles_lidos = []

            def responde(no):
                return not (no == 'worker2' and estado['primeira_chamada'])

            def lancar(comando_):
                chamadas.append(comando_)
                if len(chamadas) == 1:
                    estado['primeira_chamada'] = True
                    return 137, ''
                conteudo = Path(comando_[comando_.index('--hostfile') + 1]).read_text(
                    encoding='utf-8')
                hostfiles_lidos.append(conteudo)
                return 0, ''

            tentativas = sem_saida(supervisionar, args, responde=responde, lancar=lancar)

            self.assertEqual(len(tentativas), 2)
            self.assertEqual(tentativas[1]['nos'], ['master', 'worker1'])
            self.assertEqual(tentativas[1]['codigo'], 0)
            self.assertEqual(chamadas[1][chamadas[1].index('-np') + 1], '2')
            self.assertEqual(hostfiles_lidos, ['master slots=1\nworker1 slots=1\n'])

    def test_mestre_nao_e_consultado(self):
        with tempfile.TemporaryDirectory() as pasta:
            args = argumentos(pasta)
            args.hostfile.write_text(HOSTFILE, encoding='utf-8')
            consultados = []

            def responde(no):
                consultados.append(no)
                return True

            sem_saida(supervisionar, args, responde=responde,
                      lancar=lambda comando_: (0, ''))

            self.assertNotIn('master', consultados)
            self.assertEqual(consultados, ['worker1', 'worker2'])

    def test_nenhum_worker_responde(self):
        with tempfile.TemporaryDirectory() as pasta:
            args = argumentos(pasta)
            args.hostfile.write_text(HOSTFILE, encoding='utf-8')
            chamadas = []

            with self.assertRaises(RuntimeError):
                sem_saida(supervisionar, args, responde=lambda no: False,
                          lancar=lambda comando_: chamadas.append(comando_) or (0, ''))
            self.assertEqual(chamadas, [])

    def test_esgota_tentativas(self):
        with tempfile.TemporaryDirectory() as pasta:
            args = argumentos(pasta, tentativas=2)
            args.hostfile.write_text(HOSTFILE, encoding='utf-8')
            chamadas = []

            def lancar(comando_):
                chamadas.append(comando_)
                return 1, ''

            with self.assertRaises(RuntimeError):
                sem_saida(supervisionar, args, responde=lambda no: True, lancar=lancar)
            self.assertEqual(len(chamadas), 2)


if __name__ == '__main__':
    unittest.main()
