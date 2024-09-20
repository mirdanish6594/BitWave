# Bitwave

Bitwave is a BitTorrent client implemented in Python using `asyncio`. It includes a graphical user interface (GUI) to interact with the client. The core functionality includes parsing `.torrent` files, connecting to peers, and downloading files.

## Project Structure

- `torrent_gui.py`: Main GUI application.
- `pieces/`: Core package with BitTorrent protocol implementations.
- `docs/`: Contains `.torrent` files for testing.
- `tests/`: Unit tests for various components.

## Requirements

- Python 
- `asyncio`
- `tkinter`
- `bencoding`

## Installation

1. Clone the repository.
2. Install the required packages using `pip`:

   ```bash
   pip install -r requirements.txt
