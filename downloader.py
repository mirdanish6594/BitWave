# downloader.py
# Converted to use eventlet for cooperative multitasking instead of asyncio.

import hashlib
import logging
import os
import time
import random
from typing import List, Tuple, Set

import eventlet
from eventlet.green import socket
from eventlet.queue import Queue

from torrent import Torrent
from tracker import Tracker
from peer_protocol import PeerProtocol

class PieceManager:
    BLOCK_SIZE = 2**14

    def __init__(self, torrent: Torrent, socketio):
        self.torrent = torrent
        self.socketio = socketio
        self.pieces = [bytearray(self._get_piece_size(i)) for i in range(torrent.num_pieces)]
        self.bitfield = bytearray(-(-torrent.num_pieces // 8))
        self.requested_blocks: Set[Tuple[int, int]] = set()
        self.downloaded_blocks: Set[Tuple[int, int]] = set()
        self.downloaded_pieces_count = 0
        self.file_handle = open(os.path.join(os.getenv('RENDER_DISK_MOUNT_PATH', 'storage'), 'downloads', self.torrent.file_name), "wb")
        self.lock = eventlet.semaphore.Semaphore()
        self.bytes_downloaded_since_last_check = 0
        self.piece_availability = [0] * self.torrent.num_pieces
        self.endgame_mode = False

    def _get_piece_size(self, piece_index: int) -> int:
        if piece_index < self.torrent.num_pieces - 1:
            return self.torrent.piece_length
        return self.torrent.file_length % self.torrent.piece_length or self.torrent.piece_length
    
    def update_piece_availability(self, active_peers: List[PeerProtocol]):
        self.piece_availability = [0] * self.torrent.num_pieces
        for peer in active_peers:
            for piece_index in range(self.torrent.num_pieces):
                if peer.has_piece(piece_index):
                    self.piece_availability[piece_index] += 1

    def get_next_block_to_request(self, peer: PeerProtocol) -> Tuple[int, int, int] | None:
        with self.lock:
            if self.endgame_mode:
                missing_pieces = [i for i in range(self.torrent.num_pieces) if not self.we_have_piece(i) and peer.has_piece(i)]
                if not missing_pieces: return None
                random.shuffle(missing_pieces)
                for piece_index in missing_pieces:
                    piece_size = self._get_piece_size(piece_index)
                    for block_offset in range(0, piece_size, self.BLOCK_SIZE):
                        block_id = (piece_index, block_offset)
                        if block_id not in self.downloaded_blocks:
                            block_size = min(self.BLOCK_SIZE, piece_size - block_offset)
                            return piece_index, block_offset, block_size
                return None

            available_pieces = []
            for piece_index in range(self.torrent.num_pieces):
                if peer.has_piece(piece_index) and not self.we_have_piece(piece_index):
                    availability = self.piece_availability[piece_index]
                    available_pieces.append((availability, piece_index))
            available_pieces.sort()
            for _, piece_index in available_pieces:
                piece_size = self._get_piece_size(piece_index)
                for block_offset in range(0, piece_size, self.BLOCK_SIZE):
                    block_id = (piece_index, block_offset)
                    if block_id not in self.requested_blocks and block_id not in self.downloaded_blocks:
                        block_size = min(self.BLOCK_SIZE, piece_size - block_offset)
                        self.requested_blocks.add(block_id)
                        return piece_index, block_offset, block_size
        return None

    def block_received(self, index: int, begin: int, block: bytes, peer: PeerProtocol, all_peers: List[PeerProtocol]):
        with self.lock:
            block_id = (index, begin)
            if block_id in self.downloaded_blocks: return
            
            self.pieces[index][begin:begin + len(block)] = block
            self.downloaded_blocks.add(block_id)
            self.bytes_downloaded_since_last_check += len(block)
            if block_id in self.requested_blocks: self.requested_blocks.remove(block_id)

            if self.endgame_mode:
                for other_peer in all_peers:
                    if other_peer is not peer:
                        other_peer.send_cancel(index, begin, len(block))

            piece_size = self._get_piece_size(index)
            num_blocks_in_piece = -(-piece_size // self.BLOCK_SIZE)
            num_downloaded_blocks = sum(1 for (p_idx, _) in self.downloaded_blocks if p_idx == index)

            if num_downloaded_blocks == num_blocks_in_piece:
                self._piece_completed(index)

    def _piece_completed(self, index: int):
        piece_data = self.pieces[index]
        if hashlib.sha1(piece_data).digest() == self.torrent.pieces_hashes[index]:
            self.file_handle.seek(index * self.torrent.piece_length)
            self.file_handle.write(piece_data)
            byte_index, bit_index = divmod(index, 8)
            self.bitfield[byte_index] |= (1 << (7 - bit_index))
            self.downloaded_pieces_count += 1
        else:
            logging.warning(f"Piece {index} hash check failed. Re-downloading.")
            for block_offset in range(0, len(piece_data), self.BLOCK_SIZE):
                block_id = (index, block_offset)
                if block_id in self.downloaded_blocks: self.downloaded_blocks.remove(block_id)
                if block_id in self.requested_blocks: self.requested_blocks.remove(block_id)

    def is_complete(self) -> bool:
        return self.downloaded_pieces_count == self.torrent.num_pieces

    def close_file(self):
        self.file_handle.close()

class Downloader:
    MAX_PEERS = 50

    def __init__(self, torrent_file_path: str, socketio):
        self.torrent = Torrent(torrent_file_path)
        self.tracker = Tracker(self.torrent)
        self.piece_manager = PieceManager(self.torrent, socketio)
        self.active_peers: List[PeerProtocol] = []
        self.socketio = socketio
        self.info_hash_hex = self.torrent.info_hash.hex()
        self.message_queue = Queue()
        self.pool = eventlet.GreenPool()

    def start(self):
        if not self.torrent.announce:
            self.emit_final_status("Error: Trackerless torrent not supported")
            return

        self.pool.spawn(self.message_consumer)
        self.pool.spawn(self.status_updater)
        self.pool.spawn(self.peer_optimizer)
        self.pool.spawn(self.tracker_announcer)
        
        self.pool.waitall()
        
        self.emit_final_status("Completed" if self.piece_manager.is_complete() else "Finished with errors")
        self.piece_manager.close_file()

    def tracker_announcer(self):
        while not self.piece_manager.is_complete():
            try:
                tracker_response = self.tracker.get_peers()
                
                current_peer_ips = {p.ip for p in self.active_peers}
                for ip, port in tracker_response.peers:
                    if len(self.active_peers) < self.MAX_PEERS and ip not in current_peer_ips:
                        peer = PeerProtocol(ip, port, self, self.message_queue)
                        self.pool.spawn(self._manage_peer, peer)
                
                eventlet.sleep(tracker_response.interval)
            except Exception as e:
                logging.error(f"Error in announcer: {e}. Retrying in 60s.")
                eventlet.sleep(60)

    def message_consumer(self):
        while not self.piece_manager.is_complete():
            try:
                peer, msg_id, payload = self.message_queue.get()
                if msg_id == 7:
                    index, begin, block = peer._parse_piece_message(payload)
                    request_tuple = next((r for r in peer.outstanding_requests if r[0] == index and r[1] == begin), None)
                    if request_tuple: peer.outstanding_requests.discard(request_tuple)
                    self.piece_manager.block_received(index, begin, block, peer, self.active_peers)
                    peer._fill_request_pipeline()
            except Exception as e:
                logging.error(f"Error in message consumer: {e}")

    def peer_optimizer(self):
        while not self.piece_manager.is_complete():
            eventlet.sleep(10)
            if not self.active_peers: continue

            now = time.time()
            with self.piece_manager.lock:
                for peer in self.active_peers:
                    stale_requests = {req for req in peer.outstanding_requests if now - req[3] > 30}
                    for index, begin, length, _ in stale_requests:
                        logging.warning(f"Stale request for piece {index} block {begin} from {peer.ip}. Re-requesting.")
                        self.piece_manager.requested_blocks.discard((index, begin))
                    peer.outstanding_requests -= stale_requests

            self.active_peers.sort(key=lambda p: p.download_rate, reverse=True)
            unchoked_peers = set()
            for i, peer in enumerate(self.active_peers):
                if i < 4:
                    if peer.am_choking: peer.send_unchoke()
                    unchoked_peers.add(peer)
            
            choked_interested_peers = [p for p in self.active_peers if p.am_choking and p.peer_interested]
            if choked_interested_peers:
                optimistic_peer = random.choice(choked_interested_peers)
                if optimistic_peer.am_choking: optimistic_peer.send_unchoke()
                unchoked_peers.add(optimistic_peer)

            for peer in self.active_peers:
                if peer not in unchoked_peers and not peer.am_choking:
                    peer.send_choke()

    def status_updater(self):
        while not self.piece_manager.is_complete():
            eventlet.sleep(1)
            self.piece_manager.update_piece_availability(self.active_peers)
            
            if not self.piece_manager.endgame_mode:
                if self.piece_manager.downloaded_pieces_count > self.torrent.num_pieces * 0.95:
                    logging.info("--- ENTERING ENDGAME MODE ---")
                    self.piece_manager.endgame_mode = True

            with self.piece_manager.lock:
                bytes_downloaded = self.piece_manager.bytes_downloaded_since_last_check
                self.piece_manager.bytes_downloaded_since_last_check = 0
            
            speed = bytes_downloaded / 1024
            progress = (self.piece_manager.downloaded_pieces_count / self.torrent.num_pieces) * 100
            status = {
                'info_hash': self.info_hash_hex, 'file_name': self.torrent.file_name,
                'progress': f"{progress:.2f}", 'peers': len(self.active_peers), 'speed': f"{speed:.2f}"
            }
            self.socketio.emit('status_update', status)

    def emit_final_status(self, final_status: str):
        progress = 100.00 if final_status == "Completed" else (self.piece_manager.downloaded_pieces_count / self.torrent.num_pieces * 100)
        status = {
            'info_hash': self.info_hash_hex, 'file_name': self.torrent.file_name,
            'progress': f"{progress:.2f}", 'peers': 0, 'speed': "0.00", 'final_status': final_status
        }
        self.socketio.emit('status_update', status)

    def _manage_peer(self, peer: PeerProtocol):
        try:
            if peer.connect():
                self.active_peers.append(peer)
                peer.start_communication_loop()
        except Exception as e:
            logging.error(f"Error managing peer {peer.ip}: {e}")
        finally:
            if peer in self.active_peers:
                self.active_peers.remove(peer)

    def peer_disconnected(self, peer: PeerProtocol):
        with self.piece_manager.lock:
            for index, begin, _, _ in peer.outstanding_requests:
                self.piece_manager.requested_blocks.discard((index, begin))
