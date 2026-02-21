# 本地 LLM 优化改动说明

> 基于 [netease-youdao/LobsterAI](https://github.com/netease-youdao/LobsterAI) fork
> 主要解决：LobsterAI 调用本地大模型（vLLM）时因上下文过长导致系统卡死的问题

---

## 背景

硬件环境：NVIDIA GB10 Grace Blackwell（128GB 统一内存，CPU/GPU 共享）
本地模型：Qwen3-Next-80B-A3B-Instruct-NVFP4（48GB，NVFP4 量化）
服务方式：vLLM Docker 容器 + fix_proxy.py 网关代理

**卡死根因：**
LobsterAI 做网络搜索 + PDF 论文阅读任务时，工具调用结果（`TOOL_RESULT_MAX_CHARS = 120_000`，约 30K tokens）直接塞满 vLLM 的 KV Cache（max-model-len 65536），导致内存溢出、系统 OOM 卡死。

---

## 改动一：vLLM Provider 支持（Settings.tsx / config.ts / claudeSettings.ts / api.ts）

在 UI 中新增 vLLM 作为独立 Provider，与 Ollama 并列。

### 关键变更
- `src/renderer/components/Settings.tsx`：新增 vLLM provider 选项、图标、默认 baseUrl（`http://localhost:8000`）
- `src/renderer/config.ts`：AppConfig 类型中增加 vLLM provider 配置字段
- `src/main/libs/claudeSettings.ts`：vLLM 与 Ollama 同等处理，不强制要求 API Key
- `src/renderer/services/api.ts`：provider 检测逻辑加入 `vllm`

### 后续待做
- [ ] 在 Settings UI 里暴露 `TOOL_RESULT_MAX_CHARS` 和 `AUTO_COMPRESS_TOOL_RESULT_THRESHOLD` 两个参数，让用户按模型调整（已探索好数据流，下次继续实现）

---

## 改动二：工具结果大小限制（coworkRunner.ts）

**文件：** `src/main/libs/coworkRunner.ts`

```typescript
// 修改前
const TOOL_RESULT_MAX_CHARS = 120_000;  // ≈ 30K tokens

// 修改后
const TOOL_RESULT_MAX_CHARS = 30_000;   // ≈ 7.5K tokens
```

**效果：** 单次工具调用（读 PDF、curl 网页）最多返回 30K chars（约 7500 token），足够读完论文摘要 + 引言 + 结论，但不会把整篇 PDF 塞进上下文。

---

## 改动三：自动上下文压缩（coworkRunner.ts）

**文件：** `src/main/libs/coworkRunner.ts`

### 原理
当本地 LLM 会话中工具结果累积量超过阈值时，自动：
1. 从历史消息中提取「用户消息」+「助手回复」（跳过工具结果）
2. 清空 `claudeSessionId`（强制 SDK 开新对话，vLLM KV Cache 真正释放）
3. 把精简摘要 + 用户新消息一起发给模型
4. UI 显示 ♻️ 提示

### 新增常量
```typescript
const AUTO_COMPRESS_TOOL_RESULT_THRESHOLD = 80_000; // ≈ 20K tokens，约读了 2-3 篇论文后触发
```

### 新增字段
```typescript
private sessionToolResultChars: Map<string, number> = new Map();
```

### 新增方法
```typescript
private buildCompressedContext(sessionId: string): string
// 提取会话历史中的用户消息 + 助手回复，生成精简摘要
// 用户消息保留前 600 chars，助手回复保留前 1200 chars
// 完全跳过 tool_use / tool_result（这正是占用大量 KV Cache 的部分）
```

### 触发位置
```typescript
// continueSession() 中，调用 runClaudeCode() 之前
if (accumulatedToolResultChars >= AUTO_COMPRESS_TOOL_RESULT_THRESHOLD) {
  // 1. 构建摘要
  // 2. 重置 claudeSessionId → SDK 新建对话
  // 3. effectivePrompt = 摘要 + 用户新请求
  // 4. 计数清零
}
```

---

## 改动四：vLLM 启动脚本（scripts/start_vllm.sh）

针对 GB10 统一内存架构优化的 vLLM Docker 启动命令。

### 关键参数对比

| 参数 | 原来 | 优化后 | 原因 |
|------|------|--------|------|
| `--max-model-len` | 65536 | 65536 | 保持不变，维持长对话连贯性 |
| `--gpu-memory-utilization` | 0.85 | **0.75** | GB10 统一内存，留 ~30GB 给 OS |
| `--max-num-seqs` | 无 | **4** | 限制并发序列，防叠加 KV Cache |
| `--enable-prefix-caching` | 无 | **开启** | 相同前缀（系统提示等）复用 KV Cache |

### 使用
```bash
bash scripts/start_vllm.sh
```

---

## 下次继续的工作

### 优先级高：UI 参数化（已探索完架构，可直接实现）

目标：在 Settings 的 cowork 配置页面（`activeTab === 'coworkSandbox'` 或新建 tab）里暴露以下参数：

| 参数 | 当前硬编码值 | 建议范围 |
|------|-------------|---------|
| 工具结果最大字符数 `TOOL_RESULT_MAX_CHARS` | 30,000 | 10,000 ~ 120,000 |
| 自动压缩阈值 `AUTO_COMPRESS_TOOL_RESULT_THRESHOLD` | 80,000 | 40,000 ~ 200,000 |

**数据流已确认：**
1. `CoworkConfig` 类型（`src/main/coworkStore.ts`）加两个数字字段
2. IPC handler `cowork:config:set`（`src/main/main.ts`）加验证
3. Redux slice `coworkSlice.ts` 加字段
4. `coworkRunner.ts` 从 `store.getConfig()` 读取替换硬编码常量
5. `Settings.tsx` 在 coworkSandbox tab 里加两个数字输入框

### 优先级中：buildCompressedContext 质量改进
- 当前摘要是简单拼接，可以让模型生成结构化摘要（需要额外一次 API 调用）
- 可在压缩触发时先调用本地模型生成 500 字总结，再重置会话

### 优先级低：前缀缓存验证
- 验证 `--enable-prefix-caching` 对 NVFP4 量化模型是否有效
- 如无效需移除该参数
