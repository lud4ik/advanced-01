import os
import os.path
import socket
import signal
import logging
import threading
from operator import attrgetter
from collections import namedtuple

from work.protocol import feed
from work.models import cmd
from work.cmdargs import get_cmd_args
from work.exceptions import ServerFinishException
from work.utils import (get_random_hash,
                        handle_timeout,
                        get_keyword_args,
                        configure_logging)


def shutdown_handler(signum, frame):
    raise ServerFinishException()


class CommandServer:

    MAX_CONN = 5
    TIMEOUT = 1.0
    CHUNK_SIZE = 1024
    clients = {}
    commands = [cmd.CONNECT, cmd.PING, cmd.PINGD, cmd.QUIT, cmd.FINISH]
    templ = namedtuple('templ', 'addr, thread, session')

    def __init__(self, host, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(self.TIMEOUT)
        self.socket.bind((host, port))
        self.socket.listen(self.MAX_CONN)

    @classmethod
    def run_server(cls, host, port):
        handler = signal.signal(signal.SIGINT, shutdown_handler)
        server = cls(host, port)
        try:
            server.run()
        except (ServerFinishException, OSError):
            server.shutdown()
        finally:
            signal.signal(signal.SIGINT, handler)

    def run(self):
        while True:
            with handle_timeout():
                conn, addr = self.socket.accept()
                th = threading.Thread(target=self.run_client, args=(conn, ))
                self.clients[conn] = self.templ(addr=addr, thread=th,
                                                session=get_random_hash())
                th.start()

    def run_client(self, conn):
        feeder = feed()
        packet = next(feeder)
        while True:
            try:
                while packet is None:
                    packet = feeder.send(conn.recv(self.CHUNK_SIZE))
                getattr(self, packet.__class__.__name__.lower())(packet, conn)
            except OSError:
                conn.close()
                self.clients.pop(conn, None)
                return
            finally:
                packet = None

    def send_to_all(self, packet, conn):
        session = self.clients[conn].session
        reply = packet.reply(session)
        for client in list(self.clients.keys()):
            client.sendall(reply)

    def connect(self, packet, conn):
        self.send_to_all(packet, conn)

    def ping(self, packet, conn):
        conn.sendall(packet.reply())

    def pingd(self, packet, conn):
        conn.sendall(packet.reply())

    def quit(self, packet, conn):
        self.send_to_all(packet, conn)
        conn.close()
        self.clients.pop(conn, None)
        raise SystemExit()

    def finish(self, packet, conn):
        self.send_to_all(packet, conn)
        os.kill(os.getpid(), signal.SIGINT)
        raise SystemExit()

    def shutdown(self):
        self.socket.close()
        logging.info('socket closed')
        for conn in list(self.clients.keys()):
            conn.close()
        logging.info('connections closed')
        for th in map(attrgetter('thread'), list(self.clients.values())):
            th.join()
        logging.info('threads closed')
        raise SystemExit()


if __name__ == '__main__':
    configure_logging('Server')
    args = get_cmd_args()
    CommandServer.run_server(args.host, args.port)