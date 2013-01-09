from .protocol import Packet
from .fields import Cmd, Str


class cmd:
    CONNECT = 1
    PING = 2
    PINGD = 3
    DELAY = 4
    QUIT = 5
    FINISH = 6
    CONNECTED = 7
    PONG = 8
    PONGD = 9
    DELAYED = 10
    ACKQUIT = 11
    ACKFINISH = 12


class Connected(Packet):
    cmd = Cmd(cmd.CONNECTED)
    session = Str(maxsize=256)


class Pong(Packet):
    cmd = Cmd(cmd.PONG)


class PongD(Packet):
    cmd = Cmd(cmd.PONGD)
    data = Str(maxsize=256)


class Delayed(PongD):
    cmd = Cmd(cmd.DELAYED)


class AckQuit(Packet):
    cmd = Cmd(cmd.ACKQUIT)
    session = Str(maxsize=256)


class AckFinish(Packet):
    cmd = Cmd(cmd.ACKFINISH)


class Connect(Packet):
    cmd = Cmd(cmd.CONNECT)

    def reply(self, session):
        return Connected(session=session).pack()


class Ping(Packet):
    cmd = Cmd(cmd.PING)

    def reply(self):
        return Pong().pack()


class PingD(Packet):
    cmd = Cmd(cmd.PINGD)
    data = Str(maxsize=256)

    def reply(self):
        return PongD(data=self.data).pack()


class Delay(PingD):
    cmd = Cmd(cmd.DELAY)

    def reply(self):
        return Delayed(data=self.data).pack()


class Quit(Packet):
    cmd = Cmd(cmd.QUIT)

    def reply(self, session):
        return AckQuit(session=session).pack()


class Finish(Packet):
    cmd = Cmd(cmd.FINISH)

    def reply(self):
        return AckFinish().pack()