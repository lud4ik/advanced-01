from collections import OrderedDict

from .fields import Field, Int, Cmd
from .exceptions import FieldDeclarationError, ValidationError


class Namespace(OrderedDict):

    def __init__(self, bases):
        super().__init__()
        self._cmd = None
        self._fields = OrderedDict()
        self._set_bases_fields(bases)

    def _set_bases_fields(self, bases):
        for cls in bases:
            if issubclass(cls, Packet) and cls is not Packet:
                self._fields.update(cls._fields)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)

        if isinstance(value, Cmd):
            self._cmd = value

        if isinstance(value, Field):
            value.name = key
            self._fields[key] = value


class MetaPacket(type):

    packets = {}

    def __prepare__(name, bases):
        return Namespace(bases)

    def __init__(cls, name, bases, dct):
        type.__init__(cls, name, bases, dct)
        if not bases: return

        cls._fields = dct._fields

        if not (cls._fields and isinstance(next(iter(cls._fields.values())), Cmd)):
            raise FieldDeclarationError('Command shoud be first field.')

        if dct._cmd.id in cls.__class__.packets:
            raise FieldDeclarationError('Dublicate registered command.')

        cls.__class__.packets[dct._cmd.id] = cls


class Packet(metaclass=MetaPacket):

    def __init__(self, **kwargs):
        names = list(self._fields.keys())
        cmd_name, names = names[0], names[1:]
        cmd_val = self._fields[cmd_name]
        cmd_val.__set__(self, cmd_val.id)
        for attr in names:
            value = kwargs.get(attr)
            if value is None:
                raise ValidationError()
            self._fields[attr].__set__(self, value)

    def pack(self):
        result = bytes()
        for attr, _type in self._fields.items():
            result += _type.serialize(getattr(self, attr))

        return Int.serialize(len(result)) + result

    @classmethod
    def unpack(cls, data: bytes):
        kwargs = {}
        pack_cls = cls.__class__.packets.get(data[0])
        if pack_cls is None:
            raise ValidationError()

        tail = data
        for attr, _type in pack_cls._fields.items():
            value, tail = _type.deserialize(tail)
            kwargs[attr] = value

        return pack_cls(**kwargs)


def feed():
    LENGTH = 4
    buffer = bytes()
    while True:
        while len(buffer) < LENGTH:
            buffer += yield None

        _len, buffer = Int.deserialize(buffer)

        while len(buffer) < _len:
            buffer += yield None

        try:
            packet = Packet.unpack(buffer[:_len])
        except ValidationError:
            packet = None
        finally:
            buffer = buffer[_len:]
            buffer += yield packet
