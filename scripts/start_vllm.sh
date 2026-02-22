#!/bin/bash
# vLLM 启动脚本 - GB10 统一内存优化版
#
# 关键参数说明：
#   --max-model-len 65536        上下文窗口 65K token（保持原值，确保长对话连贯性）
#   --gpu-memory-utilization 0.75 占用 75% 统一内存（原 0.85），GB10 CPU/GPU 共享内存池，
#                                 留出 ~30GB 给 OS/UI/其他进程，避免 OOM 卡死
#   --max-num-batched-tokens 32768 单次前向传播最大 token 数
#   --max-num-seqs 4             同时处理的最大序列数，防止并发请求叠加 KV Cache 溢出
#
# 系统卡死根因已在 LobsterAI 侧修复：TOOL_RESULT_MAX_CHARS 120K→30K chars
# （PDF/网页全文单次返回量从 30K tokens 降到 7.5K tokens）

set -e

MODEL_PATH="/models/Qwen3-Next-80B-A3B-Instruct-NVFP4"
IMAGE="nvcr.io/nvidia/vllm:26.01-py3"
CONTAINER_NAME="vllm_nvfp4_server"

echo "停止旧容器..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "启动 vLLM 服务..."
docker run -d \
  --gpus all \
  --ipc=host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  --name "$CONTAINER_NAME" \
  -p 8000:8000 \
  -v /home/dannis/models:/models \
  "$IMAGE" \
  python3 -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --quantization nvfp4 \
    --tensor-parallel-size 1 \
    --max-model-len 65536 \
    --max-num-batched-tokens 32768 \
    --max-num-seqs 4 \
    --gpu-memory-utilization 0.75 \
    --dtype bfloat16 \
    --kv-cache-dtype fp8 \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    --chat-template-content-format auto \
    --enable-prefix-caching \
    --trust-remote-code

echo "等待服务就绪..."
for i in $(seq 1 60); do
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ vLLM 服务已就绪"
    break
  fi
  sleep 5
  echo "  等待中... ($((i*5))s)"
done

echo "查看日志：docker logs -f $CONTAINER_NAME"
