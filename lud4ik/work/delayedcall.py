from numbers import Number
from inspect import signature
from functools import total_ordering


@total_ordering
class DelayedCall:

    def __new__(cls, eventloop, when, callback, args, *, check_args=True):
        if check_args:
            if not cls.validate_args(callback, args):
                return
        return super().__new__(cls)

    def __init__(self, eventloop, when, callback, args, *, check_args=True):
        self.eventloop = eventloop
        self.when = when
        self.callback = callback
        self.args = args
        self.cancelled = False

    @staticmethod
    def validate_args(callback, args):
        try:
            assert callable(callback), ('callback should be any callable, '
                                            'got {!r}'.format(callback))
            sig = signature(callback)
            sig.bind(*args)
        except (TypeError, AssertionError):
            return
        else:
            return True

    def __eq__(self, other):
        if isinstance(other, Number):
            return self.when == other
        if not isinstance(other, DelayedCall):
            return NotImplemented
        return (self.when == other.when and
                self.callback == other.callback and
                self.args == other.args)

    def __lt__(self, other):
        if isinstance(other, Number):
            return self.when < other
        if not isinstance(other, DelayedCall):
            return NotImplemented
        return self.when < other.when

    def __call__(self):
        self.callback(self.eventloop, *self.args)

    def cancel(self):
        self.cancelled = True