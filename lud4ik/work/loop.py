import time
import heapq
import threading
from functools import partial
from select import epoll, EPOLLIN, EPOLLHUP, EPOLLERR

from .delayedcall import DelayedCall


class EventLoop:

    DEFAULT_TIMEOUT = 1
    READ_ONLY = EPOLLIN | EPOLLHUP | EPOLLERR

    def __init__(self):
        self.poller = epoll()
        self.handlers = {}
        self._running = False
        self._soon = []
        self._later = []
        self._executors = []
        self.timeout = self.DEFAULT_TIMEOUT
        self._soon_lock = threading.RLock()

    def run_once(self, timeout):
        for (fd, event) in self.poller.poll(timeout):
            self.handlers[fd](fd, event)
            self.process_delayed_calls()

    def run(self):
        self._running = True
        while self._running:
            for (fd, event) in self.poller.poll(self.timeout):
                self.handlers[fd](fd, event)
                self.process_delayed_calls()

    def process_delayed_calls(self):
        with self._soon_lock:
            soon = self._soon
            self._soon = []

        now = time.monotonic()
        try:
            dc = heapq.heappop(self._later)
            while dc <= now:
                if not cb.cancelled:
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
        for executor in self._executors:
            executor.shutdown(wait=False)

    def call_soon(self, cb, *args):
        dcall = DelayedCall(self, time.monotonic(), cb, args)
        if dcall is not None:
            heapq.heappush(self._soon, dcall)
            return dcall

    def call_later(self, delay, cb, *args):
        dcall = DelayedCall(self, time.monotonic() + delay, cb, args)
        if dcall is not None:
            heapq.heappush(self._later, dcall)
            return dcall

    def call_soon_threadsafe(self, cb, *args):
        dcall = DelayedCall(self, time.monotonic(), cb, args)
        if dcall is not None:
            with self._soon_lock:
                heapq.heappush(self._soon, dcall)
            return dcall

    def run_in_executor(self, executor, cb, *args):
        future = executor.submit(cb, self, *args)
        self._executors.append(executor)
        return future

    def register_server(self, sock, handler, mask=READ_ONLY):
        self.handlers[sock.fileno()] = partial(handler, self.handlers)
        self.poller.register(sock, mask)