import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.agregacao import agregar, combinar, finalizar, ler_blocos


FIXTURE = Path(__file__).parent / 'fixtures' / 'enem_manual.csv'


class TestAgregacao(unittest.TestCase):
    def test_resultado_manual_e_blocos(self):
        esperado = [
            ('AC', '2', 0, 0, None, 0, 0, None),
            ('SP', '1', 0, 1, '0.00', 0, 0, None),
            ('SP', '3', 7000, 1, '700.00', 18000, 2, '900.00'),
            ('TO', '2', 11003, 2, '550.15', 6000, 2, '300.00'),
        ]
        for tamanho in (1, 2, 3, 100):
            total = {}
            ids = []
            for bloco_id, linhas in ler_blocos(FIXTURE, tamanho):
                ids.append(bloco_id)
                combinar(total, agregar(linhas))
            self.assertEqual(ids, list(range(len(ids))))
            saida = finalizar(total)
            self.assertEqual([
                (g['uf'], g['tp_escola'], g['mt']['soma_decimos'],
                 g['mt']['contagem'], g['mt']['media'],
                 g['redacao']['soma_decimos'], g['redacao']['contagem'],
                 g['redacao']['media']) for g in saida
            ], esperado)

    def test_invalidos(self):
        with FIXTURE.open(encoding='utf-8') as f:
            base = next(csv.DictReader(f, delimiter=';'))
        for campo, valor in [('SG_UF_PROVA', 'XX'), ('TP_ESCOLA', '4'),
                             ('TP_PRESENCA_MT', '9'), ('NU_NOTA_MT', 'NaN'),
                             ('NU_NOTA_MT', '-1'), ('NU_NOTA_MT', '1.23'),
                             ('NU_NOTA_MT', '1000.1')]:
            with self.subTest(campo=campo, valor=valor), self.assertRaises(ValueError):
                agregar([dict(base, **{campo: valor})])

    def test_vazio_e_cabecalho_invalido(self):
        self.assertEqual(finalizar(agregar([])), [])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'entrada.csv'
            p.write_text('', encoding='utf-8')
            with self.assertRaises(ValueError):
                list(ler_blocos(p, 10))
            p.write_text(FIXTURE.read_text(encoding='utf-8').splitlines()[0] + '\n', encoding='utf-8')
            self.assertEqual(list(ler_blocos(p, 10)), [])
            with self.assertRaises(ValueError):
                list(ler_blocos(p, 0))

    def test_linha_truncada_ou_com_campos_extras(self):
        cabecalho, linha = FIXTURE.read_text(encoding='utf-8').splitlines()[:2]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'entrada.csv'
            for invalida in (linha.rsplit(';', 1)[0], linha + ';extra'):
                p.write_text(cabecalho + '\n' + invalida + '\n', encoding='utf-8')
                with self.assertRaises(ValueError):
                    for _, linhas in ler_blocos(p):
                        agregar(linhas)

    def test_arredondamento(self):
        grupo = finalizar({('TO', '2'): [1, 4, 0, 0]})[0]
        self.assertEqual(grupo['mt']['media'], '0.03')

    def test_cli_rejeita_entrada_invalida(self):
        r = subprocess.run([sys.executable, '-m', 'src.sequencial', str(FIXTURE),
                            '--bloco-linhas', '0'], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '')

    def test_cli(self):
        r = subprocess.run([sys.executable, '-m', 'src.sequencial', str(FIXTURE),
                            '--bloco-linhas', '2'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        resultado = json.loads(r.stdout)
        self.assertEqual(resultado['entrada']['linhas'], 8)
        self.assertEqual(len(resultado['entrada']['sha256']), 64)
        self.assertEqual(len(resultado['grupos']), 4)
        self.assertNotIn('tempo', resultado)


if __name__ == '__main__':
    unittest.main()
