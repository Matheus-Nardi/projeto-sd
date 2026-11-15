from contextlib import redirect_stderr
import io
import unittest
from unittest.mock import patch

from scripts.cluster.conectar import extrair_chave, validar_confianca
from scripts.cluster.preparar import configurar, verificar_recursos, verificar_subrede
from scripts.cluster.validar import json_remoto


class TestCluster(unittest.TestCase):
    def test_diagnostico_mpi_nao_contamina_json(self):
        aviso = '[master:11412] plm:rsh: Warning: setpgid failed in parent'
        with patch('scripts.cluster.validar.executar_no', return_value=aviso + '\n{"ok": true}\n'):
            with redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(json_remoto('master', 'mpirun'), {'ok': True})
            self.assertIn(aviso, stderr.getvalue())
        with patch('scripts.cluster.validar.executar_no', return_value='{invalido'):
            with self.assertRaisesRegex(ValueError, 'master: resposta JSON'):
                json_remoto('master', 'mpirun')

    def test_rejeita_chaves_herdadas_da_mesma_box(self):
        config = configurar(workers=1)
        confianca = {'cluster_host_keys': {'master': 'host-a', 'worker1': 'host-b'},
                     'cluster_user_keys': {'master': 'user-a', 'worker1': 'user-b'}}
        validar_confianca(config, confianca)
        confianca['cluster_host_keys']['worker1'] = 'host-a'
        with self.assertRaises(ValueError):
            validar_confianca(config, confianca)

    def test_coleta_de_chaves_publicas(self):
        chave = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExemplo chave-de-teste'
        self.assertEqual(extrair_chave('aviso\r\n' + chave + '\r\n'),
                         chave.rsplit(' ', 1)[0])
        for texto in ('', '-----BEGIN OPENSSH PRIVATE KEY-----', chave + '\n' + chave):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                extrair_chave(texto)

    def test_topologias(self):
        for workers in (1, 2, 4):
            config = configurar(workers=workers)
            nos = config['cluster_nodes']
            self.assertEqual(len(nos), workers + 1)
            self.assertEqual(nos[0], {'name': 'master', 'ip': '192.168.56.10', 'slots': 1})
            self.assertEqual(nos[-1]['ip'], f'192.168.56.{10 + workers}')
            self.assertEqual(len({n['ip'] for n in nos}), len(nos))

    def test_configuracao_invalida(self):
        for args in ({'workers': 3}, {'cpus': 0}, {'memory_mb': 0},
                     {'subnet': '0.0.0.0/24'}, {'subnet': '192.168.56.0/28'},
                     {'subnet': '192.168.56.1/24'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                configurar(**args)

    def test_conflito_de_rotas(self):
        # A rota padrão é ignorada; redes agregadas e rotas para hosts contam.
        verificar_subrede('192.168.56.0/24', ['0.0.0.0/0', '192.168.10.0/24'])
        for rota in ('192.168.0.0/16', '192.168.56.1/32', '192.168.56.0/24'):
            with self.subTest(rota=rota), self.assertRaises(ValueError):
                verificar_subrede('192.168.56.0/24', [rota])

    def test_orcamento(self):
        config = configurar()
        verificar_recursos(config, cpus=8, memoria_mb=16000, disco_mb=100000)
        for recursos in ({'cpus': 2}, {'memoria_mb': 6000}, {'disco_mb': 1000}):
            disponivel = dict(cpus=8, memoria_mb=16000, disco_mb=100000)
            disponivel.update(recursos)
            with self.subTest(recursos=recursos), self.assertRaises(ValueError):
                verificar_recursos(config, **disponivel)
