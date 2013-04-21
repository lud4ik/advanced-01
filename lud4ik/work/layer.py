import abc
import socket

from .protocol import feed


class Transport:

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
                break
            self.protocol.data_received(self.in_buffer)
            self.in_buffer.clear()
        if event & EPOLLOUT:
            try:
                sent = self.conn.send(self.out_buffer)
                self.out_buffer = self.out_buffer[sent:]
            except OSError as exc:
                self.protocol.connection_lost(exc)


class Factory:

    MAX_CONN = 5

    def __init__(self, eventloop, protocol):
        self.eventloop = eventloop
        self.protocol = protocol
        self.socket = self.create_server()

    def create_server(self):
        socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socket.setblocking(False)
        return socket

    def listen(self, host, port):
        self.socket.bind((host, port))
        self.eventloop.register_factory(self)
        self.socket.listen(self.MAX_CONN)

    def create_protocol(self):
        transport  = Transport(self.eventloop)
        protocol = self.protocol(transport)
        protocol.factory = self
        return protocol

    def close(self):
        self.eventloop.poller.unregister(self.socket.fileno())
        self.socket.close()


class Protocol(metaclass=abc.ABCMeta):

    def __init__(self, transport):
        self.transport = transport

    @abc.abstractmethod
    def connection_made(self):
        pass

    @abc.abstractmethod
    def data_received(self, data):
        pass

    def connection_lost(self, reason):
        if self.transport:
            self.transport.abort()
        self.transport = None