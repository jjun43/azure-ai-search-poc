"""
Azure AI Search PoC — FastAPI 백엔드
SSE 스트리밍 + Function Calling
"""

import os
import json
import asyncio
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

search_client = SearchClient(
    endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
    index_name=os.getenv("AZURE_SEARCH_INDEX_NAME", "azure-ai-foundry-docs"),
    credential=AzureKeyCredential(os.getenv("AZURE_SEARCH_API_KEY")),
)

gh_client = OpenAI(
    base_url=os.getenv("GITHUB_ENDPOINT", "https://api.groq.com/openai/v1"),
    api_key=os.getenv("GITHUB_TOKEN"),
    timeout=60.0,
)
MODEL = os.getenv("GITHUB_MODEL", "openai/gpt-oss-20b")
MIN_DEMO_SECONDS = 15.0
logger = logging.getLogger(__name__)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "search_azure_docs",
        "description": "Search Azure official documentation for relevant information",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}]

SYSTEM_PROMPT = (
    "You are an Azure AI expert assistant. "
    "Use the search tool to find relevant docs, then answer concisely in Korean. "
    "Keep answers under 300 words."
)


def _search_docs_sync(query: str, top: int = 5) -> list[dict]:
    results = search_client.search(query, top=top, select=["id", "title", "url", "content"])
    return [{"title": r["title"], "url": r["url"], "content": r["content"]} for r in results]


async def search_docs(query: str, top: int = 5) -> list[dict]:
    return await asyncio.to_thread(_search_docs_sync, query, top)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class DemoRequest(BaseModel):
    question: str


