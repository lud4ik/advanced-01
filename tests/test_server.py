import os
import os.path
import time
import socket
import signal
import unittest
import subprocess

from work.utils import get_msg
from work.protocol import Packet
from work.models import (Connected, Pong, PongD, AckQuit, AckFinish,
                         Connect, Ping, PingD, Quit, Finish)


class ServerTestCase(unittest.TestCase):

    HOST = ''
    PORT = 50007
    TERMINATE_TIMEOUT = 1

    def setUp(self):
        self.server = subprocess.Popen(['python3.3', 'sync_server.py'])
        self.addCleanup(self.stop_server)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while True:
            try:
                self.socket.connect((self.HOST, self.PORT))
            except ConnectionRefusedError:
                time.sleep(0.01)
            else:
                break

    def stop_server(self):
        if self.server.poll() is None:
            os.kill(self.server.pid, signal.SIGINT)

    def test_connect(self):
        packet = Connect().pack()
        self.socket.sendall(packet)
        reply = Packet.unpack(get_msg(self.socket))
        self.assertIsInstance(reply, Connected)
        self.assertTrue(hasattr(reply, 'session'))

    def test_ping(self):
        packet = Ping().pack()
        self.socket.sendall(packet)
        reply = Packet.unpack(get_msg(self.socket))
        self.assertIsInstance(reply, Pong)

    def test_pingd(self):
        packet = PingD(data='test_data')
        serialized_packet = packet.pack()
        self.socket.sendall(serialized_packet)
        reply = Packet.unpack(get_msg(self.socket))
        self.assertIsInstance(reply, PongD)
        self.assertEqual(packet.data, reply.data)

    def test_quit(self):
        packet = Quit().pack()
        self.socket.sendall(packet)
        reply = Packet.unpack(get_msg(self.socket))
        self.assertIsInstance(reply, AckQuit)
        self.assertTrue(hasattr(reply, 'session'))

    def test_finish(self):
        packet = Finish().pack()
        self.socket.sendall(packet)
        reply = Packet.unpack(get_msg(self.socket))
        self.assertIsInstance(reply, AckFinish)
        self.server.wait(timeout=self.TERMINATE_TIMEOUT)
        self.assertTrue(self.server.poll() is not None)


if __name__ == '__main__':
    import unittest
    unittest.main()