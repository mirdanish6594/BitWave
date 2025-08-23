# peer_protocol.py
# Manages the connection and communication with a single peer.

import asyncio
import struct
import logging
import time
from typing import Tuple, Set

class Downloader:
    pass

class PeerProtocol:
    PIPELINE_SIZE = 15

    def __init__(self, peer_ip: str, peer_port: int, downloader: 'Downloader', message_queue: asyncio.Queue):
        self.ip = peer_ip
        self.port = peer_port
        self.downloader = downloader
        self.torrent = downloader.torrent
        self.reader = None
        self.writer = None
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

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.ip, self.port), timeout=5.0
            )
            logging.info(f"TCP Connection successful with {self.ip}:{self.port}")
            await self._handshake()
            return True
        except Exception as e:
            logging.warning(f"Failed to establish protocol with peer {self.ip}:{self.port} - {e}")
            if self.writer: self.writer.close()
            return False

    async def _handshake(self):
        pstr = b'BitTorrent protocol'
        handshake_msg = struct.pack('!B19s8x20s20s', len(pstr), pstr, self.torrent.info_hash, self.torrent.peer_id.encode())
        self.writer.write(handshake_msg)
        await self.writer.drain()
        try:
            response = await asyncio.wait_for(self.reader.readexactly(68), timeout=20.0)
            _, _, info_hash_resp, _ = struct.unpack('!B19s8x20s20s', response)
            if info_hash_resp != self.torrent.info_hash:
                raise ValueError("Info hash mismatch")
            logging.info(f"Handshake successful with {self.ip}:{self.port}")
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            raise Exception("Handshake timed out, peer did not respond.")
        except ValueError as e:
            raise Exception(f"Handshake validation failed: {e}")

    async def start_communication_loop(self):
        try:
            while not self.downloader.piece_manager.is_complete():
                length_prefix = await asyncio.wait_for(self.reader.readexactly(4), timeout=120.0)
                msg_len = struct.unpack('!I', length_prefix)[0]

                if msg_len == 0: continue
                msg_id = (await self.reader.readexactly(1))[0]
                payload = await self.reader.readexactly(msg_len - 1) if msg_len > 1 else b''
                
                now = time.time()
                elapsed = now - self.last_rate_calculation_time
                if elapsed > 5:
                    self.download_rate = self.downloaded_bytes / elapsed
                    self.downloaded_bytes = 0
                    self.last_rate_calculation_time = now

                if msg_id == 0: self.peer_choking = True
                elif msg_id == 1: 
                    self.peer_choking = False
                    await self._fill_request_pipeline()
                elif msg_id == 2: self.peer_interested = True
                elif msg_id == 3: self.peer_interested = False
                elif msg_id == 4:
                    piece_index = struct.unpack('!I', payload)[0]
                    byte_index, bit_index = divmod(piece_index, 8)
                    self.bitfield[byte_index] |= (1 << (7 - bit_index))
                    if not self.am_interested: await self._send_interested()
                elif msg_id == 5:
                    self.bitfield = bytearray(payload)
                    if not self.am_interested: await self._send_interested()
                elif msg_id == 7:
                    self.downloaded_bytes += len(payload) - 8
                    await self.message_queue.put((self, msg_id, payload))

        except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.TimeoutError) as e:
            logging.warning(f"Connection lost with peer {self.ip}:{self.port} - {e.__class__.__name__}")
        finally:
            await self.downloader.peer_disconnected(self)
            # --- MODIFICATION: Final safety check before closing ---
            if self.writer and not self.writer.is_closing():
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except (RuntimeError, ConnectionResetError):
                    pass # Ignore errors during final cleanup

    async def _send_message(self, msg_id: int, payload: bytes = b''):
        if self.writer.is_closing(): return
        try:
            msg_len = len(payload) + 1
            msg = struct.pack('!IB', msg_len, msg_id) + payload
            self.writer.write(msg)
            await self.writer.drain()
        except ConnectionResetError:
            logging.warning(f"Could not send to {self.ip}, connection was reset.")
            self.writer.close()

    async def _send_interested(self):
        self.am_interested = True
        await self._send_message(2)

    async def _fill_request_pipeline(self):
        if self.peer_choking: return
        while len(self.outstanding_requests) < self.PIPELINE_SIZE:
            block_request = await self.downloader.piece_manager.get_next_block_to_request(self)
            if block_request:
                index, begin, length = block_request
                payload = struct.pack('!III', index, begin, length)
                await self._send_message(6, payload)
                self.outstanding_requests.add((index, begin, length, time.time()))
            else:
                break

    async def send_choke(self):
        if not self.am_choking:
            self.am_choking = True
            await self._send_message(0)

    async def send_unchoke(self):
        if self.am_choking:
            self.am_choking = False
            await self._send_message(1)
            
    async def send_cancel(self, index: int, begin: int, length: int):
        payload = struct.pack('!III', index, begin, length)
        await self._send_message(8, payload)

    def _parse_piece_message(self, payload: bytes) -> Tuple[int, int, bytes]:
        index, begin = struct.unpack('!II', payload[:8])
        block = payload[8:]
        return index, begin, block

    def has_piece(self, piece_index: int) -> bool:
        if piece_index // 8 >= len(self.bitfield): return False
        byte_index, bit_index = divmod(piece_index, 8)
        return (self.bitfield[byte_index] >> (7 - bit_index)) & 1 == 1
