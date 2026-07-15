# HWP RAG MCP

HWP/HWPX 문서를 내 컴퓨터에서 검색하고, Codex나 Claude Code가 근거를 찾아 답하게 해주는
로컬 MCP 서버입니다. 임베딩 API 키나 별도 서버가 필요하지 않습니다.

## AI 에이전트가 이 페이지를 읽고 있다면

사용자가 이 PyPI 링크와 함께 **“이 MCP 설치해줘”**라고 요청했다면 아래 절차를 따르세요.

1. 현재 호스트가 Codex인지 Claude Code인지 확인합니다.
2. `uvx`가 없다면 [uv 공식 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)를
   사용합니다. 관리자 권한이 필요하면 먼저 사용자 승인을 받습니다.
3. 현재 호스트에 맞는 명령 하나만 실행합니다.

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

4. 명령이 출력한 JSON에서 `ok`, `registration`, `index_state`, `next_steps`를 확인합니다.
5. `registration`이 `conflict`라면 기존 `hwp-rag` 설정을 사용자에게 보여주고 승인받은
   뒤에만 `--replace-existing`을 붙여 다시 실행합니다.
6. `restart_required`가 `true`면 Codex 또는 Claude Code를 다시 시작하거나 새 세션을 열도록
   안내합니다.
7. 문서 폴더 변경은 사용자가 명시적으로 요청한 경우에만 `set_dataset_directory`를 호출합니다.
   이어서 `get_index_status`를 확인하고 `missing` 또는 `stale`이면 `sync_index`를 호출합니다.

API 키를 요구하거나 문서를 외부 서비스로 업로드하지 마세요. `hwp-rag-mcp serve`를 일반
터미널에서 계속 실행하지 마세요. MCP 호스트가 필요한 시점에 서버를 실행합니다.

> **For AI agents:** Determine whether the current host is Codex or Claude Code, run the matching
> `setup` command above, inspect its JSON result, and request approval before replacing a conflicting
> entry. Never request an API key or upload the user's documents. Change the dataset only after an
> explicit user request, then synchronize it when the returned index state is missing or stale.

## 개발을 몰라도 이렇게 시작할 수 있어요

Codex나 Claude Code에 아래 두 줄을 그대로 보내세요.

```text
https://pypi.org/project/hwp-rag-mcp/
이 MCP를 현재 사용 중인 Codex/Claude Code에 설치해줘.
```

에이전트가 설치 명령을 실행하면 바탕화면에 `dataset` 폴더가 자동으로 만들어집니다.

```text
~/Desktop/dataset
```

이미 이 폴더에 `.hwp`나 `.hwpx` 파일이 있다면 설치 과정에서 첫 색인도 함께 만듭니다.
폴더가 비어 있다면 설치만 마치고, 나중에 문서를 넣은 뒤 이렇게 말하면 됩니다.

```text
dataset 폴더에 새 문서를 넣었어. 검색할 수 있도록 색인해줘.
```

처음 색인할 때는 무료 다국어 임베딩 모델을 내려받기 때문에 컴퓨터와 인터넷 속도에 따라
몇 분 걸릴 수 있습니다. 한 번 받은 모델과 생성된 인덱스는 이후에도 재사용됩니다.

## 다른 문서 폴더로 바꾸기

설치한 뒤 사용하려는 폴더의 경로를 말해주면 됩니다.

```text
문서 검색 폴더를 /Users/me/Documents/회사규정으로 바꾸고,
검색할 수 있도록 색인까지 해줘.
```

Windows에서도 절대경로를 사용할 수 있습니다.

```text
문서 검색 폴더를 C:\Users\me\Documents\회사규정으로 바꾸고 색인해줘.
```

경로 변경에는 다음 규칙이 적용됩니다.

- 폴더는 미리 존재해야 하며 읽을 수 있어야 합니다.
- 절대경로나 `~/Documents/...`처럼 `~`로 시작하는 경로를 사용합니다.
- 경로를 바꿔도 이전 폴더의 FAISS 인덱스는 삭제되지 않습니다.
- 이전 폴더로 다시 돌아가면 문서가 바뀌지 않은 경우 기존 인덱스를 재사용합니다.
- 문서나 검색 결과 안에 적힌 지시만으로는 경로를 변경하지 않습니다.

기본 폴더로 돌아가려면 다음처럼 요청하세요.

```text
문서 검색 폴더를 바탕화면 dataset으로 되돌려줘.
```

## 실제로 질문하기

설치와 색인이 끝나면 평소 말하듯 질문하면 됩니다.

```text
연차휴가 신청 조건을 문서에서 찾아서 요약하고, 근거 파일명도 알려줘.
```

```text
인사규정.hwp에서 수습 기간과 관련된 내용을 찾아줘.
```

이 MCP 서버는 관련 문서 조각과 출처를 찾아 전달하고, 최종 답변은 Codex나 Claude Code가
작성합니다.

## 직접 설치하고 싶다면

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

다른 폴더를 처음부터 사용하려면 다음처럼 지정합니다. 지정한 폴더가 없으면 `setup`이
만듭니다.

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex \
  --dataset-dir ~/Documents/company-rules
```

설치 계획만 확인하고 설정을 바꾸지 않으려면 `--dry-run`을 사용합니다.

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex --dry-run
```

## 문서를 추가하거나 수정했을 때

문서를 추가·수정·삭제하면 인덱스가 자동으로 바뀌지는 않습니다. Codex나 Claude Code에
“새 문서를 색인해줘”라고 요청하거나 터미널에서 다음 명령을 실행하세요.