async def stream_demo(question: str):
    try:
        async for event in _stream_demo(question):
            yield event
    except Exception:
        logger.exception("Demo request failed")
        yield sse("error", {"message": "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})


async def _stream_demo(question: str):
    started_at = asyncio.get_running_loop().time()
    # ── Step 1: Azure AI Search ──────────────────────────────
    yield sse("step", {"step": 1, "status": "active", "msg": "Azure AI Search 검색 중..."})
    initial_docs = await search_docs(question)
    yield sse("step", {"step": 1, "status": "done",
                       "msg": f"관련 문서 {len(initial_docs)}개 발견"})

    # ── Step 2: Function Calling (1차 LLM — tool 쿼리 결정) ──
    yield sse("step", {"step": 2, "status": "active", "msg": "Function Calling 실행 중..."})

    fc_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    def _call_fc():
        return gh_client.chat.completions.create(
            model=MODEL, messages=fc_messages,
            tools=TOOLS, tool_choice="required",
        )

    resp = await asyncio.to_thread(_call_fc)
    assistant_msg = resp.choices[0].message
    sources = []
    yield sse("step", {"step": 2, "status": "done", "msg": "도구 호출 응답 수신"})
    yield sse("step", {"step": "Decision", "status": "active", "msg": "예/아니오 경로 표시 중..."})
    await asyncio.sleep(0.4)

    if assistant_msg.tool_calls:
        tc = assistant_msg.tool_calls[0]
        args = json.loads(tc.function.arguments)
        search_query = args.get("query") or question
        yield sse("branch", {"choice": "yes", "msg": "예 · 문서 재검색"})
        yield sse("step", {"step": 5, "status": "active", "msg": "생성된 쿼리로 재검색 중..."})
        docs = await search_docs(search_query)
        yield sse("step", {"step": 5, "status": "done",
                           "msg": f'검색 쿼리: "{search_query}" · 문서 {len(docs)}개'})
    else:
        yield sse("branch", {"choice": "no", "msg": "아니오 · 초기 검색 결과 사용"})
        yield sse("step", {"step": 5, "status": "skipped", "msg": "재검색 건너뜀"})
        docs = initial_docs

    seen_urls = set()
    sources = []
    for d in docs:
        if d["url"] in seen_urls:
            continue
        seen_urls.add(d["url"])
        sources.append({"title": d["title"], "url": d["url"]})
    context = "\n\n".join(f"[{d['title']}]\n{d['content']}" for d in docs)

    # ── Step 3: 스트리밍 답변 — tool 메시지 없는 순수 대화 형식 ──
    # tool_calls 이력 없이 context를 user 메시지로 주입 → 모델이 tool 호출 시도 불가
    yield sse("step", {"step": 3, "status": "active", "msg": "LLM 답변 생성 중..."})

    answer_messages = [
        {"role": "system", "content":
            "You are an Azure AI expert assistant. "
            "Answer the question in Korean based on the provided search results. "
            "Keep the ENTIRE answer, including any table, under 350 words. "
            "Always finish the answer completely — never leave a sentence or a table row unfinished. "
            "If you use a table, keep it short (at most 4 rows) so it fits within the word limit."},
        {"role": "user", "content":
            f"다음 검색 결과를 참고해서 질문에 답해주세요.\n\n"
            f"[검색 결과]\n{context}\n\n"
            f"[질문]\n{question}"},
    ]

    def _stream():
        return gh_client.chat.completions.create(
            model=MODEL, messages=answer_messages, stream=True, max_tokens=850,
        )

    stream = await asyncio.to_thread(_stream)
    answer_parts = []
    # The SDK stream is synchronous; advance it in a worker so other requests stay responsive.
    sentinel = object()
    def _next_chunk():
        return next(stream, sentinel)
    while True:
        chunk = await asyncio.to_thread(_next_chunk)
        if chunk is sentinel:
            break
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            answer_parts.append(token)
            yield sse("token", {"token": token})
            await asyncio.sleep(0.015)  # 토큰 출력 속도 조절
    yield sse("step", {"step": 3, "status": "done", "msg": "답변 완료 ✅"})
    yield sse("step", {"step": 4, "status": "active", "msg": "답변 품질 평가 중..."})
    try:
        judge_messages = [
            {"role": "system", "content": (
                "Evaluate the answer against the question and supplied sources. "
                "Return only a JSON object with numeric relevance, completeness, and confidence "
                "scores between 0 and 1. Confidence means how well the answer is supported by the sources. "
                "Do not claim this is an objective or verified accuracy measurement."
            )},
            {"role": "user", "content": (
                f"Question:\n{question}\n\nSources:\n{context}\n\nAnswer:\n{''.join(answer_parts)}"
            )},
        ]
        judge_resp = await asyncio.to_thread(
            lambda: gh_client.chat.completions.create(model=MODEL, messages=judge_messages)
        )
        raw_scores = json.loads(judge_resp.choices[0].message.content)
        scores = {key: float(raw_scores[key]) for key in ("relevance", "completeness", "confidence")}
        if not all(0 <= score <= 1 for score in scores.values()):
            raise ValueError("Judge score outside 0–1 range")
        average_score = round(sum(scores.values()) / len(scores) * 100)
        yield sse("judge", {"scores": scores})
        yield sse("step", {"step": 4, "status": "done", "msg": f"평가 완료 · 평균 {average_score}점"})
    except (ValueError, TypeError, KeyError, IndexError):
        logger.exception("Judge returned invalid scores")
        yield sse("step", {"step": 4, "status": "error", "msg": "평가 결과를 표시할 수 없습니다"})
    except Exception:
        logger.exception("Judge request failed")
        yield sse("step", {"step": 4, "status": "error", "msg": "평가 요청에 실패했습니다"})
    # Keep the complete workflow visible for a minimum demo duration.
    remaining = MIN_DEMO_SECONDS - (asyncio.get_running_loop().time() - started_at)
    if remaining > 0:
        yield sse("hold", {"msg": "평가 결과 표시 중 · 데모 시간 조정"})
        await asyncio.sleep(remaining)
    yield sse("done", {"sources": sources})


@app.post("/demo")
async def demo(req: DemoRequest):
    return StreamingResponse(
        stream_demo(req.question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
