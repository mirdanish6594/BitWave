# peer_protocol.py
# Converted to use eventlet for cooperative multitasking.

import struct
import logging
import time
from typing import Tuple, Set

import eventlet
from eventlet.green import socket
from eventlet.timeout import Timeout

class Downloader:
    pass

class PeerProtocol:
    PIPELINE_SIZE = 15

    def __init__(self, peer_ip: str, peer_port: int, downloader: 'Downloader', message_queue: eventlet.queue.Queue):
        self.ip = peer_ip
        self.port = peer_port
        self.downloader = downloader
        self.torrent = downloader.torrent
        self.sock = None
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.bitfield = bytearray(-(-self.torrent.num_pieces // 8))
        self.outstanding_requests: Set[Tuple[int, int, int, float]] = set()
        self.message_queue = message_queue
        self.downloaded_bytes = 0
        self.last_rate_calculation_time = time.time()
        self.download_rate = 0.0

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with Timeout(5):
                self.sock.connect((self.ip, self.port))
            logging.info(f"TCP Connection successful with {self.ip}:{self.port}")
            self._handshake()
            return True
        except Exception as e:
            logging.warning(f"Failed to establish protocol with peer {self.ip}:{self.port} - {e}")
            if self.sock: self.sock.close()
            return False

    def _handshake(self):
        pstr = b'BitTorrent protocol'
        handshake_msg = struct.pack('!B19s8x20s20s', len(pstr), pstr, self.torrent.info_hash, self.torrent.peer_id.encode())
        self.sock.sendall(handshake_msg)
        with Timeout(20):
            response = self._recv_all(68)
        _, _, info_hash_resp, _ = struct.unpack('!B19s8x20s20s', response)
        if info_hash_resp != self.torrent.info_hash:
            raise ValueError("Info hash mismatch")
        logging.info(f"Handshake successful with {self.ip}:{self.port}")

    def start_communication_loop(self):
        try:
            while not self.downloader.piece_manager.is_complete():
                with Timeout(120):
                    length_prefix = self._recv_all(4)
                if not length_prefix: break
                msg_len = struct.unpack('!I', length_prefix)[0]

                if msg_len == 0: continue
                
                with Timeout(120):
                    message_body = self._recv_all(msg_len)
                if not message_body: break

                msg_id = message_body[0]
                payload = message_body[1:]
                
                now = time.time()
                elapsed = now - self.last_rate_calculation_time
                if elapsed > 5:
                    self.download_rate = self.downloaded_bytes / elapsed
                    self.downloaded_bytes = 0
                    self.last_rate_calculation_time = now

                if msg_id == 0: self.peer_choking = True
                elif msg_id == 1: 
                    self.peer_choking = False
                    self._fill_request_pipeline()
                elif msg_id == 2: self.peer_interested = True
                elif msg_id == 3: self.peer_interested = False
                elif msg_id == 4:
                    piece_index = struct.unpack('!I', payload)[0]
                    byte_index, bit_index = divmod(piece_index, 8)
                    self.bitfield[byte_index] |= (1 << (7 - bit_index))
                    if not self.am_interested: self._send_interested()
                elif msg_id == 5:
                    self.bitfield = bytearray(payload)
                    if not self.am_interested: self._send_interested()
                elif msg_id == 7:
                    self.downloaded_bytes += len(payload) - 8
                    self.message_queue.put((self, msg_id, payload))
        except (Timeout, OSError, ValueError) as e:
            logging.warning(f"Connection lost with peer {self.ip}:{self.port} - {e.__class__.__name__}")
        finally:
            self.downloader.peer_disconnected(self)
            if self.sock: self.sock.close()

    def _recv_all(self, n):
        """Helper to receive n bytes from a socket."""
        data = bytearray()
        while len(data) < n:
            packet = self.sock.recv(n - len(data))
            if not packet:
                return None
            data.extend(packet)
        return data

    def _send_message(self, msg_id: int, payload: bytes = b''):
        try:
            msg_len = len(payload) + 1
            msg = struct.pack('!IB', msg_len, msg_id) + payload
            self.sock.sendall(msg)
        except OSError:
            logging.warning(f"Could not send to {self.ip}, connection was reset.")
            self.sock.close()

    def _send_interested(self):
        self.am_interested = True
        self._send_message(2)

    def _fill_request_pipeline(self):
        if self.peer_choking: return
        while len(self.outstanding_requests) < self.PIPELINE_SIZE:
            block_request = self.downloader.piece_manager.get_next_block_to_request(self)
            if block_request:
                index, begin, length = block_request
                payload = struct.pack('!III', index, begin, length)
                self._send_message(6, payload)
                self.outstanding_requests.add((index, begin, length, time.time()))
            else:
                break

    def send_choke(self):
        if not self.am_choking:
            self.am_choking = True
            self._send_message(0)

    def send_unchoke(self):
        if self.am_choking:
            self.am_choking = False
            self._send_message(1)
            
    def send_cancel(self, index: int, begin: int, length: int):
        payload = struct.pack('!III', index, begin, length)
        self._send_message(8, payload)

    def _parse_piece_message(self, payload: bytes) -> Tuple[int, int, bytes]:
        index, begin = struct.unpack('!II', payload[:8])
        block = payload[8:]
        return index, begin, block

    def has_piece(self, piece_index: int) -> bool:
        if piece_index // 8 >= len(self.bitfield): return False
        byte_index, bit_index = divmod(piece_index, 8)
        return (self.bitfield[byte_index] >> (7 - bit_index)) & 1 == 1
