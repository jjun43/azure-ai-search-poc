"""
Azure AI Foundry 문서 크롤러
10개 핵심 페이지 수집 → docs_raw.json 저장
"""

import httpx
import json
import time
from bs4 import BeautifulSoup

# 수집할 10개 페이지
TARGET_URLS = [
    {
        "id": "doc_001",
        "title": "What is Azure AI Foundry",
        "url": "https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry"
    },
    {
        "id": "doc_002",
        "title": "Azure AI Foundry Quickstart",
        "url": "https://learn.microsoft.com/en-us/azure/ai-foundry/quickstarts/get-started-code"
    },
    {
        "id": "doc_003",
        "title": "Azure AI Foundry - Projects and Hubs",
        "url": "https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/ai-resources"
    },
    {
        "id": "doc_004",
        "title": "Azure AI Foundry Model Catalog",
        "url": "https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/model-catalog-overview"
    },
    {
        "id": "doc_005",
        "title": "RAG with Azure AI Foundry",
        "url": "https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/retrieval-augmented-generation"
    },
    {
        "id": "doc_006",
        "title": "What is Azure AI Search",
        "url": "https://learn.microsoft.com/en-us/azure/search/search-what-is-azure-search"
    },
    {
        "id": "doc_007",
        "title": "Azure AI Search - RAG Tutorial",
        "url": "https://learn.microsoft.com/en-us/azure/search/search-get-started-rag"
    },
    {
        "id": "doc_008",
        "title": "Azure AI Search - Vector Search",
        "url": "https://learn.microsoft.com/en-us/azure/search/vector-search-overview"
    },
    {
        "id": "doc_009",
        "title": "Function Calling with Azure OpenAI",
        "url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/function-calling"
    },
    {
        "id": "doc_010",
        "title": "Phi-4 Model in Azure AI Foundry",
        "url": "https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-phi-4"
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

def extract_text(html: str) -> str:
    """HTML에서 본문 텍스트 추출"""
    soup = BeautifulSoup(html, "html.parser")

    # 불필요한 태그 제거
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Microsoft Docs 본문 영역
    main = soup.find("main") or soup.find("article") or soup.find("div", {"id": "main-content"})
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # 빈 줄 정리
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

def chunk_text(text: str, chunk_size: int = 500) -> list[str]:
    """텍스트를 청크로 분할"""
    paragraphs = text.split("\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += " " + para
        else:
            if current.strip():
                chunks.append(current.strip())
            current = para

    if current.strip():
        chunks.append(current.strip())

    return chunks

def crawl():
    results = []

    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for doc in TARGET_URLS:
            print(f"[{doc['id']}] 수집 중: {doc['title']}")
            try:
                response = client.get(doc["url"])
                if response.status_code == 200:
                    text = extract_text(response.text)
                    chunks = chunk_text(text)
                    for i, chunk in enumerate(chunks):
                        results.append({
                            "id": f"{doc['id']}_chunk{i:03d}",
                            "doc_id": doc["id"],
                            "title": doc["title"],
                            "url": doc["url"],
                            "chunk_index": i,
                            "content": chunk
                        })
                    print(f"  → {len(chunks)}개 청크 생성")
                else:
                    print(f"  → 실패: HTTP {response.status_code}")
            except Exception as e:
                print(f"  → 에러: {e}")

            time.sleep(1)  # 요청 간격

    with open("docs_raw.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n완료: 총 {len(results)}개 청크 → docs_raw.json 저장")

if __name__ == "__main__":
    crawl()
