import struct
import logging
import bitstring

REQUEST_SIZE = 2**14  # 16KB default request size for blocks

class PeerMessage:
    """
    Base class for all PeerMessages in the protocol. Each message type will inherit from this.
    """
    KeepAlive = -1
    Choke = 0
    Unchoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8

    @staticmethod
    def decode(data: bytes):
        """
        Decodes the raw bytes into the corresponding PeerMessage object.
        """
        length = struct.unpack('>I', data[:4])[0]
        if length == 0:
            return KeepAlive()
        message_id = struct.unpack('>b', data[4:5])[0]
        if message_id == PeerMessage.Choke:
            return Choke()
        elif message_id == PeerMessage.Unchoke:
            return Unchoke()
        elif message_id == PeerMessage.Interested:
            return Interested()
        elif message_id == PeerMessage.NotInterested:
            return NotInterested()
        elif message_id == PeerMessage.Have:
            return Have.decode(data)
        elif message_id == PeerMessage.BitField:
            return BitField.decode(data)
        elif message_id == PeerMessage.Request:
            return Request.decode(data)
        elif message_id == PeerMessage.Piece:
            return Piece.decode(data)
        elif message_id == PeerMessage.Cancel:
            return Cancel.decode(data)
        else:
            raise ValueError(f"Unknown message id: {message_id}")

class KeepAlive(PeerMessage):
    """
    The KeepAlive message is just used to keep the connection alive. It has no payload.
    Message format:
        <len=0000>
    """
    def __str__(self):
        return 'KeepAlive'

class PeerConnection:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = None  # Initialize socket connection

    def stop(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def connect(self):
        # Code to establish a connection to the peer
        pass

    def send_message(self, message: PeerMessage):
        # Code to send a message to the peer
        try:
            self.socket.sendall(message.encode())
            logging.debug(f'Sent message: {message}')
        except Exception as e:
            logging.error(f'Error sending message: {e}')

    def receive_message(self):
        # Code to receive a message from the peer
        try:
            data = self.socket.recv(4096)  # Adjust buffer size as needed
            message = PeerMessage.decode(data)
            logging.debug(f'Received message: {message}')
            return message
        except Exception as e:
            logging.error(f'Error receiving message: {e}')
            return None

class BitField(PeerMessage):
    """
    The BitField is a message with variable length where the payload is a
    bit array representing all the bits a peer has (1) or does not have (0).
    Message format:
        <len=0001+X><id=5><bitfield>
    """
    def __init__(self, data):
        self.bitfield = bitstring.BitArray(bytes=data)

    def encode(self) -> bytes:
        """
        Encodes this object instance to the raw bytes representing the entire message.
        """
        bits_length = len(self.bitfield)
        return struct.pack('>Ib' + str(bits_length) + 's',
                           1 + bits_length,
                           PeerMessage.BitField,
                           self.bitfield.bytes)

    @classmethod
    def decode(cls, data: bytes):
        message_length = struct.unpack('>I', data[:4])[0]
        logging.debug('Decoding BitField of length: {length}'.format(length=message_length))
        parts = struct.unpack('>Ib' + str(message_length - 1) + 's', data)
        return cls(parts[2])

    def __str__(self):
        return 'BitField'

class Interested(PeerMessage):
    """
    The interested message is fixed length and has no payload other than the message identifier.
    Message format:
        <len=0001><id=2>
    """
    def encode(self) -> bytes:
        """
        Encodes this object instance to the raw bytes representing the entire message.
        """
        return struct.pack('>Ib', 1, PeerMessage.Interested)

    def __str__(self):
        return 'Interested'

class NotInterested(PeerMessage):
    """
    The not interested message is fixed length and has no payload other than the message identifier.
    Message format:
        <len=0001><id=3>
    """
    def encode(self) -> bytes:
        return struct.pack('>Ib', 1, PeerMessage.NotInterested)

    def __str__(self):
        return 'NotInterested'

class Choke(PeerMessage):
    """
    The choke message tells the other peer to stop sending request messages until unchoked.
    Message format:
        <len=0001><id=0>
    """
    def encode(self) -> bytes:
        return struct.pack('>Ib', 1, PeerMessage.Choke)

    def __str__(self):
        return 'Choke'

class Unchoke(PeerMessage):
    """
    Unchoking a peer allows that peer to start requesting pieces.
    Message format:
        <len=0001><id=1>
    """
    def encode(self) -> bytes:
        return struct.pack('>Ib', 1, PeerMessage.Unchoke)

    def __str__(self):
        return 'Unchoke'

class Have(PeerMessage):
    """
    Represents a piece successfully downloaded by the remote peer.
    Message format:
        <len=0005><id=4><index>
    """
    def __init__(self, index: int):
        self.index = index

    def encode(self) -> bytes:
        return struct.pack('>IbI', 5, PeerMessage.Have, self.index)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Have of length: {length}'.format(length=len(data)))
        index = struct.unpack('>IbI', data)[2]
        return cls(index)

    def __str__(self):
        return f'Have(index={self.index})'

class Request(PeerMessage):
    """
    The message used to request a block of a piece (i.e., a partial piece).
    Message format:
        <len=0013><id=6><index><begin><length>
    """
    def __init__(self, index: int, begin: int, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self) -> bytes:
        return struct.pack('>IbIII', 13, PeerMessage.Request, self.index, self.begin, self.length)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Request of length: {length}'.format(length=len(data)))
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return f'Request(index={self.index}, begin={self.begin}, length={self.length})'

class Piece(PeerMessage):
    """
    Represents a block of data (partial piece).
    Message format:
        <len><id=7><index><begin><block>
    """
    length = 9

    def __init__(self, index: int, begin: int, block: bytes):
        self.index = index
        self.begin = begin
        self.block = block

    def encode(self) -> bytes:
        message_length = Piece.length + len(self.block)
        return struct.pack('>IbII' + str(len(self.block)) + 's', message_length, PeerMessage.Piece, self.index, self.begin, self.block)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Piece of length: {length}'.format(length=len(data)))
        length = struct.unpack('>I', data[:4])[0]
        parts = struct.unpack('>IbII' + str(length - Piece.length) + 's', data[:length + 4])
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return f'Piece(index={self.index}, begin={self.begin}, block_size={len(self.block)})'

class Cancel(PeerMessage):
    """
    The cancel message is used to cancel a previously requested block.
    Message format:
         <len=0013><id=8><index><begin><length>
    """
    def __init__(self, index, begin, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self) -> bytes:
        return struct.pack('>IbIII', 13, PeerMessage.Cancel, self.index, self.begin, self.length)

    @classmethod
    def decode(cls, data: bytes):
        logging.debug('Decoding Cancel of length: {length}'.format(length=len(data)))
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return f'Cancel(index={self.index}, begin={self.begin}, length={self.length})'
