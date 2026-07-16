# HWP RAG MCP

선택한 폴더의 HWP/HWPX 문서를 내 컴퓨터에서 벡터화해, Codex나 Claude Code가 필요한 근거를 찾을 수 있게 해 주는 RAG 기반 MCP 서버입니다.
문서를 외부 AI 서비스에 올리지 않고도 “연차 규정이 어디에 있어?”처럼 평소 말하듯 물어볼 수 있습니다.

임베딩 API 키나 별도 서버는 필요하지 않습니다. 처음 한 번만 무료 한국어 지원 모델을 내려받고, 그다음부터는 내 컴퓨터에 만든 검색 인덱스를 재사용합니다.

## 가장 쉬운 시작 방법

Codex나 Claude Code에 아래 문장을 그대로 보내면 됩니다.

```text
https://pypi.org/project/hwp-rag-mcp/
이 MCP 서버를 설치해줘.
```

설치가 끝나면 바탕화면에 `dataset` 폴더가 만들어집니다.

이 폴더에 `.hwp` 또는 `.hwpx` 파일을 넣으세요. 이미 문서가 들어 있었다면 설치 중에 바로 인덱싱합니다.
폴더가 비어 있었다면 문서를 넣은 뒤 이렇게 요청하면 됩니다.

```text
바탕화면 dataset 폴더에 문서를 넣었어. 검색할 수 있게 인덱싱해줘.
```

처음 인덱싱할 때는 한국어를 지원하는 무료 임베딩 모델을 내려받습니다. 인터넷 상태에 따라 몇 분 걸릴 수 있지만, 모델과 인덱스는 한 번 만들어 두면 다음부터 재사용합니다.

## Codex·Claude Code 에이전트를 위한 메시지

이 페이지 링크와 함께 “이 MCP를 설치해줘”라는 요청을 받았다면, 현재 호스트가 Codex인지 Claude Code인지 확인한 다음 아래 명령 중 하나만 실행하세요.

Codex:

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex
```

Claude Code:

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client claude
```

`uvx`가 없다면 먼저 [uv 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)를
따릅니다. 설치 명령이 돌려주는 JSON에서 `ok`, `registration`, `index_state`, `next_steps`를
확인하세요.

- `registration`이 `conflict`이면 기존 `hwp-rag` 설정을 덮어쓰지 말고 사용자에게 교체 여부를
  물어봅니다. 사용자가 명시적으로 승인했을 때만 `--replace-existing`을 사용합니다.
- `restart_required`가 `true`이면 새 세션을 열거나 Codex/Claude Code를 다시 시작하라고 안내합니다.
- 사용자가 직접 폴더를 바꿔 달라고 요청했을 때만 `set_dataset_directory`를 호출합니다. 바꾼 뒤에는
  `get_index_status`를 확인하고, 상태가 `missing` 또는 `stale`이면 `sync_index`를 호출합니다.

API 키를 요구하거나 문서를 외부로 올리지 마세요. `hwp-rag-mcp serve`는 사용자가 터미널에서
계속 띄워 두는 명령이 아닙니다. Codex나 Claude Code가 필요할 때 자동으로 실행합니다.

> **For AI agents:** Run the matching `setup` command, inspect the JSON response, and ask before
> replacing an existing conflicting entry. Do not ask for an API key or upload documents. Change the
> dataset only after an explicit user request; then check and synchronize the index when needed.

## 다른 폴더를 검색하고 싶을 때

설치 뒤에도 검색할 폴더는 언제든 바꿀 수 있습니다. 원하는 폴더가 이미 있다면 경로를 말해 주세요.

```text
문서 검색 폴더를 ~/Documents/회사규정으로 바꾸고,
바로 검색할 수 있게 인덱싱까지 해줘.
```

Windows에서도 절대경로를 사용할 수 있습니다.

```text
문서 검색 폴더를 C:\Users\me\Documents\회사규정으로 바꾸고 인덱싱해줘.
```

