# Azure AI Search PoC

Azure AI Search에서 문서를 찾고, Groq의 GPT-OSS 20B가 Function Calling으로 검색 쿼리를 생성한 뒤 답변을 스트리밍하는 데모입니다. 마지막 단계에서 LLM이 답변을 자체 평가합니다. 평가 점수는 사실 검증 결과가 아닙니다.

## 로컬 실행

Python 3.11 이상 환경에서:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

`.env`에 `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`, `AZURE_SEARCH_INDEX_NAME`, `GITHUB_TOKEN`(Groq API 키), `GITHUB_MODEL`, `GITHUB_ENDPOINT`를 설정합니다. 키를 Git에 추가하지 마세요. 화면은 `http://127.0.0.1:8000`, 상태 확인은 `/health`입니다. `static/index.html` 파일을 직접 열면 데모 요청이 백엔드에 연결되지 않습니다.

Workflow는 실제 검색, 도구 호출, 재검색, 답변, 평가 이벤트에 따라 진행 상태를 표시합니다. 데모 결과는 총 표시 시간이 최소 15초가 되도록 완료 후 남은 시간을 기다립니다. 이 추가 시간은 화면에 `데모 시간 조정`으로 표시됩니다.

## Render 배포

저장소 루트에 [render.yaml](render.yaml)이 포함되어 있습니다. Render에서 New → Blueprint로 이 GitHub 저장소를 연결하면 자동으로 인식됩니다. 초기 생성 화면에서 `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`, `GITHUB_TOKEN` 값을 입력합니다. `sync: false` 값은 이후 Blueprint 동기화에 반영되지 않으므로 키 변경 시 서비스의 환경변수를 직접 수정합니다.

무료 웹 서비스는 유휴 상태에서 중지될 수 있어 첫 요청이 느릴 수 있습니다. 사용하지 않는 서비스를 계속 깨우는 모니터링은 설정하지 않았습니다.
