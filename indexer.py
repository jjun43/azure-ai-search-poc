"""
Azure AI Search 인덱서
docs_raw.json → Azure AI Search 인덱스 업로드
실행: python indexer.py
"""

import json
import os
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SimpleField, SearchableField, SearchFieldDataType
)
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()

ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
API_KEY  = os.getenv("AZURE_SEARCH_API_KEY")
INDEX    = os.getenv("AZURE_SEARCH_INDEX_NAME", "azure-ai-foundry-docs")


def create_index():
    client = SearchIndexClient(ENDPOINT, AzureKeyCredential(API_KEY))
    fields = [
        SimpleField(name="id",          type=SearchFieldDataType.String, key=True),
        SimpleField(name="doc_id",       type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title",   type=SearchFieldDataType.String),
        SimpleField(name="url",          type=SearchFieldDataType.String),
        SimpleField(name="chunk_index",  type=SearchFieldDataType.Int32),
        SearchableField(name="content", type=SearchFieldDataType.String),
    ]
    index = SearchIndex(name=INDEX, fields=fields)
    client.create_or_update_index(index)
    print(f"✅ 인덱스 '{INDEX}' 생성 완료")


def upload_docs():
    with open("docs_raw.json", encoding="utf-8") as f:
        docs = json.load(f)

    search_client = SearchClient(ENDPOINT, INDEX, AzureKeyCredential(API_KEY))

    batch_size = 100
    total = len(docs)
    for i in range(0, total, batch_size):
        batch = docs[i : i + batch_size]
        search_client.upload_documents(batch)
        print(f"  업로드: {min(i + batch_size, total)}/{total}")

    print(f"✅ 총 {total}개 청크 업로드 완료")


if __name__ == "__main__":
    create_index()
    upload_docs()
