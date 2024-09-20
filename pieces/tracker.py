import aiohttp
import asyncio
import bencodepy
import random
import socket
import struct

class Tracker:
    def __init__(self, torrent):
        self.torrent = torrent  # Store the torrent object
        self.url = 'udp://tracker.coppersurfer.tk:6969'
        self.peer_id = self.generate_peer_id()  # Generate peer ID on initialization

    def generate_peer_id(self):
        # Generate a unique peer ID
        return "-PC0001-" + "".join([str(random.randint(0, 9)) for _ in range(12)])

    async def connect(self, uploaded=0, downloaded=0, event=None):
        if self.url.startswith('http'):
            return await self._http_connect(uploaded, downloaded, event)
        elif self.url.startswith('udp'):
            return await self._udp_connect(uploaded, downloaded, event)
        else:
            raise ValueError("Unsupported tracker protocol")

    async def _http_connect(self, uploaded, downloaded, event):
        params = {
            'info_hash': self.torrent.info_hash,  # The info hash from the torrent
            'peer_id': self.peer_id,
            'port': 6881,  # Default port for BitTorrent
            'uploaded': uploaded,
            'downloaded': downloaded,
            'compact': 1,
            'event': event
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(self.url, params=params) as response:
                if response.status == 200:
                    response_data = await response.read()
                    return self.parse_response(response_data)
                else:
                    raise Exception(f"Tracker response error: {response.status}")

    async def _udp_connect(self, uploaded, downloaded, event):
       tracker_address = self.url.split('://')[1]  # Get the address without "udp://"
       host, port = tracker_address.split(':')
       port = port.split('/')[0]

       sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
       sock.settimeout(20)  # Increased timeout

       # Build the UDP connection request
       connection_id = 0x41727101980
       action = 0
       transaction_id = random.randint(0, 0xFFFFFFFF)

       request = struct.pack('!QQI', connection_id, action, transaction_id)
       print(f"Connecting to tracker at {host}:{port}")
       print(f"Sending request to tracker...")
       sock.sendto(request, (host, int(port)))
       print(f"Waiting for response from tracker...")

       try:
           response, _ = sock.recvfrom(4096)
       except socket.timeout:
           raise Exception("UDP Tracker request timed out")

       if len(response) < 16:
           raise Exception("Invalid UDP response")

       action, transaction_id = struct.unpack('!II', response[:8])
       if action != 0:
           raise Exception("UDP tracker error")

       # Send announce request
       action = 1
       request = struct.pack('!QQI20s20sII', connection_id, action, transaction_id,
                             self.torrent.info_hash, self.peer_id.encode(), 6881, 0)

       sock.sendto(request, (host, int(port)))
       try:
           response, _ = sock.recvfrom(4096)
       except socket.timeout:
           raise Exception("UDP Tracker announce request timed out")

       return self.parse_udp_response(response)



    def parse_response(self, response_data):
        decoded = bencodepy.decode(response_data)
        return {
            'interval': decoded.get(b'interval', 30),  # Default interval if not specified
            'peers': self.decode_peers(decoded.get(b'peers', b'')),
        }

    def parse_udp_response(self, response_data):
        print(f"Raw response: {response_data}") 
        if len(response_data) < 20:
            raise Exception("Invalid UDP response")
        action, transaction_id = struct.unpack('!I', response_data[:4])[0]
        if action != 0:  # 0 indicates a successful response
         raise Exception(f"Unexpected action in response: {action}")
        
        peer_list = []
        peer_count = (len(response_data) - 8) // 6
        for i in range(peer_count):
            peer = response_data[8 + i * 6: 8 + (i + 1) * 6]
            ip = peer[:4]
            port = peer[4:]
            peer_list.append((self.bytes_to_ip(ip), self.bytes_to_port(port)))

        return {
            'interval': 30,  # Default interval for UDP response
            'peers': peer_list,
        }

    def decode_peers(self, peers):
        # Assuming compact format for HTTP response
        peer_list = []
        for i in range(0, len(peers), 6):
            ip = peers[i:i + 4]
            port = peers[i + 4:i + 6]
            peer_list.append((self.bytes_to_ip(ip), self.bytes_to_port(port)))
        return peer_list

    def bytes_to_ip(self, byte_ip):
        return ".".join(str(x) for x in byte_ip)

    def bytes_to_port(self, byte_port):
        return int.from_bytes(byte_port, 'big')

    def close(self):
        # Clean up any connections or resources
        pass
