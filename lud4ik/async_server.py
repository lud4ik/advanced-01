import socket
from operator import attrgetter
from select import epoll, EPOLLIN, EPOLLOUT, EPOLLET, EPOLLHUP, EPOLLERR

from work.models import cmd
from work.protocol import Feeder
from work.cmdargs import get_cmd_args
from work.utils import get_random_hash
from work.loop import EventLoop


class ClientHandler:

    ERRORS = (EPOLLHUP, EPOLLERR)
    CHUNK_SIZE = 1024
    commands = [cmd.CONNECT, cmd.PING, cmd.PINGD, cmd.DELAY, cmd.QUIT, cmd.FINISH]

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

    def write_to_buffer(self, data):
        self.out_buffer += data

    def delayed_write(self, event_loop, data):
        self.write_to_buffer(data)
        self.handle_write() # hack

    def delayed_reply_to_all(self, eventloop, reply):
        self.server.reply_to_all(reply)
        self.handle_write() # hack

    def connect(self, packet):
        reply = packet.reply(self.session)
        self.server.reply_to_all(reply)

    def ping(self, packet):
        reply = packet.reply()
        self.out_buffer += reply

    def pingd(self, packet):
        reply = packet.reply()
        self.server.event_loop.call_later(5, self.delayed_reply_to_all, reply)

    def delay(self, packet):
        reply = packet.reply()
        self.server.event_loop.call_later(5, self.delayed_write, reply)

    def quit(self, packet):
        reply = packet.reply(self.session)
        self.server.reply_to_all(reply)
        self.server.quit_client(self)

    def finish(self, packet):
        reply = packet.reply()
        self.server.reply_to_all(reply)
        self.server.shutdown()


class AsyncCommandServer:

    MAX_CONN = 5
    ERRORS = (EPOLLHUP, EPOLLERR)
    EDGE_MASK = EPOLLIN | EPOLLOUT | EPOLLET | EPOLLHUP | EPOLLERR

    def __init__(self, event_loop, host, port):
        self.clients = []
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setblocking(False)
        self.socket.bind((host, port))
        self.socket.listen(self.MAX_CONN)
        self.event_loop = event_loop
        event_loop.register_server(self.socket, self.handle_accept)

    def handle_accept(self, handlers, fd, event):
        if event in self.ERRORS:
            print('error')
        conn, addr = self.socket.accept()
        conn.setblocking(False)
        self.event_loop.poller.register(conn, self.EDGE_MASK)
        client_handler = ClientHandler(self, conn, addr)
        self.clients.append(client_handler)
        handlers[conn.fileno()] = client_handler

    def quit_client(self, client):
        self.clients.remove(client)
        self.event_loop.poller.unregister(client.conn.fileno())
        client.conn.close()

    def reply_to_all(self, data):
        for client in self.clients:
            client.write_to_buffer(data)

    def shutdown(self):
        poller = self.event_loop.poller
        poller.unregister(self.socket.fileno())
        self.socket.close()
        for conn in map(attrgetter('conn'), self.clients):
            poller.unregister(conn.fileno())
            conn.close()
        poller.close()
        raise SystemExit()


if __name__ == '__main__':
    args = get_cmd_args()
    event_loop = EventLoop()
    async_server = AsyncCommandServer(event_loop, args.host, args.port)
    event_loop.run()