import json
import httpx
import uvicorn
import re
import sys
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

VLLM_INTERNAL_URL = "http://localhost:8000/v1/chat/completions"
VLLM_MODEL_NAME = "/models/Qwen3-Next-80B-A3B-Instruct-NVFP4"

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        req_data = await request.json()
        # 打印最后一条用户消息，确认请求内容
        last_msg = req_data['messages'][-1]['content']
        if isinstance(last_msg, list): last_msg = str(last_msg[0])
        print(f"\n用户提问: {last_msg[:50]}...")
    except Exception as e:
        print(f"❌ 请求解析失败: {e}")
        return StreamingResponse(iter(["data: {\"error\": \"Invalid Request\"}\n\n"]), media_type="text/event-stream")

    # 参数清理
    req_data["model"] = VLLM_MODEL_NAME
    req_data["stream"] = True
    req_data.pop("strict", None); req_data.pop("store", None); req_data.pop("metadata", None)

    async def event_generator():
        print(f"📡 [Proxy] 正在连接 vLLM ({VLLM_INTERNAL_URL})...")
        is_tool_mode = False
        tool_buffer = ""
        
        # 调高超时时间，因为 Blackwell 加载长 context 可能需要时间
        timeout = httpx.Timeout(600.0, connect=60.0)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                async with client.stream("POST", VLLM_INTERNAL_URL, json=req_data) as response:
                    print(f"📥 [Proxy] vLLM 响应状态码: {response.status_code}")
                    
                    if response.status_code != 200:
                        body = await response.aread()
                        print(f"❌ [vLLM Error] {body.decode()}")
                        yield f"data: {json.dumps({'error': 'vLLM Error', 'details': body.decode()})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        # 只要有数据进来就打个点，确认流没断
                        # sys.stdout.write("."); sys.stdout.flush() 
                        
                        if not line: continue
                        if not line.startswith("data: "): 
                            print(f"\n⚠️ [非标准行]: {line}")
                            continue
                            
                        if "[DONE]" in line:
                            print("\n✅ [Proxy] 流传输完成 ([DONE])")
                            yield f"{line}\n\n"
                            break

                        try:
                            chunk = json.loads(line[6:])
                            if not chunk.get('choices'):
                                yield f"{line}\n\n"
                                continue
                            
                            delta = chunk['choices'][0].get('delta', {})
                            content = delta.get('content', '')

                            if content:
                                # 只要有文字，一定要打印出来！
                                print(f"🔍 [RAW]: {repr(content)}")
                                
                                # 工具拦截逻辑
                                if "<tool_call>" in content or (not is_tool_mode and "<tool" in content):
                                    status_delta = {"choices": [{"delta": {"content": "\n> 🛠️ **正在调度工具...**\n"}}]}
                                    yield f"data: {json.dumps(status_delta)}\n\n"
                                    is_tool_mode = True

                                if is_tool_mode:
                                    tool_buffer += content
                                    if "</tool_call>" in tool_buffer:
                                        match = re.search(r"<tool_call>(.*?)</tool_call>", tool_buffer, re.DOTALL)
                                        if match:
                                            try:
                                                raw_json = match.group(1).strip().replace("'", '"')
                                                tool_json = json.loads(raw_json)
                                                tool_chunk = {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": f"call_{chunk.get('id', 'idx')[-6:]}", "type": "function", "function": {"name": tool_json.get("name"), "arguments": json.dumps(tool_json.get("arguments"))}}]}}]}
                                                yield f"data: {json.dumps(tool_chunk)}\n\n"
                                                print(f"🎯 [Proxy] 工具 {tool_json.get('name')} 调度成功")
                                            except: pass
                                        is_tool_mode = False
                                        tool_buffer = ""
                                    continue
                                else:
                                    yield f"{line}\n\n"
                        except Exception as e:
                            print(f"\n🔥 Chunk 解析异常: {e}")
                            yield f"{line}\n\n"
            except Exception as e:
                print(f"\n💥 无法连接到 vLLM: {e}")
                yield f"data: {json.dumps({'error': 'Connection Refused'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=4000)