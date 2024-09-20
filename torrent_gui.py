import tkinter as tk
from tkinter import ttk
from pieces.client import TorrentClient
import asyncio
import threading
from pieces.torrent import load_torrent_file
import sys

class TorrentGUI:
    def __init__(self, root, torrent):
        self.root = root
        self.root.title("Torrent Client")

        # Initialize the TorrentClient with the loaded torrent
        self.client = TorrentClient(torrent)

        # Download progress label and bar
        self.progress_label = tk.Label(root, text="Download Progress:")
        self.progress_label.pack(pady=5)

        self.progress_bar = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate")
        self.progress_bar.pack(pady=5)

        # Control buttons
        self.start_button = tk.Button(root, text="Start Download", command=self.start_download)
        self.start_button.pack(pady=10)

        self.pause_button = tk.Button(root, text="Pause", command=self.pause_download)
        self.pause_button.pack(pady=5)

        self.stop_button = tk.Button(root, text="Stop", command=self.stop_download)
        self.stop_button.pack(pady=5)

        # Speed label
        self.speed_label = tk.Label(root, text="Download Speed: 0 kB/s")
        self.speed_label.pack(pady=5)

        self.update_progress()

    def start_download(self):
        # Start the download in a separate thread
        self.client_task = threading.Thread(target=self._run_client)
        self.client_task.start()

    def _run_client(self):
        asyncio.run(self.client.start())

    def pause_download(self):
        # Implement actual pause functionality
        if self.client.is_running:
            self.client.pause()
            self.pause_button.config(text="Resume", command=self.resume_download)
        else:
            self.resume_download()

    def resume_download(self):
        self.client.resume()
        self.pause_button.config(text="Pause", command=self.pause_download)

    def stop_download(self):
        self.client.stop()

    def update_progress(self):
        # Update progress bar and download speed
        if self.client.piece_manager:
            downloaded_bytes = self.client.piece_manager.bytes_downloaded
            total_size = self.client.piece_manager.torrent.total_size

            if total_size > 0:
                progress = (downloaded_bytes / total_size) * 100
                self.progress_bar["value"] = progress

            self.speed_label.config(text=f"Download Speed: {self.get_download_speed()} kB/s")
        
        self.root.after(1000, self.update_progress)

    def get_download_speed(self):
        # Implement actual speed calculation based on your logic
        # Placeholder for now
        return 0

if __name__ == "__main__":
    root = tk.Tk()

    # Load the torrent file
    torrent = load_torrent_file('docs/test.torrent')  # Ensure this returns a valid torrent object

    # Check if the torrent was loaded successfully
    if torrent is None:
        print("Error: Failed to load the torrent file.")
        sys.exit(1)

    # Initialize the TorrentGUI with the loaded torrent
    app = TorrentGUI(root, torrent)

    # Start the GUI event loop
    root.mainloop()
