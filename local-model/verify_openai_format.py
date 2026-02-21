import openai
import json

# 指向 LiteLLM 代理端口
client = openai.OpenAI(
    base_url="http://127.0.0.1:4000/v1",
    api_key="sk-any-key-is-fine"
)

def test_tool_format():
    print("🔍 正在测试工具调用格式标准化...")
    
    # 定义测试工具
    tools = [{
        "type": "function",
        "function": {
            "name": "calculate_sum",
            "description": "计算两个数字的和",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"}
                },
                "required": ["a", "b"]
            }
        }
    }]

    try:
        response = client.chat.completions.create(
            model="qwen3-coder",
            messages=[{"role": "user", "content": "请使用 calculate_sum 工具计算 12345 加 67890"}],
            tools=tools,
            tool_choice="auto"
        )

        # 核心验证逻辑
        message = response.choices[0].message
        
        print("-" * 30)
        if message.tool_calls:
            print("✅ 格式正确！检测到标准 OpenAI Tool Calls:")
            for i, tool_call in enumerate(message.tool_calls):
                print(f"  工具 [{i}]: {tool_call.function.name}")
                print(f"  参数: {tool_call.function.arguments}")
                
            # 打印原始 JSON 结构供你确认
            print("\n[原始响应数据结构]:")
            print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))
        else:
            print("❌ 格式错误: 未检测到 tool_calls 字段。")
            print(f"模型实际返回内容: {message.content}")
        print("-" * 30)

    except Exception as e:
        print(f"⚠️ 请求失败: {str(e)}")

if __name__ == "__main__":
    test_tool_format()
