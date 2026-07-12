# HWP RAG MCP

바탕화면에 모아 둔 한글 문서를 Codex나 Claude Code에서 바로 검색해 보세요.

회사 규정, 업무 매뉴얼, 보고서가 `.hwp`나 `.hwpx` 파일로 쌓여 있는데 AI가 내용을
찾아주지 못해 불편했다면 이 패키지를 사용할 수 있습니다. 문서를 내 컴퓨터에서 읽고
검색용 인덱스를 만든 뒤, 질문과 관련 있는 내용을 Codex 또는 Claude Code에 전달합니다.

- 문서와 검색 인덱스는 내 컴퓨터에만 저장됩니다.
- 임베딩 API 키나 별도 서버가 필요하지 않습니다.
- 본문뿐 아니라 표, 각주, 미주, 메모도 함께 검색할 수 있습니다.
- macOS, Windows, Linux에서 같은 방식으로 사용할 수 있습니다.

> 이 프로젝트는 개인이나 소규모 팀이 수십 개 정도의 문서를 검색하는 용도로 만들었습니다.
> 스캔 이미지 OCR, 이미지 검색, 문서 자동 감시는 아직 지원하지 않습니다.

## 가장 빠르게 시작하기

Python 3.10~3.13과 [uv](https://docs.astral.sh/uv/) 사용을 권장합니다.

### 1. 문서를 넣을 폴더 만들기

바탕화면에 `dataset` 폴더를 만들고 검색할 HWP/HWPX 파일을 넣습니다.

```bash
mkdir -p ~/Desktop/dataset
```

폴더 안에 하위 폴더를 만들어 정리해도 괜찮습니다.

### 2. 설치하기

```bash
uv tool install hwp-rag-mcp
```

이미 설치했다면 다음 명령으로 새 버전으로 올릴 수 있습니다.

```bash
uv tool upgrade hwp-rag-mcp
```

`uv` 대신 `pipx install hwp-rag-mcp`를 사용해도 됩니다.

### 3. 처음 한 번 색인하기

```bash
hwp-rag-mcp sync
```

처음 실행할 때는 무료 한국어 임베딩 모델을 내려받습니다. 수백 MB 정도를 다운로드하므로
컴퓨터와 인터넷 속도에 따라 몇 분 걸릴 수 있습니다. 한 번 받아 둔 모델은 이후에도 계속
재사용합니다.

색인이 잘 만들어졌는지 확인하려면 다음 명령을 실행하세요.

```bash
hwp-rag-mcp status
```

`"state": "current"`가 보이면 검색할 준비가 끝난 것입니다.

### 4. Codex에 연결하기

```bash
codex mcp add hwp-rag -- \
  uvx --from hwp-rag-mcp hwp-rag-mcp serve
```

등록한 뒤 `codex mcp list` 또는 Codex의 `/mcp` 메뉴에서 `hwp-rag`가 연결됐는지
확인합니다.

### 5. Claude Code에 연결하기

```bash
claude mcp add hwp-rag -- \
  uvx --from hwp-rag-mcp hwp-rag-mcp serve
```

이제 평소처럼 질문하면 됩니다.

```text
연차휴가를 신청하려면 어떤 조건이 필요한지 문서에서 찾아줘.
근거가 나온 파일명도 함께 알려줘.
```

```text
인사규정.hwp에서 수습 기간과 관련된 내용을 찾아서 요약해줘.
```

## 문서를 추가하거나 수정했을 때

파일이 바뀌었다고 해서 검색 결과가 자동으로 갱신되지는 않습니다. `dataset` 폴더에 문서를
추가하거나 기존 문서를 수정·삭제했다면 다시 동기화해 주세요.

```bash
hwp-rag-mcp sync
```

문서가 바뀐 상태에서 검색하면 오래된 내용을 보여주는 대신 먼저 동기화가 필요하다고
안내합니다.

## 다른 폴더를 사용하고 싶다면

기본 폴더는 `~/Desktop/dataset`입니다. 다른 폴더를 쓰려면 명령 끝에 경로를 지정합니다.

```bash
hwp-rag-mcp sync --dataset-dir ~/Documents/company-rules
```

MCP를 등록할 때도 같은 경로를 넘겨야 합니다.

```bash
codex mcp add hwp-rag -- \
  uvx --from hwp-rag-mcp hwp-rag-mcp serve \
  --dataset-dir ~/Documents/company-rules
```

매번 경로를 적고 싶지 않다면 `HWP_RAG_DATASET_DIR` 환경변수를 사용할 수 있습니다.

## 내 문서는 어디에 저장되나요?

- 원본 HWP/HWPX 파일은 사용자가 만든 `dataset` 폴더에서 이동하지 않습니다.
- 검색용 FAISS 인덱스는 운영체제의 사용자 데이터 폴더에 저장됩니다.
- 문서 본문이나 검색어를 외부 임베딩 API로 보내지 않습니다.
- 인터넷은 최초 임베딩 모델 다운로드와 패키지 설치에만 필요합니다.
- API 키를 입력하거나 텍스트 파일에 저장하는 기능은 없습니다.

인덱스는 `index.faiss`, `documents.json`, `manifest.json`으로 저장합니다. Python pickle을
사용하지 않으며, 파일이 손상되거나 바뀌었는지 SHA-256으로 확인합니다.

## 지원하는 문서와 제한 사항

지원하는 기능:

- `.hwp`, `.hwpx` 파일과 하위 폴더 검색
- 본문, 표, 각주, 미주, 메모, 하이퍼링크 추출
- 한국어를 포함한 다국어 의미 검색
- 문서별 파일명과 원본 경로를 검색 결과에 포함

현재 지원하지 않는 기능:

- 암호가 걸린 문서 복호화
- 스캔 문서 OCR
- 문서 안의 이미지 내용 검색
- 문서 변경 자동 감시
- 수천~수만 개 문서를 위한 분산 검색

암호화되거나 손상된 문서는 건너뛰고, 나머지 정상 문서는 계속 색인합니다.

## 자주 쓰는 명령

| 명령 | 언제 사용하나요? |
| --- | --- |
| `hwp-rag-mcp status` | 현재 인덱스를 바로 검색할 수 있는지 확인할 때 |
| `hwp-rag-mcp sync` | 문서를 처음 넣었거나 파일이 바뀌었을 때 |
| `hwp-rag-mcp sync --force` | 변경이 없어도 인덱스를 처음부터 다시 만들 때 |
| `hwp-rag-mcp serve` | MCP 클라이언트가 로컬 서버를 실행할 때 |

## 제공하는 MCP 도구

| 도구 | 하는 일 |
| --- | --- |
| `get_index_status` | 인덱스가 없음, 사용 가능, 갱신 필요 중 어느 상태인지 확인합니다. |
| `sync_index` | HWP/HWPX 파일을 다시 읽어 검색 인덱스를 만듭니다. |
| `list_documents` | 현재 인덱스에 들어 있는 문서 목록을 보여줍니다. |
| `search_documents` | 질문과 관련 있는 문서 내용을 찾아 파일 정보와 함께 반환합니다. |

검색 결과를 바탕으로 실제 답변을 작성하는 일은 Codex나 Claude Code가 담당합니다. 이 MCP
서버가 별도의 유료 LLM API를 호출하지는 않습니다.

## 문제가 생겼을 때

### `index_missing`이 표시됩니다

`~/Desktop/dataset` 폴더가 있는지, 그 안에 `.hwp` 또는 `.hwpx` 파일이 있는지 확인한 뒤
`hwp-rag-mcp sync`를 실행하세요.

### `index_stale`이 표시됩니다

문서가 추가·수정·삭제된 상태입니다. `hwp-rag-mcp sync`를 한 번 더 실행하세요.

### 첫 동기화가 너무 오래 걸립니다

처음에는 임베딩 모델을 내려받고 문서를 모두 읽어야 해서 시간이 걸립니다. MCP 도구에서
시간 초과가 난다면 터미널에서 `hwp-rag-mcp sync`를 먼저 마친 뒤 다시 검색하세요.

### 특정 문서만 검색되지 않습니다

암호화됐거나 손상된 문서일 수 있습니다. `sync` 결과의 `skipped_files`와 `failed_files`를
확인하세요.

## 개발하기

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check .
mypy src/hwp_rag_mcp
pytest
python -m build
twine check dist/*
```

## 사용 기술

- HWP/HWPX 파싱: `langchain-hwp-hwpx-loader`
- 문서 분할: `RecursiveCharacterTextSplitter`
- 로컬 임베딩: `intfloat/multilingual-e5-small`
- 벡터 검색: FAISS `IndexFlatIP`
- MCP 서버: 공식 Python MCP SDK의 FastMCP

## 라이선스

MIT License

## English summary

HWP RAG MCP indexes local Korean HWP/HWPX documents with a free multilingual embedding model and
exposes evidence search to Codex and Claude Code over MCP. Documents and indexes remain on the
user's computer, and no embedding API key is required.
