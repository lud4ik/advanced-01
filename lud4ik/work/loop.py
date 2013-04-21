import time
import heapq
import threading
from functools import partial
from select import epoll, EPOLLIN, EPOLLHUP, EPOLLERR

from .delayedcall import DelayedCall


class TimeLoop:

    DEFAULT_TIMEOUT = 1

    def __init__(self):
        self._running = False
        self._soon = []
        self._later = []
        self.timeout = self.DEFAULT_TIMEOUT
        self._soon_lock = threading.RLock()

    def run(self):
        self._running = True

    def process_delayed_calls(self):
        with self._soon_lock:
            soon = self._soon
            self._soon = []

        now = time.monotonic()
        try:
            dc = heapq.heappop(self._later)
            while dc <= now:
                if not dc.cancelled:
                    soon.append(dc)
                dc = heapq.heappop(self._later)
            else:
                self.timeout = dc.when - now
                heapq.heappush(self._later, dc)
        except IndexError:
            self.timeout = self.DEFAULT_TIMEOUT

        for dc in soon:
            if not dc.cancelled:
                dc()
        if self._soon:
            self.timeout = 0

    def stop(self):
        self._running = False

    def call_soon(self, cb, *args):
        dcall = DelayedCall(self, time.monotonic(), cb, args)
        if dcall is not None:
            with self._soon_lock:
                heapq.heappush(self._soon, dcall)
            return dcall

    def call_later(self, delay, cb, *args):
        dcall = DelayedCall(self, time.monotonic() + delay, cb, args)
        if dcall is not None:
            heapq.heappush(self._later, dcall)
            return dcall


def accept(factory, event):
    if event in (EPOLLHUP, EPOLLERR):
        return

    EDGE_MASK = EPOLLIN | EPOLLOUT | EPOLLET | EPOLLHUP | EPOLLERR
    eventloop = factory.eventloop
    conn, addr = factory.socket.accept()
    conn.setblocking(False)
    protocol = factory.create_protocol()
    protocol.connection_made()
    transport = protocol.transport
    transport.conn, transport.protocol = conn, protocol
    eventloop.handlers[conn.fileno()] = protocol.transport
    eventloop.poller.register(conn, EDGE_MASK)


class EventLoop(TimeLoop):

    def __init__(self):
        self.poller = epoll()
        self.handlers = {}
        self._executors = []

    def run_once(self, timeout):
        for (fd, event) in self.poller.poll(timeout):
            self.handlers[fd](event)
            self.process_delayed_calls()

    def run(self):
        super().run()
        while self._running:
            self.run_once(self.timeout)

    def stop(self):
        super.stop()
        for executor in self._executors:
            executor.shutdown(wait=False)

    def run_in_executor(self, executor, cb, *args):
        future = executor.submit(cb, self, *args)
        self._executors.append(executor)
        return future

    def register_factory(self, factory):
        self.handlers[factory.socket.fileno()] = partial(accept, factory)
        self.poller.register(factory.socket, EPOLLIN | EPOLLHUP | EPOLLERR)