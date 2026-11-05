"""
tests/test_dados.py
Testes unitários para o script de manipulação e geração de dados.
"""

import os
import shutil
import tempfile
import unittest

from scripts.obter_dados import (
    calcular_sha256,
    gerar_dados_sinteticos,
    inspecionar_arquivo,
    COLUNAS_SELECIONADAS
)


class TestGeradorDados(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.test_dir, "teste_enem.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_geracao_sintetica_e_determinismo(self):
        # Gera 0.5 MB para teste rápido
        res1 = gerar_dados_sinteticos(self.csv_path, tamanho_mb=0.5, seed=42)
        self.assertTrue(os.path.exists(self.csv_path))
        self.assertGreater(res1["linhas"], 1000)
        self.assertGreaterEqual(res1["bytes"], int(0.5 * 1024 * 1024))

        # Re-gera e verifica se com a mesma seed o checksum SHA-256 é idêntico
        csv_path2 = os.path.join(self.test_dir, "teste_enem_2.csv")
        res2 = gerar_dados_sinteticos(csv_path2, tamanho_mb=0.5, seed=42)
        self.assertEqual(res1["sha256"], res2["sha256"])

    def test_inspecionar_arquivo(self):
        gerar_dados_sinteticos(self.csv_path, tamanho_mb=0.2, seed=123)
        info = inspecionar_arquivo(self.csv_path)

        self.assertEqual(info["colunas"], COLUNAS_SELECIONADAS)
        self.assertGreater(info["total_linhas"], 100)
        self.assertEqual(info["total_linhas"], info["presentes"] + info["faltosos"])
        self.assertEqual(info["sha256"], calcular_sha256(self.csv_path))


if __name__ == "__main__":
    unittest.main()