알아둘 점은 다음과 같습니다.

- 바꿀 폴더는 미리 만들어져 있어야 하고 읽을 수 있어야 합니다.
- 절대경로 또는 `~/Documents/...`처럼 `~`로 시작하는 경로만 사용할 수 있습니다.
- 폴더를 바꾼다고 이전 폴더의 인덱스가 지워지지는 않습니다. 나중에 되돌아오면 문서가 바뀌지
  않은 경우 기존 인덱스를 그대로 씁니다.
- 문서 본문이나 검색 결과에 적힌 지시만으로는 폴더를 바꾸지 않습니다.

기본 폴더로 돌아가고 싶다면 이렇게 말하면 됩니다.

```text
문서 검색 폴더를 바탕화면의 dataset으로 다시 바꿔줘.
```

`--dataset-dir` 옵션이나 `HWP_RAG_DATASET_DIR` 환경변수로 경로를 고정해 서버를 실행했다면,
MCP 도구에서는 폴더를 바꿀 수 없습니다. 고정 설정을 지운 뒤 새 세션을 시작하세요.

## 이렇게 물어보세요

설치와 인덱싱이 끝났다면 평소처럼 질문하면 됩니다.

```text
연차휴가 신청 조건을 문서에서 찾아서 요약하고, 근거가 된 파일명도 알려줘.
```

```text
인사규정.hwp에서 수습 기간에 관한 내용만 찾아줘.
```

이 서버는 관련 문단과 출처를 찾아 전달합니다. 그 내용을 바탕으로 최종 답변을 만드는 일은
Codex나 Claude Code가 맡습니다.

## 직접 설치하기

