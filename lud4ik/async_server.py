import heapq
import socket
from functools import partial
from select import epoll, EPOLLIN, EPOLLOUT, EPOLLET, EPOLLHUP, EPOLLERR

from work.models import cmd
from work.protocol import Feeder
from work.cmdargs import get_cmd_args
from work.utils import get_random_hash
from work.delayedcall import DelayedCall


class ClientHandler:

    ERRORS = (EPOLLHUP, EPOLLERR)
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
        if any(event & e for e in self.ERRORS):
            print('error')
        if event & EPOLLIN:
            print('EPOLLIN')
            self.handle_read()
        if event & EPOLLOUT:
            print('EPOLLOUT')
            self.handle_write()

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

    def ping(self, packet):
        reply = packet.reply()
        self.out_buffer += reply

    def pingd(self, packet):
        reply = packet.reply()
        self.out_buffer += reply

    def quit(self, packet):
        reply = packet.reply(self.session)
        self.out_buffer += reply
        self.server.quit_client(self.conn)

    def finish(self, packet):
        reply = packet.reply()
        self.out_buffer += reply
        self.server.shutdown()


class AsyncCommandServer:

    MAX_CONN = 5
    ERRORS = (EPOLLHUP, EPOLLERR)
    EDGE_MASK = EPOLLIN | EPOLLOUT | EPOLLET | EPOLLHUP | EPOLLERR

    def __init__(self, reactor, host, port):
        self.clients = []
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setblocking(False)
        self.socket.bind((host, port))
        self.socket.listen(self.MAX_CONN)
        self.poller = reactor.poller
        reactor.register_server(self.socket, self.handle_accept)


    def handle_accept(self, handlers, fd, event):
        if event in self.ERRORS:
            print('error')
        conn, addr = self.socket.accept()
        self.clients.append(conn)
        self.poller.register(conn, self.EDGE_MASK)
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


class Eventloop:

    timeout = 0.1
    READ_ONLY = EPOLLIN | EPOLLHUP | EPOLLERR

    def __init__(self):
        self.poller = epoll()
        self.handlers = {}
        self.running = False
        self.soon = []
        self.later = []

    def register_server(self, sock, handler, mask=READ_ONLY):
        self.handlers[sock.fileno()] = partial(handler, self.handlers)
        self.poller.register(sock, mask)

    def run_once(self, timeout):
        for (fd, event) in self.poller.poll(timeout):
            self.handlers[fd](fd, event)

    def run(self):
        self.running = True
        while self.running:
            for (fd, event) in self.poller.poll(self.timeout):
                self.handlers[fd](fd, event)

    def stop(self):
        self.running = False

    def call_soon(self, cb, *args):
        dcall = DelayedCall(self, time.monotonic(), cb, args)
        if dcall is not None:
            heapq.heappush(self.later, dcall)
            return dcall

    def call_later(self, delay, cb, *args):
        dcall = DelayedCall(self, time.monotonic() + delay, cb, args)
        if dcall is not None:
            heapq.heappush(self.later, dcall)
            return dcall

    def call_soon_threadsafe(self, cb, *args):
        pass


if __name__ == '__main__':
    args = get_cmd_args()
    eventloop = Eventloop()
    async_server = AsyncCommandServer(reactor, args.host, args.port)
    eventloop.run()