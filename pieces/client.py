import asyncio
import logging
import time
import os
import math
from hashlib import sha1
from asyncio import Queue
from collections import namedtuple
from pieces.protocol import PeerConnection, REQUEST_SIZE
from pieces.tracker import Tracker
from typing import List

MAX_PEER_CONNECTIONS = 40

class TorrentClient:
    def __init__(self, torrent):
        self.is_running = False 
        self.tracker = Tracker(torrent)
        self.available_peers = Queue()
        self.peers = []
        self.piece_manager = PieceManager(torrent)
        self.abort = False

    async def start(self):
        # Initialize peers using host and port
        while len(self.peers) < MAX_PEER_CONNECTIONS and not self.available_peers.empty():
            host, port = await self.available_peers.get()
            self.peers.append(PeerConnection(host, port))

        previous = None
        interval = 30 * 60

        while True:
            if self.piece_manager.complete:
                logging.info('Torrent fully downloaded!')
                break
            if self.abort:
                logging.info('Aborting download...')
                break

            current = time.time()
            if (not previous) or (previous + interval < current):
                response = await self.tracker.connect(
                    uploaded=self.piece_manager.bytes_uploaded,
                    downloaded=self.piece_manager.bytes_downloaded)

                if response:
                    previous = current
                    interval = response['interval']
                    self._empty_queue()
                    for peer in response['peers']:
                        self.available_peers.put_nowait((peer['host'], peer['port']))  # Assuming peers are dicts with 'host' and 'port'
            else:
                await asyncio.sleep(5)
        self.stop()

    def _empty_queue(self):
        while not self.available_peers.empty():
            self.available_peers.get_nowait()

    def stop(self):
        self.abort = True
        for peer in self.peers:
            peer.stop()  # Ensure you have a stop method in PeerConnection
        self.piece_manager.close()
        self.tracker.close()

    def _on_block_retrieved(self, peer_id, piece_index, block_offset, data):
        self.piece_manager.block_received(
            peer_id=peer_id, piece_index=piece_index,
            block_offset=block_offset, data=data)


class Block:
    Missing = 0
    Pending = 1
    Retrieved = 2

    def __init__(self, piece: int, offset: int, length: int):
        self.piece = piece
        self.offset = offset
        self.length = length
        self.status = Block.Missing
        self.data = None


class Piece:
    def __init__(self, index: int, blocks=None, hash_value=None):
        if blocks is None:
            blocks = []
        self.index = index
        self.blocks = blocks
        self.hash = hash_value

    def reset(self):
        for block in self.blocks:
            block.status = Block.Missing

    def next_request(self) -> Block:
        missing = [b for b in self.blocks if b.status is Block.Missing]
        if missing:
            missing[0].status = Block.Pending
            return missing[0]
        return None

    def block_received(self, offset: int, data: bytes):
        matches = [b for b in self.blocks if b.offset == offset]
        block = matches[0] if matches else None
        if block:
            block.status = Block.Retrieved
            block.data = data
        else:
            logging.warning(f'Trying to complete a non-existing block {offset}')

    def is_complete(self) -> bool:
        blocks = [b for b in self.blocks if b.status is not Block.Retrieved]
        return len(blocks) == 0

    @property
    def data(self):
        retrieved = sorted(self.blocks, key=lambda b: b.offset)
        blocks_data = [b.data for b in retrieved]
        return b''.join(blocks_data)


PendingRequest = namedtuple('PendingRequest', ['block', 'added'])

class PieceManager:
    def __init__(self, torrent):
        self.torrent = torrent
        self.peers = {}
        self.pending_blocks = []
        self.missing_pieces = []
        self.ongoing_pieces = []
        self.have_pieces = []
        self.max_pending_time = 300 * 1000  # 5 minutes
        self.missing_pieces = self._initiate_pieces()
        self.total_pieces = len(torrent.pieces)
        # In PieceManager __init__ method
        self.fd = open(os.path.join(os.path.dirname(self.torrent.output_file), 'output_file.bin'), 'ab')


        # In the PieceManager class
        if not hasattr(self.torrent, 'output_file') or not self.torrent.output_file:
         self.torrent.output_file = 'E:\\BitWave\\output_file.bin'  # Simplified default name


        try:
           self.fd = open(os.path.join(os.path.dirname(self.torrent.output_file), 'output_file.bin'), 'ab')
        except PermissionError as e:
            logging.error(f"Permission denied when trying to open the output file: {self.torrent.output_file}. Error: {e}")
            raise
        except Exception as e:
            logging.error(f"An error occurred while trying to open the output file: {self.torrent.output_file}. Error: {e}")
            raise

    def _initiate_pieces(self) -> List[Piece]:
        torrent = self.torrent
        pieces = []
        total_pieces = len(torrent.pieces)
        std_piece_blocks = math.ceil(torrent.piece_length / REQUEST_SIZE)

        for index, hash_value in enumerate(torrent.pieces):
            if index < (total_pieces - 1):
                blocks = [Block(index, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(std_piece_blocks)]
            else:
                last_length = torrent.total_size % torrent.piece_length
                num_blocks = math.ceil(last_length / REQUEST_SIZE)
                blocks = [Block(index, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(num_blocks)]

                if last_length % REQUEST_SIZE > 0:
                    last_block = blocks[-1]
                    last_block.length = last_length % REQUEST_SIZE
                    blocks[-1] = last_block
            pieces.append(Piece(index, blocks, hash_value))
        return pieces

    def close(self):
        if self.fd:
            self.fd.close()

    @property
    def complete(self):
        return len(self.have_pieces) == self.total_pieces

    @property
    def bytes_downloaded(self) -> int:
        return len(self.have_pieces) * self.torrent.piece_length

    @property
    def bytes_uploaded(self) -> int:
        return 0

    def add_peer(self, peer_id, bitfield):
        self.peers[peer_id] = bitfield

    def update_peer(self, peer_id, index: int):
        if peer_id in self.peers:
            self.peers[peer_id][index] = 1

    def remove_peer(self, peer_id):
        if peer_id in self.peers:
            del self.peers[peer_id]

    def next_request(self, peer_id) -> Block:
        if peer_id not in self.peers:
            return None

        block = self._expired_requests(peer_id)
        if not block:
            block = self._next_ongoing(peer_id)
            if not block:
                block = self._get_rarest_piece(peer_id).next_request()
        return block

    def block_received(self, peer_id, piece_index, block_offset, data):
        logging.debug(f'Received block {block_offset} for piece {piece_index} from peer {peer_id}: ')
