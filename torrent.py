# torrent.py
# Contains the Torrent class for parsing .torrent files.

import hashlib
import random
import string
import logging
from typing import List, Optional
from bencode import bdecode, bencode

class Torrent:
    """
    Parses a .torrent file and stores its metadata.
    """
    def __init__(self, torrent_file_path: str):
        with open(torrent_file_path, 'rb') as f:
            meta_info_bytes = f.read()
        
        self.meta_info, _ = bdecode(meta_info_bytes)
        info = self.meta_info[b'info']
        
        self.info_hash = hashlib.sha1(bencode(info)).digest()
        
        # This will now be None if no tracker is found
        self.announce = self._get_tracker_url()
        
        self.file_name = info[b'name'].decode('utf-8')
        # Handle torrents with single vs multiple files (though we only download the first)
        if b'length' in info:
            self.file_length = info[b'length']
        else:
            # For multi-file torrents, calculate total size. Our client
            # will still download it as a single file in a folder.
            self.file_length = sum(file[b'length'] for file in info[b'files'])

        self.piece_length = info[b'piece length']
        self.pieces_hashes = self._split_piece_hashes(info[b'pieces'])
        self.num_pieces = len(self.pieces_hashes)

        self.peer_id = '-BW0001-' + ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        
        logging.info(f"--- Torrent Info ---")
        logging.info(f"File Name: {self.file_name}")
        if self.announce:
            logging.info(f"Tracker URL: {self.announce}")
        else:
            logging.warning("This is a trackerless torrent (uses DHT). BitWave does not support this.")
        logging.info(f"Total Size: {self.file_length / 1024 / 1024:.2f} MB")
        logging.info(f"Number of Pieces: {self.num_pieces}")
        logging.info(f"--------------------")

    def _get_tracker_url(self) -> Optional[str]:
        """
        Gets the tracker URL. Returns None if no tracker is found.
        """
        if b'announce-list' in self.meta_info:
            first_tier = self.meta_info[b'announce-list'][0]
            if first_tier:
                return first_tier[0].decode('utf-8')
        
        if b'announce' in self.meta_info:
            return self.meta_info[b'announce'].decode('utf-8')
            
        return None # Return None for trackerless torrents

    def _split_piece_hashes(self, hashes: bytes) -> List[bytes]:
        """Splits the concatenated SHA1 hashes into a list of 20-byte hashes."""
        return [hashes[i:i + 20] for i in range(0, len(hashes), 20)]
