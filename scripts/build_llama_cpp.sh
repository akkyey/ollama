#!/bin/bash
set -e

echo "--- Setting up llama.cpp directories ---"
sudo mkdir -p /opt/llama.cpp
sudo chown -R $USER:$USER /opt/llama.cpp

echo "--- Cloning llama.cpp ---"
cd /opt/llama.cpp
if [ ! -d ".git" ]; then
  git clone https://github.com/ggerganov/llama.cpp .
fi

echo "--- Building llama.cpp with native optimizations ---"
cmake -B build -DGGML_NATIVE=ON
cmake --build build --config Release -j 6

echo "--- Setting up models directory ---"
sudo mkdir -p /mnt/data/llama-models
sudo chown -R $USER:$USER /mnt/data/llama-models

echo "Build and setup complete!"
