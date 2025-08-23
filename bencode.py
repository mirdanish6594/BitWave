# bencode.py
# Contains utility functions for bencoding and bdecoding data.

from typing import Any, Tuple

def bdecode(data: bytes) -> Tuple[Any, bytes]:
    """Decodes bencoded data."""
    if data.startswith(b'i'):
        # Integer: i<integer>e
        end_index = data.find(b'e')
        num = int(data[1:end_index])
        return num, data[end_index + 1:]
    elif data.startswith(b'l'):
        # List: l<bencoded values>e
        items = []
        remaining_data = data[1:]
        while not remaining_data.startswith(b'e'):
            item, remaining_data = bdecode(remaining_data)
            items.append(item)
        return items, remaining_data[1:]
    elif data.startswith(b'd'):
        # Dictionary: d<bencoded string><bencoded value>e
        items = {}
        remaining_data = data[1:]
        while not remaining_data.startswith(b'e'):
            key, remaining_data = bdecode(remaining_data)
            value, remaining_data = bdecode(remaining_data)
            items[key] = value
        return items, remaining_data[1:]
    else:
        # Byte string: <length>:<string>
        colon_index = data.find(b':')
        length = int(data[:colon_index])
        start_index = colon_index + 1
        end_index = start_index + length
        string_data = data[start_index:end_index]
        return string_data, data[end_index:]

def bencode(data: Any) -> bytes:
    """Encodes data into bencode format."""
    if isinstance(data, int):
        return f"i{data}e".encode()
    elif isinstance(data, bytes):
        return f"{len(data)}:".encode() + data
    elif isinstance(data, str):
        return bencode(data.encode())
    elif isinstance(data, list):
        return b"l" + b"".join(bencode(item) for item in data) + b"e"
    elif isinstance(data, dict):
        encoded_dict = b"d"
        # Keys must be sorted
        for key, value in sorted(data.items()):
            encoded_dict += bencode(key) + bencode(value)
        return encoded_dict + b"e"
    else:
        raise TypeError(f"Unsupported type for bencoding: {type(data)}")

