#!/bin/bash
sudo systemctl start ollama
sleep 2
ollama create qwen-coder-32b -f Modelfile.qwen
ollama run qwen-coder-32b "Hello" &
sleep 5
ollama ps
kill %1
