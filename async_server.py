from operator import attrgetter, methodcaller

from work.models import cmd
from work.protocol import feed
from work.cmdargs import get_cmd_args
from work.utils import get_random_hash
from work.loop import EventLoop
from work.layer import Factory, Protocol


class CommandProtocol(Protocol):

    def connection_made(self):
        self.feeder = feed()
        next(self.feeder)
        self.session = get_random_hash()

    def data_received(self, data):
        packet = self.feeder.send(data)
        if packet:
            getattr(self, packet.__class__.__name__.lower())(packet)

    def send_to_all(self, data):
        for client in self.factory.clients[:]:
            client.transport.write(data)

    def connect(self, packet):
        self.send_to_all(packet.reply(self.session))

    def ping(self, packet):
        self.transport.write(packet.reply())

    def pingd(self, packet):
        self.transport.write(packet.reply())

    def quit(self, packet):
        self.send_to_all(packet.reply(self.session))
        self.connection_lost()

    def finish(self, packet):
        self.send_to_all(packet.reply(self.session))
        self.factory.close()


if __name__ == '__main__':
    args = get_cmd_args()
    eventloop = EventLoop()
    factory = Factory(eventloop, CommandProtocol)
    factory.listen(args.host, args.port)
    eventloop.run()