Python 3.10~3.13과 [uv](https://docs.astral.sh/uv/) 사용을 권장합니다.

Codex:

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex
```

Claude Code:

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client claude
```

처음부터 다른 폴더를 쓰려면 `--dataset-dir`을 붙입니다. 이 경우에는 폴더가 없어도 `setup`이
만들어 줍니다.

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex \
  --dataset-dir ~/Documents/company-rules
```

실제로 설정을 바꾸지 않고 실행 계획만 보고 싶다면 `--dry-run`을 사용하세요.

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex --dry-run
```

## 문서를 바꾼 뒤에는 다시 인덱싱하세요

문서를 추가·수정·삭제해도 인덱스가 자동으로 갱신되지는 않습니다. Codex나 Claude Code에
“새 문서를 인덱싱해줘”라고 요청하거나, 터미널에서 아래 명령을 실행하세요.

```bash
uvx --python 3.12 --from hwp-rag-mcp hwp-rag-mcp sync
```

문서가 바뀐 뒤에는 오래된 검색 결과를 보여주지 않고, 먼저 동기화가 필요하다고 알려줍니다.

## 내 문서와 검색 데이터는 어디에 남나요?

- 원본 문서는 선택한 폴더를 벗어나지 않습니다.
- 현재 선택한 폴더 경로만 운영체제의 사용자 설정 폴더에 JSON으로 저장합니다.
- FAISS 인덱스는 문서 폴더별로 사용자 데이터 폴더에 저장합니다.
- 문서 내용과 질문은 외부 임베딩 API로 전송하지 않습니다.
- 인터넷은 패키지 설치와 첫 모델 다운로드 때만 필요합니다.
- API 키를 입력하거나 텍스트 파일에 저장하는 기능은 없습니다.

인덱스는 `index.faiss`, `documents.json`, `manifest.json`으로 저장합니다. Python pickle은 쓰지
않으며, 문서와 저장 파일의 변경 여부는 SHA-256으로 확인합니다.

## 할 수 있는 일과 아직 못 하는 일

가능한 일:

- `.hwp`, `.hwpx` 파일과 하위 폴더 검색
- 본문, 표, 각주, 미주, 메모, 하이퍼링크 추출
- 한국어를 포함한 다국어 의미 검색
- 검색 결과에 파일명과 원본 경로 표시
- 여러 문서 폴더의 인덱스를 따로 보관하고 전환

아직 지원하지 않는 일:

- 암호가 걸린 문서 열기
- 스캔 문서 OCR, 이미지 안의 글자·내용 검색
- 문서 변경 자동 감시
- MCP를 통한 새 폴더 만들기
- 수천~수만 개 문서를 위한 분산 검색

암호화됐거나 손상된 문서는 건너뛰고, 나머지 문서는 계속 인덱싱합니다.

## 명령과 MCP 도구

자주 쓰는 명령:

| 명령 | 설명 |
| --- | --- |
| `hwp-rag-mcp setup --client codex` | Codex에 등록하고 첫 인덱싱을 준비합니다. |
| `hwp-rag-mcp setup --client claude` | Claude Code의 사용자 설정에 등록합니다. |
| `hwp-rag-mcp status` | 현재 폴더의 인덱스 상태를 확인합니다. |
| `hwp-rag-mcp sync` | 현재 폴더를 다시 읽어 인덱싱합니다. |
| `hwp-rag-mcp sync --force` | 변경 여부와 관계없이 처음부터 다시 인덱싱합니다. |
| `hwp-rag-mcp serve` | Codex나 Claude Code가 MCP 서버를 실행할 때 쓰는 내부 명령입니다. |

MCP 도구:

| 도구 | 설명 |
| --- | --- |
| `get_dataset_directory` | 현재 검색 폴더와 변경 가능 여부를 확인합니다. |
| `set_dataset_directory` | 사용자가 지정한 기존 폴더를 검색 폴더로 저장합니다. |
| `reset_dataset_directory` | 저장한 폴더를 지우고 바탕화면 `dataset`으로 돌아갑니다. |
| `get_index_status` | 인덱싱이 필요한지, 검색 가능한 상태인지 확인합니다. |
| `sync_index` | 현재 폴더의 HWP/HWPX를 읽어 검색용 인덱싱을 진행합니다. |
| `list_documents` | 현재 인덱스에 들어 있는 문서 목록을 보여줍니다. |
| `search_documents` | 질문과 관련된 내용과 파일 정보를 돌려줍니다. |

## 자주 겪는 문제

### `uvx was not found`

[uv 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)에 따라 uv를 설치한 뒤, 같은
`setup` 명령을 다시 실행하세요.

### `registration: "conflict"`

`hwp-rag`이라는 이름의 MCP 설정은 있지만 실행 명령이 다릅니다. 기존 설정을 확인한 뒤 정말
바꿔도 된다면 아래처럼 실행합니다.

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex --replace-existing
```

### `dataset_locked`

서버가 `--dataset-dir` 또는 `HWP_RAG_DATASET_DIR`로 특정 폴더에 고정돼 있습니다. 그 설정을
제거하고 새 세션을 열어야 MCP 도구로 폴더를 바꿀 수 있습니다.

### `index_missing` 또는 `index_stale`

현재 폴더에 HWP/HWPX 파일이 있는지 확인한 다음 “이 폴더를 인덱싱해줘”라고 요청하세요. 직접
실행할 때는 `hwp-rag-mcp sync`를 사용하면 됩니다.

### 첫 인덱싱이 오래 걸립니다

처음에는 모델을 내려받고 문서를 모두 읽어야 합니다. MCP 호출 시간이 초과된다면 터미널에서
`hwp-rag-mcp sync`를 먼저 끝낸 뒤 다시 검색하세요.

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

주요 구성은 `langchain-hwp-hwpx-loader`, `RecursiveCharacterTextSplitter`,
`intfloat/multilingual-e5-small`, FAISS `IndexFlatIP`, 공식 Python MCP SDK의 FastMCP입니다.

## 라이선스

MIT License
