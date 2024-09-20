import struct
from collections import OrderedDict

class Decoder:
    def __init__(self, data):
        self.data = data
        self.index = 0

    def decode(self):
        try:
            return self.parse()
        except Exception as e:
            raise ValueError(f"Decoding failed: {e}")

    def parse(self):
        if self.data[self.index] == ord('i'):
            return self.parse_int()
        elif self.data[self.index] == ord('l'):
            return self.parse_list()
        elif self.data[self.index] == ord('d'):
            return self.parse_dict()
        else:
            return self.parse_str()

    def parse_int(self):
        self.index += 1
        end = self.data.find(b'e', self.index)
        if end == -1:
            raise ValueError("Invalid integer encoding")
        value = int(self.data[self.index:end])
        self.index = end + 1
        return value

    def parse_str(self):
        colon = self.data.find(b':', self.index)
        if colon == -1:
            raise ValueError("Invalid string encoding")
        length = int(self.data[self.index:colon])
        self.index = colon + 1
        value = self.data[self.index:self.index + length]
        self.index += length
        return value.decode('utf-8')  # Assuming you want strings instead of bytes

    def parse_list(self):
        self.index += 1
        result = []
        while self.data[self.index] != ord('e'):
            result.append(self.parse())
        self.index += 1
        return result

    def parse_dict(self):
        self.index += 1
        result = OrderedDict()
        while self.data[self.index] != ord('e'):
            key = self.parse_str()
            value = self.parse()
            result[key] = value
        self.index += 1
        return result

class Encoder:
    def __init__(self, data):
        self.data = data

    def encode(self):
        if isinstance(self.data, int):
            return b'i%de' % self.data
        elif isinstance(self.data, bytes):
            return b'%d:%s' % (len(self.data), self.data)
        elif isinstance(self.data, str):  # Handle string encoding
            return b'%d:%s' % (len(self.data), self.data.encode('utf-8'))
        elif isinstance(self.data, list):
            return b'l' + b''.join(Encoder(item).encode() for item in self.data) + b'e'
        elif isinstance(self.data, OrderedDict):
            encoded_items = b''.join(Encoder(k if isinstance(k, bytes) else k.encode('utf-8')).encode() + Encoder(v).encode() for k, v in self.data.items())
            return b'd' + encoded_items + b'e'
        else:
            raise TypeError(f"Unsupported data type for encoding: {type(self.data)}")

