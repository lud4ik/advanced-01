import abc
import socket
from select import EPOLLIN, EPOLLOUT, EPOLLHUP, EPOLLERR

from .protocol import feed


class Transport:

    CHUNK_SIZE = 1024

    def __init__(self, eventloop):
        self.conn = None
        self.eventloop = eventloop
        self.in_buffer = bytearray()
        self.out_buffer = bytearray()

    def write(self, data):
        self.out_buffer += data

    def abort(self):
        self.eventloop.poller.unregister(self.conn.fileno())
        self.eventloop.handlers.pop(self.conn.fileno(), None)
        self.protocol.factory.clients.remove(self.conn)
        self.conn.close()

    def __call__(self, event):
        if any(event & e for e in (EPOLLHUP, EPOLLERR)):
            return
        if event & EPOLLIN:
            try:
                while True:
                    _input = self.conn.recv(self.CHUNK_SIZE)
                    if not _input:
                        break
                    self.in_buffer += _input
            except BlockingIOError:
                pass
            except OSError as exc:
                self.protocol.connection_lost(exc)
            self.protocol.data_received(self.in_buffer)
            self.in_buffer.clear()
        if event & EPOLLOUT:
            try:
                sent = self.conn.send(self.out_buffer)
                self.out_buffer = self.out_buffer[sent:]
            except BlockingIOError:
                pass
            except OSError as exc:
                self.protocol.connection_lost(exc)


class Factory:

    MAX_CONN = 5

    def __init__(self, eventloop, protocol):
        self.eventloop = eventloop
        self.protocol = protocol
        self.socket = self.create_server()
        self.clients = []

    def create_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        return sock

    def listen(self, host, port):
        self.socket.bind((host, port))
        self.eventloop.register_factory(self)
        self.socket.listen(self.MAX_CONN)

    def create_protocol(self):
        transport  = Transport(self.eventloop)
        self.clients.append(transport.conn)
        protocol = self.protocol(transport)
        protocol.factory = self
        return protocol

    def close(self):
        poller = self.eventloop.poller
        poller.unregister(self.socket.fileno())
        self.socket.close()
        for conn in self.clients[:]:
            poller.unregister(conn.fileno())
            client.close()


class Protocol(metaclass=abc.ABCMeta):

    def __init__(self, transport):
        self.transport = transport

    @abc.abstractmethod
    def connection_made(self):
        pass

    @abc.abstractmethod
    def data_received(self, data):
        pass

    def connection_lost(self, reason=None):
        if self.transport:
            self.transport.abort()
        self.transport = None