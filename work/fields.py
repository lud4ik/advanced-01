from .exceptions import ValidationError


class Field:
    _type = NotImplemented

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__dict__[self.name]

    def __set__(self, instance, value):
        if value.__class__ != self._type:
            raise ValidationError()
        if hasattr(self, 'validate'):
            self.validate(value)
        instance.__dict__[self.name] = value


class Cmd(Field):
    _type = int
    serialize = staticmethod(lambda x: x.to_bytes(1, 'little'))
    deserialize = staticmethod(lambda data: (data[0], data[1:]))

    def __init__(self, _id):
        self.id = _id


class Int(Field):
    _type = int

    @staticmethod
    def serialize(value):
        return value.to_bytes(4, 'little')

    @staticmethod
    def deserialize(value):
        return (int.from_bytes(value[:4], 'little'), value[4:])


class Str(Field):
    _type = str

    def __init__(self, maxsize):
        self.maxsize = maxsize

    def validate(self, value):
        if len(value) > self.maxsize:
            raise ValidationError()

    @staticmethod
    def serialize(value):
        data = bytes(value, 'utf-8')
        return Int.serialize(len(data)) + data

    @staticmethod
    def deserialize(value):
        _len, tail = Int.deserialize(value)
        data, tail = tail[:_len], tail[_len:]
        return (data.decode('utf-8'), tail)