import requests
import json

OPENAI_API_KEY = "sk-rgijapfapkddnnbbwftgcqycdniodxuxqibiwrtfnthxdaqw"
OPENAI_BASE_URL = "https://api.siliconflow.cn/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [
        {"role": "user", "content": "你好，你是谁？"}
    ],
    "max_tokens": 50
}

try:
    response = requests.post(OPENAI_BASE_URL, headers=headers, json=payload)
    response_json = response.json()
    print("Success:", response_json["choices"][0]["message"]["content"])
except Exception as e:
    print("Error:", e)

