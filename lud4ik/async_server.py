import os
import os.path
import socket
import signal
import logging
import threading
from functools import partial
from operator import attrgetter
from collections import namedtuple
from select import epoll, EPOLLIN, EPOLLOUT, EPOLLET, EPOLLHUP, EPOLLERR

from work.protocol import Feeder
from work.models import cmd
from work.cmdargs import get_cmd_args
from work.exceptions import ServerFinishException
from work.utils import get_random_hash, handle_timeout, configure_logging


READ_ONLY = EPOLLIN | EPOLLHUP | EPOLLERR
EDGE_MASK = EPOLLIN | EPOLLOUT | EPOLLET | EPOLLHUP | EPOLLERR
ERRORS = (EPOLLHUP, EPOLLERR)


class ClientHandler:

    CHUNK_SIZE = 1024
    commands = [cmd.CONNECT, cmd.PING, cmd.PINGD, cmd.QUIT, cmd.FINISH]

    def __init__(self, conn, addr):
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
            self.handle_read()
        elif event == EPOLLOUT:
            if self.out_buffer:
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


class AsyncCommandServer:

    MAX_CONN = 5

    def __init__(self, poller, host, port):
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
        self.poller.register(conn, EDGE_MASK)
        handle_client = ClientHandler(conn, addr)
        handlers[conn.fileno()] = handle_client


def main():
    args = get_cmd_args()

    poller = epoll()
    async_server = AsyncCommandServer(poller, args.host, args.port)
    handlers = {}
    handlers[async_server.socket.fileno()] = partial(async_server.handle_accept,
                                                     handlers)
    poller.register(async_server.socket, READ_ONLY)

    while True:
        for (fd, event) in poller.poll():
            handlers[fd](fd, event)


if __name__ == '__main__':
    configure_logging('Server')
    main()