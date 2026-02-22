# 本地模型启动配置

本目录包含在 GB10 Grace Blackwell 上运行 Qwen3-Next-80B-A3B-Instruct-NVFP4 的完整配置。

## 架构

```
LobsterAI (Electron)
    │  OpenAI 兼容格式（直连）
    ▼
vLLM Docker (port 8000)
    │
    ▼
Qwen3-Next-80B-A3B-Instruct-NVFP4  (/models/)
```

工具调用格式已通过 vLLM 启动参数 `--tool-call-parser hermes` 原生解决，无需额外代理。

## 快速启动

### 步骤 1：启动 vLLM

```bash
bash ../scripts/start_vllm.sh
```

关键参数（见 `../scripts/start_vllm.sh`）：

| 参数 | 值 | 说明 |
|------|----|------|
| `--max-model-len` | 65536 | 65K token 上下文，保证长对话连贯 |
| `--gpu-memory-utilization` | 0.75 | GB10 统一内存留 ~30GB 给 OS |
| `--max-num-seqs` | 4 | 限制并发，防 KV Cache 叠加溢出 |
| `--tool-call-parser` | hermes | 原生 OpenAI 兼容工具调用格式 |
| `--enable-prefix-caching` | 开启 | 相同前缀复用 KV Cache |

等待日志出现 `Application startup complete` 后继续。

### 步骤 2：配置 LobsterAI

Settings → Model → 选择 **vLLM** provider：
- Base URL：`http://localhost:8000`
- API Key：留空
- Model：`/models/Qwen3-Next-80B-A3B-Instruct-NVFP4`

### 步骤 3：启动 LobsterAI

```bash
npm run electron:dev
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `../scripts/start_vllm.sh` | vLLM Docker 启动脚本（优化参数） |

## 内存估算（GB10, 128GB 统一内存）

| 项目 | 占用 |
|------|------|
| 模型权重（NVFP4）| ~48 GB |
| KV Cache（75% × 128GB - 48GB）| ~48 GB |
| OS + LobsterAI + 其他 | ~32 GB |
| **合计** | ~128 GB ✅ |
