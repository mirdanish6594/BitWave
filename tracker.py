# tracker.py
# Contains the Tracker class for communicating with the torrent tracker.

import asyncio
import socket
import struct
import urllib.parse
import logging
from typing import List, Tuple, Any, Dict

import aiohttp
from torrent import Torrent
from bencode import bdecode

class TrackerResponse:
    """A container for the parsed response from the tracker."""
    def __init__(self, response: Dict):
        self.peers: List[Tuple[str, int]] = []
        # Default re-announce interval is 30 minutes, but the tracker can override.
        self.interval: int = 1800 

        if b'failure reason' in response:
            logging.error(f"Tracker error: {response[b'failure reason'].decode()}")
            return

        self.interval = response.get(b'interval', 1800)
        peers_data = response.get(b'peers')
        if peers_data:
            self._parse_peers(peers_data)

    def _parse_peers(self, peers_data: Any):
        """
        Parses the peer list, handling both compact and dictionary formats.
        """
        if isinstance(peers_data, bytes):
            logging.info("Parsing compact (binary) peer list.")
            for i in range(0, len(peers_data), 6):
                ip_bytes = peers_data[i:i+4]
                port_bytes = peers_data[i+4:i+6]
                try:
                    ip = socket.inet_ntoa(ip_bytes)
                    port = struct.unpack('!H', port_bytes)[0]
                    self.peers.append((ip, port))
                except Exception:
                    logging.warning(f"Failed to parse peer data chunk.")
        elif isinstance(peers_data, list):
            logging.info("Parsing dictionary model peer list.")
            for peer_dict in peers_data:
                ip = peer_dict[b'ip'].decode('utf-8')
                port = peer_dict[b'port']
                self.peers.append((ip, port))
        
        logging.info(f"Received {len(self.peers)} peers from tracker.")


class Tracker:
    """
    Communicates with the torrent tracker to get a list of peers.
    """
    def __init__(self, torrent: Torrent):
        self.torrent = torrent

    async def get_peers(self) -> TrackerResponse:
        """
        Sends an HTTPS/HTTP request to the tracker and returns a TrackerResponse.
        """
        params = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.torrent.peer_id,
            'port': 6881,
            'uploaded': 0,
            'downloaded': 0,
            'left': self.torrent.file_length,
            'compact': 1
        }
        
        url = self.torrent.announce + '?' + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        
        logging.info(f"Contacting tracker at: {self.torrent.announce}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        logging.error(f"Tracker responded with status: {response.status}")
                        return TrackerResponse({}) # Return empty response
                    
                    body = await response.read()
                    tracker_response_dict, _ = bdecode(body)
                    return TrackerResponse(tracker_response_dict)

        except Exception as e:
            logging.error(f"An unexpected error occurred with the tracker: {e}", exc_info=True)
            return TrackerResponse({}) # Return empty response
