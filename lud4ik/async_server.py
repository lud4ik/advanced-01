import socket
from functools import partial
from select import epoll, EPOLLIN, EPOLLOUT, EPOLLET, EPOLLHUP, EPOLLERR

from work.models import cmd
from work.protocol import Feeder
from work.cmdargs import get_cmd_args
from work.utils import get_random_hash


READ_ONLY = EPOLLIN | EPOLLHUP | EPOLLERR
EDGE_MASK = EPOLLIN | EPOLLOUT | EPOLLET | EPOLLHUP | EPOLLERR
ERRORS = (EPOLLHUP, EPOLLERR)


class ClientHandler:

    CHUNK_SIZE = 1024
    commands = [cmd.CONNECT, cmd.PING, cmd.PINGD, cmd.QUIT, cmd.FINISH]

    def __init__(self, server, conn, addr):
        self.server = server
        self.conn = conn
        self.addr = addr
        self.in_buffer = bytes()
        self.out_buffer = bytes()
        self.feeder = Feeder(self.commands)
        self.session = get_random_hash()

    def __call__(self, fd, event):
        if event in ERRORS:
            print('error')
        elif event == EPOLLIN:
            print('EPOLLIN')
        elif event == EPOLLOUT:
            print('EPOLLOUT')
            self.handle_read()

    def handle_write(self):
        sent = self.conn.send(self.out_buffer)
        self.out_buffer = self.out_buffer[sent:]

    def handle_read(self):
        self.in_buffer += self.conn.recv(self.CHUNK_SIZE)
        packet, tail = self.feeder.feed(self.in_buffer)
        self.in_buffer = tail
        if packet:
            process = getattr(self, packet.__class__.__name__.lower())
            process(packet)

    def connect(self, packet):
        reply = packet.reply(self.session)
        self.out_buffer += reply
        self.handle_write()

    def ping(self, packet):
        reply = packet.reply()
        self.out_buffer += reply
        self.handle_write()

    def pingd(self, packet):
        reply = packet.reply()
        self.out_buffer += reply
        self.handle_write()

    def quit(self, packet):
        reply = packet.reply(self.session)
        self.out_buffer += reply
        self.handle_write()
        self.server.quit_client(self.conn)

    def finish(self, packet):
        reply = packet.reply()
        self.out_buffer += reply
        self.handle_write()
        self.server.shutdown()


class AsyncCommandServer:

    MAX_CONN = 5

    def __init__(self, poller, host, port):
        self.clients = []
        self.poller = poller
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setblocking(False)
        self.socket.bind((host, port))
        self.socket.listen(self.MAX_CONN)

    def handle_accept(self, handlers, fd, event):
        if event in ERRORS:
            print('error')
        conn, addr = self.socket.accept()
        self.clients.append(conn)
        self.poller.register(conn, EDGE_MASK)
        handle_client = ClientHandler(self, conn, addr)
        handlers[conn.fileno()] = handle_client

    def quit_client(self, conn):
        self.clients.remove(conn)
        self.poller.unregister(conn.fileno())
        conn.close()

    def shutdown(self):
        self.poller.unregister(self.socket.fileno())
        self.socket.close()
        for conn in self.clients:
            self.poller.unregister(conn.fileno())
            conn.close()
        self.poller.close()
        raise SystemExit()


class Reactor:

    INTERVAL = 0.1

    def __init__(self):
        self.poller = epoll()
        self.handlers = {}

    def register_server(self, sock, handler, mask=READ_ONLY):
        self.handlers[sock.fileno()] = partial(handler, self.handlers)
        self.poller.register(sock, mask)

    def run(self):
        while True:
            for (fd, event) in self.poller.poll(self.INTERVAL):
                self.handlers[fd](fd, event)


if __name__ == '__main__':
    args = get_cmd_args()
    reactor = Reactor()
    async_server = AsyncCommandServer(reactor.poller, args.host, args.port)
    reactor.register_server(async_server.socket, async_server.handle_accept)
    reactor.run()