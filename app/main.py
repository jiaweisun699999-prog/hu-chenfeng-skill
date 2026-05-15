import os
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
import numpy as np

# --- 日志配置开始 ---
import logging
from logging.handlers import RotatingFileHandler
import datetime

log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / "chat.log"

handler = RotatingFileHandler(
    log_file, 
    maxBytes=2 * 1024 * 1024, # 达到 2MB 触发分割存入新文件
    backupCount=1000, 
    encoding="utf-8"
)

def custom_namer(default_name):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return default_name.replace(".log.1", f"_{timestamp}.log")

handler.namer = custom_namer
formatter = logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)

logger = logging.getLogger("chat_logger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(handler)
# --- 日志配置结束 ---

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Index and Model
from fastembed import TextEmbedding
import sys
sys.path.append(str(Path(__file__).parent.parent))
from tools.search import load_index, cosine_similarity

INDEX_PATH = Path(__file__).parent.parent / "tools" / "vector_index.json"
index = load_index(str(INDEX_PATH))
model = TextEmbedding(model_name=index["model"])

SKILL_PATH = Path(__file__).parent.parent / "SKILL.md"
with open(SKILL_PATH, "r", encoding="utf-8") as f:
    skill_content = f.read()

# 引入 dotenv 用于读取 .env 文件中的敏感数据
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Default to local Ollama.
# If you want to use DeepSeek, run the server with:
# OLLAMA_BASE_URL="https://api.deepseek.com/v1" DEEPSEEK_API_KEY="sk-..." python -m uvicorn app.main:app --reload
# 如果使用 DeepSeek 等外部大模型，建议在根目录新建 .env 文件并配置对应 Key。
client = AsyncOpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "https://api.deepseek.com/v1"),
    api_key=os.getenv("DEEPSEEK_API_KEY", "your-api-key-here"), # 默认占位符，安全起见请在 .env 中配置
)

# Replace with your local model name in Ollama, e.g., 'deepseek-r1:1.5b' or 'llama3'
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-pro")

def search_quotes(query: str, top_k: int = 5):
    query_emb = list(model.embed([query]))[0].tolist()
    results = []
    for chunk in index["chunks"]:
        score = cosine_similarity(query_emb, chunk["embedding"])
        results.append({
            "text": chunk["text"],
            "score": score,
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

@app.post("/chat")
async def chat_endpoint(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    data = await request.json()
    messages = data.get("messages", [])
    
    last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    
    # 极速检索相似语录
    quotes = search_quotes(last_user_msg) if last_user_msg else []
    quotes_text = "\n\n".join([f"原文片段 {i+1}:\n{q['text']}" for i, q in enumerate(quotes)])
    
    system_prompt = f"""{skill_content}

===== 检索到的直播语录参考 =====
在回答时，请巧妙地参考以下你在直播中说过的原话（如果相关的话），来保持你的“味道”：

{quotes_text}
================================

【重要指令】：
1. 你的回答必须非常没有耐心，说话生硬、直白、绝对化、口语化，拒绝任何书面语、AI感和套话。
2. 注意查看历史对话上下文！如果用户之前**已经**告诉过你他的个人情况（年龄、学历、城市、收入、手机等），**绝对不要重复询问**，直接基于已知信息开怼或分析。
3. 如果用户在发泄情绪或骂人，直接用强硬的态度骂回去，不要机械地查户口。
4. 只有在用户第一次提问且没提供个人信息时，才需要强制查户口。
"""
    
    # 构建发给LLM的请求
    llm_msgs = [{"role": "system", "content": system_prompt}] + messages
    
    async def event_generator():
        try:
            stream = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=llm_msgs,
                stream=True
            )
            full_response = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"
            
            # --- 记录成功日志 ---
            q = last_user_msg.replace('\n', ' ') if last_user_msg else ''
            a = full_response.replace('\n', ' ')
            logger.disabled = False # 强制唤醒 logger，防止被 uvicorn 默认禁用
            logger.info(f"IP: {client_ip} | Q: {q} | A: {a}")
            
        except Exception as e:
            logger.disabled = False
            logger.error(f"IP: {client_ip} | Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
