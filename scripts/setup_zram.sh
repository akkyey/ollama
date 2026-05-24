#!/bin/bash
set -e

echo "--- Setting up zRAM (16GB) ---"
sudo modprobe zram
sudo zramctl --reset /dev/zram0 || true
sudo zramctl --find --size 16G --algorithm zstd
sudo mkswap /dev/zram0
sudo swapon /dev/zram0 -p 32767

echo "zRAM configured successfully."
zramctl
