import os
import signal
import socket
import logging

from work.protocol import feed, Packet
from work.models import cmd, Connected, AckQuit, AckFinish
from work.utils import configure_logging, packet_from_code
from work.cmdargs import get_cmd_args
from work.exceptions import ClientFinishException


def shutdown_handler(signum, frame):
    raise ClientFinishException()


class CommandClient:

    session_id = None
    TIMEOUT = 10.0
    CHUNK_SIZE = 1024
    commands = [cmd.CONNECTED, cmd.PONG, cmd.PONGD, cmd.DELAYED,
                cmd.ACKQUIT, cmd.ACKFINISH]

    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.TIMEOUT)
        self.socket.connect((host, port))

    @classmethod
    def run_client(cls, host, port):
        client = cls(host, port)
        handler = signal.signal(signal.SIGINT, shutdown_handler)
        try:
            client.run()
        except (OSError, ClientFinishException):
            client.shutdown()
        finally:
            signal.signal(signal.SIGINT, handler)

    def run(self):
        self.feeder = feed()
        self.feeder.send(None)
        while True:
            print('Ender command: \n1 - CONNECT;\n2 - PING;\n3 <data> - PINGD;'
                  '\n4 <data> - DELAY;\n5 - QUIT;\n6 - FINISH.\n')
            result = input().split()
            packet = packet_from_code(result)
            self.socket.sendall(packet.pack())
            self.recv_response()

    def recv_response(self, packet=None):
        while not packet:
            packet = self.feeder.send(self.socket.recv(self.CHUNK_SIZE))

        getattr(self, packet.__class__.__name__.lower())(packet)

    def connected(self, packet):
        self.session = packet.session
        print('{} {}'.format(packet.cmd, packet.session))

    def pong(self, packet):
        print(packet.cmd)

    def pongd(self, packet):
        print('{} {}'.format(packet.cmd, packet.data))

    def delayed(self, packet):
        print('{} {}'.format(packet.cmd, packet.data))

    def ackquit(self, packet):
        print('{} {}'.format(packet.cmd, packet.session))
        self.shutdown()

    def ackfinish(self, packet):
        print(packet.cmd)
        self.shutdown()

    def shutdown(self):
        self.socket.close()
        logging.info('socket closed')
        raise SystemExit()


if __name__ == '__main__':
    configure_logging('Client')
    args = get_cmd_args()
    CommandClient.run_client(args.host, args.port)