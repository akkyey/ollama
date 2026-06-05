#!/bin/bash
MODEL="/mnt/data/llama-models/Qwen3.6-27B-MTP-Q4_K_M.gguf"
BENCH="/opt/llama.cpp/build/bin/llama-bench"

echo "=== BENCHMARK: WITHOUT -t 6 (Default SMT) ==="
numactl --physcpubind=0-5 "$BENCH" -m "$MODEL" -p 512 -n 128 -ngl 20 -fa 1 -ctk q8_0 -ctv q8_0

echo ""
echo "=== BENCHMARK: WITH -t 6 (Physical Core Bind) ==="
numactl --physcpubind=0-5 "$BENCH" -m "$MODEL" -p 512 -n 128 -ngl 20 -fa 1 -ctk q8_0 -ctv q8_0 -t 6