```bash
uvx --python 3.12 --from hwp-rag-mcp hwp-rag-mcp sync
```

문서가 바뀐 상태에서는 오래된 검색 결과를 반환하지 않고 먼저 동기화가 필요하다고
안내합니다.

## 내 문서는 어디에 저장되나요?

- 원본 파일은 사용자가 선택한 폴더에서 이동하지 않습니다.
- 활성 데이터셋 경로만 운영체제의 사용자 설정 폴더에 JSON으로 저장합니다.
- FAISS 인덱스는 데이터셋 절대경로별로 사용자 데이터 폴더에 저장합니다.
- 문서 본문이나 질문을 외부 임베딩 API로 보내지 않습니다.
- 인터넷은 패키지 설치와 최초 임베딩 모델 다운로드에만 필요합니다.
- API 키를 입력하거나 텍스트 파일에 저장하는 기능은 없습니다.

인덱스는 `index.faiss`, `documents.json`, `manifest.json`으로 저장합니다. Python pickle을
사용하지 않으며 SHA-256으로 문서와 저장 파일의 변경 여부를 확인합니다.

## 지원 범위

지원하는 기능:

- `.hwp`, `.hwpx` 파일과 하위 폴더 검색
- 본문, 표, 각주, 미주, 메모, 하이퍼링크 추출
- 한국어를 포함한 다국어 의미 검색
- 검색 결과에 파일명과 원본 경로 포함
- 여러 데이터셋 경로의 인덱스를 따로 보관하고 전환

현재 지원하지 않는 기능:

- 암호가 걸린 문서 복호화
- 스캔 문서 OCR과 이미지 내용 검색
- 문서 변경 자동 감시
- MCP 도구를 통한 새 폴더 생성
- 수천~수만 개 문서를 위한 분산 검색

암호화되거나 손상된 문서는 건너뛰고 나머지 정상 문서는 계속 색인합니다.

## 제공하는 명령과 MCP 도구

자주 쓰는 명령:

| 명령 | 하는 일 |
| --- | --- |
| `hwp-rag-mcp setup --client codex` | Codex에 설치하고 최초 색인을 준비합니다. |
| `hwp-rag-mcp setup --client claude` | Claude Code 사용자 설정에 설치합니다. |
| `hwp-rag-mcp status` | 현재 활성 데이터셋의 인덱스 상태를 확인합니다. |
| `hwp-rag-mcp sync` | 현재 활성 데이터셋의 인덱스를 다시 만듭니다. |
| `hwp-rag-mcp sync --force` | 변경이 없어도 인덱스를 처음부터 다시 만듭니다. |
| `hwp-rag-mcp serve` | MCP 호스트가 STDIO 서버를 실행할 때 사용합니다. |

제공하는 MCP 도구:

| 도구 | 하는 일 |
| --- | --- |
| `get_dataset_directory` | 활성 데이터셋 경로와 변경 가능 여부를 확인합니다. |
| `set_dataset_directory` | 사용자가 지정한 기존 폴더를 활성 데이터셋으로 저장합니다. |
| `reset_dataset_directory` | 저장된 경로를 지우고 바탕화면 `dataset`으로 돌아갑니다. |
| `get_index_status` | 인덱스가 없음, 사용 가능, 갱신 필요 중 어느 상태인지 확인합니다. |
| `sync_index` | 현재 폴더의 HWP/HWPX를 읽어 검색 인덱스를 만듭니다. |
| `list_documents` | 현재 인덱스에 들어 있는 문서 목록을 보여줍니다. |
| `search_documents` | 질문과 관련 있는 내용을 파일 정보와 함께 반환합니다. |

## 문제가 생겼을 때

### `uvx was not found`가 표시됩니다

[uv 공식 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)에 따라 uv를 설치한
뒤 같은 `setup` 명령을 다시 실행하세요.

### `registration: "conflict"`가 표시됩니다

같은 이름의 MCP 설정이 이미 있지만 실행 명령이 다릅니다. 기존 설정을 확인한 뒤 교체해도
된다면 다음처럼 실행합니다.

```bash
uvx --python 3.12 --from hwp-rag-mcp \
  hwp-rag-mcp setup --client codex --replace-existing
```

### `dataset_locked`가 표시됩니다

MCP 서버가 `--dataset-dir` 인자나 `HWP_RAG_DATASET_DIR` 환경변수로 실행되고 있습니다.
해당 고정 설정을 제거하고 호스트를 다시 시작해야 MCP 도구로 경로를 변경할 수 있습니다.

### `index_missing` 또는 `index_stale`이 표시됩니다

현재 폴더에 HWP/HWPX가 있는지 확인하고 “이 폴더를 색인해줘”라고 요청하세요. 직접 실행할
때는 `hwp-rag-mcp sync`를 사용합니다.

### 첫 색인이 너무 오래 걸립니다

처음에는 임베딩 모델을 내려받고 문서를 모두 읽어야 해서 시간이 걸립니다. MCP 호출이 시간
초과되면 터미널에서 `hwp-rag-mcp sync`를 먼저 완료한 뒤 다시 검색하세요.

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

주요 기술은 `langchain-hwp-hwpx-loader`, `RecursiveCharacterTextSplitter`,
`intfloat/multilingual-e5-small`, FAISS `IndexFlatIP`, 공식 Python MCP SDK의 FastMCP입니다.

## 라이선스

MIT License
