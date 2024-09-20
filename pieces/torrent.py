import bencodepy
import os
import re
import hashlib

class Torrent:
    def __init__(self, meta_info, output_path=None):
        self.meta_info = meta_info
        self.torrent_data = meta_info
        self.name = self.torrent_data[b'info'][b'name']
        self.length = self.torrent_data[b'info'].get(b'length', 0)
        self.piece_length = self.torrent_data[b'info'][b'piece length']
        self.pieces = self.torrent_data[b'info'][b'pieces']
        self.files = self.torrent_data[b'info'].get(b'files', None)

        # Extract announce URL
        self.announce = self.torrent_data.get(b'announce', b'').decode()

        # Calculate the info_hash
        self.info_hash = self.calculate_info_hash()  # This should set the info_hash

        self.total_size = self.calculate_total_size() if self.files else self.length
        self.output_file = self.set_output_file(output_path)
        self.downloaded_bytes = 0
        self.pieces_downloaded = 0
    
    def calculate_info_hash(self):
        # Create a hash of the info dictionary
        info_encoded = bencodepy.encode(self.torrent_data[b'info'])
        return hashlib.sha1(info_encoded).digest()
    
    def calculate_total_size(self):
        total_size = 0
        if self.files:
            for file in self.files:
                total_size += file[b'length']
        return total_size

    def set_output_file(self, output_path):
        sanitized_name = self.sanitize_file_name(self.name.decode())
        if output_path:
            if self.files:
                output_dir = os.path.join(output_path, sanitized_name)
                os.makedirs(output_dir, exist_ok=True)
                return output_dir
            else:
                output_file = os.path.join(output_path, sanitized_name)
                return output_file
        else:
            if self.files:
                output_dir = os.path.join(os.getcwd(), sanitized_name)
                os.makedirs(output_dir, exist_ok=True)
                return output_dir
            else:
                output_file = os.path.join(os.getcwd(), sanitized_name)
                return output_file

    def sanitize_file_name(self, file_name):
        return re.sub(r'[<>:"/\\|?*]', '_', file_name).replace(" ", "_")

    def get_file_names(self):
        if self.files:
            return [file[b'path'][-1] for file in self.files]
        return [self.name]

    def get_pieces(self):
        return self.pieces

    def get_piece_count(self):
        return len(self.pieces) // 20

    def get_remaining_pieces(self):
        return self.get_piece_count() - self.pieces_downloaded

    def get_downloaded_bytes(self):
        return self.downloaded_bytes

    def update_downloaded_bytes(self, bytes_downloaded):
        self.downloaded_bytes = bytes_downloaded

    def update_downloaded_pieces(self, pieces_downloaded):
        self.pieces_downloaded = pieces_downloaded

    def __str__(self):
        return (f'Torrent Name: {self.name.decode()}\n'
                f'Total Size: {self.total_size}\n'
                f'Piece Length: {self.piece_length}\n'
                f'Number of Pieces: {self.get_piece_count()}\n'
                f'Output File/Directory: {self.output_file}\n'
                f'Announce URL: {self.announce}')  # Added for clarity

def load_torrent_file(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f'Torrent file not found: {file_path}')

    with open(file_path, 'rb') as f:
        torrent_data = bencodepy.decode(f.read())

    return Torrent(torrent_data)
