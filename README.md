# Paper Blog

최신 논문을 찾고 한국어 요약을 Markdown과 분야별 블로그로 모으는 개인 연구실입니다. 기존 로컬 UI의 초록 조사 기능과 별도로, 아래의 **주간 선정·일간 원문 요약 파이프라인**은 Antigravity CLI(`agy`)와 GitHub Pages 자동 게시를 지원합니다.

## 바로 실행하기 (Windows)

1. `start.cmd`를 더블클릭합니다. 블로그 주소는 **http://127.0.0.1:8765** 입니다.
2. 로그인 없이 둘러보려면 **데모 글로 둘러보기**를 누르세요. 데모는 2017년 논문이며 최신 조사 결과가 아닙니다.
3. 실제 조사를 하려면 `login-gemini.cmd`를 실행하고 **Sign in with Google**을 선택합니다. 학생 AI Pro 혜택을 받은 Google 계정으로 로그인한 다음 `/quit`로 종료합니다.
4. 블로그의 **설정 및 실행 기록**에서 분야 이름, arXiv 검색식, Gemini 조사 지침을 바꾸고 저장합니다.
5. **지금 논문 조사하기**를 누르세요. 실행 기록에서 완료·실패 여부를 볼 수 있고, 완료된 글은 분야별 페이지에 나타납니다.
6. 자동 수집을 원하면 **주기적으로 자동 조사**를 켜고 저장합니다. **서버 창과 PC가 켜져 있어야 합니다.** 처음 켜면 아직 실행하지 않은 활성 분야부터 조사합니다.

필요한 프로그램: Python 3.10 이상, Node.js 20 이상, 인터넷. 이 폴더를 다른 PC로 옮겼다면 `.venv`와 `node_modules`는 재사용하지 말고 각 시작 스크립트로 다시 설치하세요. 현재 PC에는 실행 의존성을 설치해 두었습니다.

## 학생 구독과 Gemini 연결

학생 혜택은 일반적으로 Google AI Pro 구독 혜택이며, Gemini 앱의 사용량이 그대로 API 토큰 잔액이 되는 구조는 아닙니다. 이 프로젝트는 **Gemini CLI의 Google 로그인**을 사용합니다. 공식 문서는 AI Pro/Ultra 구독 계정으로 로그인하도록 안내하며, 기존 로그인 자격 증명을 이용한 headless 실행을 지원합니다.

- [Gemini CLI 로그인](https://geminicli.com/docs/get-started/authentication/)
- [CLI 사용 한도와 요금](https://geminicli.com/docs/resources/quota-and-pricing/)
- [Gemini API 별도 결제 체계](https://ai.google.dev/gemini-api/docs/billing)

CLI·Code Assist 한도는 Gemini 웹 앱과 같다고 가정하면 안 됩니다. 학생 혜택 적용 여부·계정 자격·사용 가능 모델은 실제 로그인 계정과 Google 정책에 따릅니다. 혜택이 반영되지 않으면 Google 구독 계정과 CLI 로그인 계정이 같은지 확인하세요. 학교가 관리하는 Workspace 계정은 별도 프로젝트 설정이 필요할 수 있습니다.

이 앱의 자동 요약 프로세스는 Google OAuth 인증만 사용하도록 설정합니다. API 키나 Vertex AI로 자동 전환하지 않습니다. API 키는 입력할 필요가 없습니다. `login-gemini.cmd`에서는 반드시 Google 로그인을 선택하세요. 로그인 자격 증명은 Gemini CLI가 사용자 프로필에 관리하며 이 프로젝트의 Markdown이나 정적 블로그에 저장하지 않습니다.

## 분야 설정

웹 설정 화면 또는 `config.json`을 사용합니다. 파일을 직접 수정하면 다음 실행부터 읽습니다. 웹 화면에서는 변경 후 저장해야 합니다.

| 설정 | 의미 |
| --- | --- |
| 분야 ID | 영문 소문자·숫자·하이픈, URL과 Markdown 폴더 이름에 사용 |
| 분야 이름·소개 | 메뉴와 분야별 페이지에 표시 |
| arXiv 검색식 | 실제 수집 대상 결정 |
| Gemini 조사 지침 | 초록을 어떤 관점으로 요약할지 결정 |
| 조사 주기 | 1~720시간, 마지막 조사 시작 시점 기준 |
| 최근 며칠 | 최초 제출일 기준 1~365일 |
| 최대 편수 | 한 번에 새 논문 1~20편, 최신순 |
| 자동·전체 조사에 포함 | 자동 조사와 전체 수동 조사의 대상 여부 |
| Gemini 모델 | 비워두면 로그인 계정의 CLI 기본 모델, 필요하면 모델명 지정 |

검색식 예시:

```text
cat:cs.AI OR cat:cs.CL
cat:cs.CL AND (ti:reasoning OR ti:agent)
cat:cs.CR AND all:"post-quantum"
cat:cs.RO
cat:quant-ph
cat:q-bio.NC
```

조사 지침 예시:

> RAG와 LLM 에이전트의 신뢰성에 관심이 있습니다. 문제 정의, 새로운 접근법, 기존 연구와의 차이를 설명하고, 재현을 위해 전문에서 확인할 사항을 적어주세요. 초록에 없는 실험 수치는 추정하지 마세요.

검색 범위는 현재 **arXiv**입니다. 모든 학술 데이터베이스를 포괄하지 않으며 특히 의학·인문사회 분야는 arXiv 범위에 한계가 있습니다. arXiv에는 심사 전 프리프린트도 포함됩니다. [검색식 문서](https://info.arxiv.org/help/api/user-manual.html)를 참고하세요.

## 조사 방식과 한계

1. arXiv에서 설정한 기간 안에 최초 제출된 논문을 최신순으로 최대 200편 조회합니다. 요청 간 최소 3.1초를 두고 네트워크 일시 오류를 제한적으로 재시도합니다.
2. 분야별로 이미 저장한 arXiv ID+버전을 제외한 후 설정한 편수만 요약합니다. 같은 논문이 여러 분야에 해당하면 각 분야의 다른 관점으로 별도 저장될 수 있습니다.
3. 제목, 저자, 제출일, 초록을 Gemini CLI에 전달하고 한국어 요약을 받습니다. **PDF 전문은 다운로드·분석하지 않습니다.** 한 논문당 한 번의 CLI 작업이며 실제 모델 요청 횟수와 사용량은 CLI에 따라 달라질 수 있습니다.
4. 출처·초록·요약을 `content/분야ID/*.md`에 저장하고 SQLite에 목록과 실행 기록을 기록합니다.

범위 내 검색 결과가 200편을 넘으면 실행 기록에 표시합니다. 최신 후보 200편 밖의 논문까지 전부 수집하지는 않으므로 검색식을 좁히거나 조사 주기/편수를 조정하세요. 최초 제출일 필터이므로 오래된 논문의 최근 개정본은 놓칠 수 있습니다. “Gemini 조사 지침”은 요약에 적용되며 검색식을 자동으로 바꾸지는 않습니다.

성공한 글만 중복 처리합니다. 요약 실패 시 해당 논문은 나중에 다시 시도할 수 있습니다. 한 분야에서 모델 오류가 나면 그 분야의 남은 요약을 중단하며, 이미 저장한 글은 보존합니다. 실패해도 마지막 시도 시점은 기록하여 계속 호출하는 일을 막습니다. 자동 재시도는 다음 주기에 하고 즉시 재시도는 수동 조사로 가능합니다.

예약은 서버 프로세스 내부에서 15초마다 확인하고 시각은 UTC로 저장, 브라우저에서는 로컬 시간대로 표시합니다. 종료·절전 중에는 실행되지 않습니다. 다시 켜면 밀린 횟수만큼 몰아서 실행하지 않고 분야당 한 번 처리합니다. 종료 시 진행 중 요약은 중단될 수 있으며 다음 시작 때 중단 기록으로 표시됩니다. 이 버전에는 Windows 자동 시작/작업 스케줄러 등록이 없습니다.

조사 중복 실행은 프로세스 간 파일 잠금으로 막습니다. 설정을 조사 중에 변경하면 다음 조사부터 적용됩니다. 분야를 제거하거나 ID를 바꿔도 기존 글과 Markdown은 삭제하지 않습니다. 기존 글은 전체 목록에서 계속 볼 수 있습니다.

## 파일 구조

```text
paper-garden/
  start.cmd                 로컬 블로그 실행
  login-gemini.cmd           Gemini 설치·Google 로그인
  app.py                    웹 서버, 다운로드, 정적 내보내기, CLI
  garden.py                 논문 수집, 요약, 중복 방지, 예약
  config.json               분야·주기·조사 지침
  templates/                페이지 템플릿
  static/                   CSS, JavaScript (외부 CDN 없음)
  policies/                 요약용 CLI 인증·도구 제한
  content/<분야ID>/*.md       실제 생성된 글
  data/garden.sqlite3        목록·실행 기록·예약 상태
  data/cli-work/             요약 프로세스 작업 폴더
  site/                     정적 블로그 내보내기 결과
  tests/                    오프라인 자동 테스트
```

Markdown은 JSON 객체 형식의 YAML-compatible frontmatter, 제목, 요약, 출처, 초록으로 구성됩니다. 저장된 `.md`를 편집하면 글 본문과 다음 정적 내보내기에 반영됩니다. 목록의 제목·날짜 메타데이터는 DB 기준이므로 Markdown frontmatter만 수정해서는 목록이 바뀌지 않습니다. 임의로 추가한 Markdown의 자동 인덱싱은 제공하지 않습니다. 백업할 때는 **`config.json`, `content/`, `data/garden.sqlite3`를 함께** 보관하세요.

## 터미널 명령

프로젝트 폴더에서 PowerShell:

```powershell
.\.venv\Scripts\python.exe app.py serve --open
.\.venv\Scripts\python.exe app.py serve --port 8766
.\.venv\Scripts\python.exe app.py check
.\.venv\Scripts\python.exe app.py demo
.\.venv\Scripts\python.exe app.py run --topic ai
.\.venv\Scripts\python.exe app.py run
.\.venv\Scripts\python.exe app.py export
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`check`는 설치·설정만 확인하고 로그인 성공이나 사용 한도는 확인하지 않습니다. 테스트는 가짜 논문과 모의 모델 응답을 사용하며 Google 호출을 하지 않습니다.

선택적인 브라우저 검증은 `requirements-dev.txt`를 설치한 뒤 `python tests/browser_smoke.py`로 실행합니다. Windows의 Microsoft Edge를 사용하며 임시 작업 공간에서 분야 추가·조사·다운로드·내보내기를 검증하고 `data/preview-desktop.png`, `data/preview-mobile.png`에 화면을 저장합니다.

`site/index.html`은 더블클릭으로 읽을 수 있고 분야별 페이지도 상대 경로로 연결됩니다. 정적 내보내기에는 로그인·설정·수집 기능이 없으며 글이 추가된 후 다시 내보내야 반영됩니다. 기존 내보낸 파일은 덮어쓰되 더 이상 목록에 없는 파일은 자동 삭제하지 않습니다. 새 원문 요약은 Git 추적 Markdown에서 읽으므로 SQLite가 없는 GitHub Actions에서도 내보낼 수 있습니다.

## 문제 해결

- **Gemini 실패 / 한도 초과:** `login-gemini.cmd`에서 로그인과 계정을 확인하세요. 사용 한도가 소진되었으면 기다렸다가 다시 실행합니다. 진단 메시지는 실행 기록에 표시하며 인증 정보 유출을 피하려고 CLI stderr 원문은 저장하지 않습니다.
- **논문이 0편:** 검색식, 최초 제출일 기간, 이미 수집한 논문 여부를 확인하세요. 주말·arXiv 반영 지연 때문에 새 글이 없을 수 있습니다.
- **arXiv 연결 오류:** 인터넷·프록시·VPN을 확인하고 재시도하세요. 외부 서비스 장애일 수도 있습니다.
- **포트 사용 중:** `app.py serve --port 8766`처럼 다른 포트를 사용하세요.
- **Python 패키지 오류:** `.venv\Scripts\python.exe -m pip install -r requirements.txt`를 다시 실행하세요.
- **Gemini 설치 오류:** Node.js 20 이상인지 확인하고 `npm.cmd ci --no-audit --no-fund`를 실행하세요.

서버는 `127.0.0.1`에만 열리고, 쓰기 요청에 세션별 토큰을 사용하며 HTML 출력은 정화합니다. 공유 서버 배포용 사용자 인증은 제공하지 않습니다. 기존 UI의 Gemini 요약에는 도구 사용을 차단하고 사용자 훅·MCP·확장 기능을 끄는 프로젝트 전용 설정을 적용합니다. 새 agy 파이프라인의 권장 권한 설정은 아래를 참고하세요.

## 주간 선정·일간 원문 요약 파이프라인

Python 3.12에서 확인했습니다. 기존 `app.py run`은 초록 기반 조사이며, 아래 명령은 별도의 큐와 agy 백엔드를 사용합니다. 작업 스케줄러를 사용할 때 기존 UI의 자동 조사는 필요에 따라 꺼 두세요. 새 파이프라인은 Flask 서버 실행 없이 동작합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# npm 명령의 python이 이 가상환경을 사용하도록 현재 창의 PATH 설정
$env:Path = "$PWD\.venv\Scripts;$env:Path"
agy --help
agy models
agy
```

`agy` 대화형 세션에서 로그인하고 Gemini 모델을 선택합니다. `agy models`에 표시되는 Gemini 모델 ID를 `config.json`의 `pipeline.model`에 넣으면 매 실행에서 고정됩니다. 빈 문자열은 CLI에 설정된 기본 모델을 사용합니다. 인증 토큰은 CLI 자격 증명 저장소에 두고 저장소에 기록하지 않습니다. 기존 `login-gemini.cmd`는 기존 Gemini CLI용이며 agy 로그인과 별개입니다.

첫 실행 전에 파이프라인 전용 파일 작업 폴더의 권한을 설정합니다.

```powershell
.\.venv\Scripts\python.exe -B paper_pipeline.py setup-agy
```

이 명령은 agy 사용자 설정의 기존 값들을 유지하면서 `read_file(<agy_work_dir의 절대 경로>)`와 `write_file(<agy_work_dir의 절대 경로>)`만 추가합니다. 기본 폴더는 `~/.paper-blog/agy-work`이며 저장소 밖입니다. 변경 전 설정은 같은 설정 디렉터리의 `settings.paper-blog-backup.json`으로 보관합니다. 전체 파일 시스템 쓰기나 명령 실행 권한은 허용하지 않습니다. `setup-agy --dry-run`으로 변경 예정 경로만 확인할 수 있습니다.

### 명령과 dry-run

```powershell
npm run paper:weekly
npm run paper:daily
npm run paper:add -- 2609.00001 --note "먼저 읽기"
npm run paper:add -- https://arxiv.org/abs/2609.00001v2
npm run paper:add -- https://eprint.iacr.org/2026/2092
npm run paper:add -- https://example.org/paper.pdf
npm run paper:list
```

동일한 Python 명령은 `python -B paper_pipeline.py weekly|daily|add|list`입니다. `-B`는 Python 바이트코드 캐시 생성을 막습니다. 모든 명령에 `--dry-run`을 사용할 수 있습니다.

외부 서비스·agy·파일 저장 없이 전체 흐름을 확인하려면 아래 fixture 명령을 사용하세요. fixture는 합성 자료이며 실제 논문 결과가 아닙니다. `--fixture`는 `--dry-run`과 함께만 허용합니다.

```powershell
npm run paper:weekly -- --dry-run --fixture tests/fixtures/paper-pipeline.json
npm run paper:daily -- --dry-run --fixture tests/fixtures/paper-pipeline.json
npm run paper:add -- 2609.00001 --note "fixture" --dry-run --fixture tests/fixtures/paper-pipeline.json
npm run paper:list -- --dry-run --fixture tests/fixtures/paper-pipeline.json
```

dry-run은 로그 파일, 큐, 원문 보관본, 임시 LLM 파일, 초안, 게시물, Git을 변경하지 않습니다. 기본 dry-run도 모델 응답과 PDF는 fixture로 대신하며 실제 모델 품질 검증이 아닙니다. `add --dry-run`에 fixture를 주지 않으면 메타데이터만 실제로 조회합니다. `daily --dry-run`의 큐가 비면 정상 종료합니다. 명시적인 fixture가 있으면 빈 큐에 fixture 논문을 **메모리에서만** 넣어 끝까지 검증합니다. 기존 큐에 fixture 밖의 논문이 있으면 섞어서 요약하지 않고 실패합니다. dry-run에서 변경된 큐는 다음 명령에 유지되지 않습니다.

### 설정: 기존 config.json의 pipeline 객체 하나

기존 `title`, `topics`, UI 설정은 유지합니다. UI에서 블로그 설정을 저장해도 `pipeline`은 보존됩니다. 새 필드를 추가하거나 바꿀 때 설정 검증을 통과해야 하며, 알 수 없는 키는 오류입니다.

| 설정 | 기본값 / 의미 |
| --- | --- |
| `keywords`, `arxiv_categories`, `use_eprint` | 관심 키워드, arXiv 범주, ePrint RSS 사용 여부 |
| `topic_filters` | 분야 ID별 키워드 그룹. 그룹 사이는 AND, 그룹 내부는 OR |
| `weekly_new`, `pool_limit`, `expiry_weeks` | 신규 10편, candidate 최대 20편, 만료 3주 |
| `llm_shortlist`, `fetch_limit` | LLM 평가 최대 30편, arXiv API 페이지당 200편 |
| `rank_batch_size` | 요청당 평가할 논문 수, 기본 5편; 각 논문은 독립적으로 스키마 검증 |
| `min_relevance_score` | 관련성 최소 점수, 기본 3/5; 일반 후보에 적용하며 수동 pinned는 제외 |
| `rule_weight`, `llm_weight` | 0.3, 0.7; 각 0~5점 척도의 가중평균 |
| `method_min_chars`, `experiment_min_chars` | 방법론 1200자, 실험 1000자; 헤더 제외 본문 길이 |
| `post_dir`, `category` | `content/ai`, `ai`; category는 기존 topics의 ID |
| `queue_path` | `data/paper-queue.json` |
| `draft_dir`, `archive_dir`, `log_dir` | `drafts`, `data/papers`, `logs` |
| `agy_path`, `model`, `timeout` | `agy`, CLI 기본 모델, 호출당 300초 |
| `agy_work_dir` | `~/.paper-blog/agy-work`; agy에 파일 권한을 허용하는 전용 작업 폴더 |
| `http_timeout`, `max_pdf_bytes` | HTTP 60초, PDF 최대 50 MiB |
| `abstract_mode` | `original`만 지원; 제목·초록은 메타데이터에서 가져옴 |
| `max_quote_words` | 직접 인용 제한 25단어; 원문 초록과 코드가 복사한 참고문헌 제외 |
| `arxiv_api`, `eprint_rss` | arXiv 공개 API, `https://eprint.iacr.org/rss/rss.xml` |

`agy_path`는 작업 스케줄러에서도 찾을 수 있도록 실제 실행 파일의 절대 경로로 지정하는 것을 권장합니다. 예: `C:/Users/<사용자>/AppData/Local/agy/bin/agy.exe`. 사용자명·토큰이 포함된 설정은 커밋 전에 확인하세요. 게시 경로는 `content/` 아래, 초안은 그 밖의 상대 경로여야 합니다. 큐 경로를 바꾸면 `.gitignore`에서도 해당 파일의 추적을 허용해야 합니다.

### 선정·요약·검증 동작

주간 작업은 최근 7일의 arXiv 제출 논문과 ePrint RSS 항목을 읽습니다. arXiv는 페이지를 순회하고 요청 간 3.1초를 둡니다. ePrint RSS는 서버가 제공하는 최신 항목 범위만 수집하므로 제출량이 많으면 최근 일주일 전체가 포함되지 않을 수 있습니다. API 장애는 로그를 남기고 실행을 실패시킵니다.

키워드 일치마다 1점, 범주 일치마다 2점으로 최대 5점을 부여합니다. 양수인 상위 후보만 LLM 평가로 넘깁니다. 관련성·새로움·방법론·재현 가능성의 정수 1~5점 및 근거를 JSON Schema로 검증하며 잘못된 JSON만 1회 재시도합니다. 메타데이터에 코드·데이터 공개 근거가 없으면 추측하지 않도록 지시합니다. 평가를 통과한 신규 상위 후보를 기존 후보와 합치고, 만료→상한 정리→잔존 후보의 대기 주 수 증가 순서로 처리합니다. 같은 로컬 달력 주의 재실행은 중복 노화를 방지하기 위해 건너뜁니다. 화요일에 처음 실행해도 다음 주 월요일 작업은 정상 실행됩니다.

검증을 통과한 개별 평가는 `data/paper-rank-cache.json`에 즉시 원자적으로 저장합니다. 중간에 모델 서비스 오류가 발생하면 큐는 미완료 상태로 유지하고, 다음 실행에서는 메타데이터·검색 관심사·모델·스키마가 같은 평가를 재사용합니다. 쿼터 오류는 자동 재시도하지 않습니다. 캐시는 Git 게시 대상이 아닙니다.

주간 평가는 기본 5편씩 묶어 CLI 실행 횟수를 줄입니다. 응답은 논문 ID별로 검증하며 정상 항목은 저장하고, 잘못된 항목만 한 번 다시 요청합니다. 일간 요약의 A/B/C/D 분리 호출은 그대로 유지합니다.

현재 운영 주제는 **AI CryptAnalysis**와 **AI Digital Forensics**입니다. `topic_filters`가 설정되면 모든 그룹에서 하나 이상의 표현이 일치해야 합니다. 즉 AI 표현과 해당 분야 표현이 함께 있어야 하며 `cs.AI`/`cs.CR` 범주만으로는 통과하지 않습니다. 이 모드에서는 일치 키워드와 범주에 각 1점씩, 최대 5점을 주고 가장 많이 일치한 분야를 선택합니다. arXiv 검색에도 그룹의 AND 조건을 적용하고 ePrint에는 같은 필터를 적용합니다. 후보의 `topic_id`에 따라 `content/ai-cryptanalysis/` 또는 `content/ai-digital-forensics/`에 게시하고 frontmatter `category`도 맞춥니다. 수동 추가 논문은 매칭되는 분야를 사용하며 미일치 시 설정의 기본 `category`를 사용합니다.

`seen`은 과거 큐에 들어간 ID를 영구 보관합니다. arXiv 버전 접미사를 제거하고 출처 접두사를 붙여 중복을 막습니다. 수동 추가는 seen 여부와 관계없이 pinned로 승격하며, 원래 `addedAt` 순서가 FIFO 기준입니다. pinned는 정리 대상에서 제외합니다. done·failed·expired는 일간 선택에서 제외됩니다. failed를 다시 시도하려면 `paper:add`로 승격합니다. 이미 게시된 파일은 덮어쓰지 않습니다.

일간 작업은 pinned→최고 점수 candidate 순서로 한 편을 선택합니다. PDF는 PyMuPDF4LLM으로 표와 텍스트를 Markdown으로 변환하고, 그림 저장·임베딩은 끕니다. 변환 Markdown과 일반 텍스트는 `data/papers/<해시>/source.md`, `source.txt`에 보관합니다. PDF 수식의 추출 품질은 원문 인코딩에 따라 제한되며, 스캔 PDF의 OCR은 제공하지 않습니다. 임의 PDF URL은 내장 메타데이터를 우선하고 제목이 없으면 첫 추출 행을 사용합니다. 추출된 초록이 없으면 큐에는 넣되 일간 필수 초록 검증에서 게시를 차단합니다. 이 경우 arXiv/ePrint 페이지 URL 사용을 권장합니다.

LLM은 A(필요성·흐름·관련 연구·배경·문제·기여), B(방법론), C(실험), D(고찰·결론)를 별도 호출합니다. 코드가 필수 헤더, 방법론·실험 길이, 실험 수치의 원문 존재, 원문/PDF 링크, frontmatter 필드·날짜·출처를 검증합니다. 없는 수치는 리포트에 나열하며 콤마·공백·퍼센트와 소수 표기를 정규화합니다. 실패한 그룹만 사유를 주어 1회 재생성합니다. 원문에 필수 내용이 없는 이론 논문 등은 내용을 꾸며 채우지 않고 실패 초안으로 남을 수 있습니다. 선택 섹션은 없어도 됩니다.

References/Bibliography의 `[번호]` 또는 `번호.` 항목을 코드로 분리하고, LLM은 사용할 번호의 JSON 배열만 선택합니다. 서지 문자열은 원문 추출 텍스트 그대로 복사합니다. 번호가 없는 저자-연도 방식이나 모호한 번호는 임의로 복원하지 않고 참고문헌을 생략합니다.

최종 실패는 `drafts/<파일명>.md`와 `.validation.json`에 남기고 `failCount` 증가·`failed` 처리합니다. 실패 실행은 비정상 종료하며 Git을 실행하지 않습니다. 429/RESOURCE_EXHAUSTED 등 쿼터 오류는 즉시 중단하고 candidate/pinned 상태를 유지하므로 다음 실행에서 재시도할 수 있습니다. 검증은 구조와 수치 출처를 검사하며, 수치가 같은 실험을 가리키는지 또는 해석이 타당한지까지 증명하지는 않습니다.

### Git·Pages와 복구

현재 제공된 작업 폴더에는 `.git`이 없었습니다. 실제 운영은 Git 저장소에서 수행하고 먼저 코드·설정·워크플로를 초기 커밋하여 업스트림을 연결해야 합니다. Git 자격 증명은 Git Credential Manager 등 저장소 외부에서 관리합니다. GitHub 저장소 Settings → Pages에서 Source를 **GitHub Actions**로 설정하세요. `.github/workflows/pages.yml`은 main/master의 push에서 기존 `app.py export`로 생성한 `site/`를 배포합니다. 다른 기본 브랜치는 워크플로의 branches를 수정하세요.

검증을 통과한 **새 게시물과 큐 파일만** 명시적 경로로 stage/commit합니다. 기존 index에 staged 변경이 있으면 건드리지 않고 중단합니다. `git add -A`와 force push는 사용하지 않습니다. 커밋 메시지는 `post: [논문 요약] <제목 일부>`이고 푸시는 `git push`입니다. 주간/수동 추가는 큐를 원자적으로 저장하며 다음 성공한 일간 게시 커밋에 포함됩니다.

게시 트랜잭션은 Git에서 제외한 `data/paper-publish-pending.json`에 먼저 기록합니다. 커밋/푸시 실패 시 유지하고 다음 비 dry-run 변경 명령에서 먼저 복구합니다. 이미 커밋된 내용을 중복 커밋하지 않으며, 복구한 실행은 추가 논문을 게시하지 않습니다. 큐를 수동 편집하거나 이 파일을 삭제하기 전에 pending 작업부터 해결하세요. 다른 로컬 커밋도 일반 `git push` 대상이므로 운영 브랜치를 전용으로 사용하는 것이 좋습니다. 공유 작업 폴더의 동시 실행은 FileLock으로 차단합니다.

로그는 PC 로컬 날짜 기준 `logs/YYYY-MM-DD.log`에 저장하고 각 행의 시각은 UTC입니다. CLI stdout/stderr 원문이나 인증 정보는 로그에 저장하지 않습니다. 큐를 제외한 `data/`, 초안, 로그, 정적 빌드 결과는 Git에서 제외합니다.

### agy 확인한 사용법과 권장 deny 설정

2026-09-22 이 PC의 `agy --help`로 `--print`, `--sandbox`, `--disable-slash-commands`, `--print-timeout`, `--model`을 확인했습니다. 어댑터는 대략 다음 방식으로 호출합니다.

```text
agy --print "Read <absolute prompt path> ... write <absolute result path> ..." --sandbox --disable-slash-commands --output-format json --print-timeout 300s
```

출력 파일 전용 플래그는 확인되지 않았습니다. `agy_work_dir` 아래 호출마다 고유 디렉터리에 `prompt.txt`를 만들고 파일 도구로 `result.txt`에 답변을 쓰게 한 뒤 읽습니다. 모든 파일 경로를 절대 경로로 전달합니다. 비TTY stdout이 비어도 동작하며, 파일이 없으면 stdout으로 대체하지 않고 실패합니다. stdout JSON은 `denied_actions` 및 상태 진단에만 사용합니다. agy가 종료 코드 0과 `SUCCESS`를 반환해도 파일 읽기·쓰기 도구를 거부할 수 있으며, 이 경우 `setup-agy` 실행을 안내합니다. timeout이나 쿼터 감지 시 하위 프로세스도 종료합니다. `generate(prompt, options) -> str` 인터페이스 뒤에 감췄으므로 나중에 API 키 백엔드로 교체할 수 있습니다.

print 모드의 도구 자동 승인 여부는 버전·권한 설정에 따라 다릅니다. 현재 공식 문서는 workspace 파일 쓰기의 자동 허용과, 별도 승인 없는 명령의 soft-deny를 설명하지만 실제 Windows 실행에서는 명시적인 파일 권한이 필요했습니다. `setup-agy`가 추가하는 전용 폴더 allow 규칙은 유지하면서 아래 예시의 deny 규칙을 기존 permissions에 병합할 수 있습니다. **weekly/daily는 사용자 권한 설정을 변경하지 않습니다.** 명령 도구 전체를 막으면 `rm`, `del`, `Remove-Item`, `git push`도 차단됩니다. 이 작업은 파일 읽기/쓰기 도구만 필요합니다.

```json
{
  "permissions": {
    "deny": [
      "command(*)",
      "unsandboxed(*)",
      "mcp(*)",
      "read_url(*)",
      "execute_url(*)",
      "write_file(.git/)"
    ],
    "allow": [],
    "ask": []
  }
}
```

이 전역 예시는 다른 agy 작업의 명령 실행도 막습니다. 전용 Windows 계정으로 운영하면 설정을 분리할 수 있습니다. `--dangerously-skip-permissions`는 어댑터에서 사용하지 않습니다. 격리 디렉터리와 프롬프트만으로 OS 수준의 완전한 격리를 보장하지 않으므로 실제 설치 버전의 권한 적용 여부를 확인하세요. [공식 headless 문서](https://antigravity.google/docs/cli/headless), [권한 문서](https://antigravity.google/docs/permissions).

### Windows 작업 스케줄러

```powershell
# 등록 전 확인
.\scripts\register-paper-tasks.ps1 -WhatIf
# 매주 월요일 08:00 선정, 매일 09:00 게시 (Windows 로컬 시간)
.\scripts\register-paper-tasks.ps1 -WeeklyDay Monday -WeeklyTime '08:00' -DailyTime '09:00'
# Python 경로를 직접 지정할 수도 있음
.\scripts\register-paper-tasks.ps1 -PythonPath 'E:\paper-garden\.venv\Scripts\python.exe'
```

같은 이름의 작업은 갱신됩니다. 등록 스크립트는 현재 사용자·일반 권한·로그온한 세션에서 실행하도록 구성합니다. 화면 잠금은 가능하지만 로그아웃하면 실행되지 않습니다. PC와 해당 사용자 세션을 유지해야 하며, agy 인증과 Git 인증도 같은 계정에서 완료하세요. 비밀번호를 스크립트에 넣지 않습니다. 놓친 작업은 다음 가능한 시점에 실행하고, 중복 인스턴스는 건너뜁니다. 작업 실행 시간 상한은 6시간입니다. 서로 다른 weekly/daily 작업이 겹치면 프로세스 잠금으로 한쪽을 중단하므로 충분한 간격을 설정하세요.

### 테스트와 구현 기준

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

테스트는 agy를 호출하지 않습니다. 큐 정렬·상한·만료·FIFO·seen, 필수/선택 헤더, 수치 정규화·링크·frontmatter, 참고문헌 복사, 잘못된 JSON 재시도, 그룹별 재생성, quota/timeout, 실제 합성 PDF 변환, 파일 없는 stdout 처리, dry-run 무쓰기, 기존 UI 설정 보존, SQLite 없는 정적 내보내기를 검증합니다. 임시 로컬 Git 저장소와 bare remote로 stage 범위·푸시 실패·커밋 직후 중단 복구도 검증합니다.

Python 모듈은 기존 루트 배치와 `unittest` 관례를 따릅니다. `garden.atomic_write`, UTC 시각, 설정 로딩, arXiv 파서를 재사용합니다. 파일명은 기존 날짜+20자리 해시 규칙이며 fulltext 구분자를 해시에 넣어 기존 초록 글과 충돌을 피합니다. frontmatter 필드는 기존과 동일하게 유지하고 `basis` 값만 `fulltext`로 구분합니다. ePrint/manual은 `arxiv_id`를 빈 문자열로 유지하고 `source`에 해당 원문 링크를 기록합니다. [참고 구현](https://github.com/suanlab/suanlab.com/blob/master/scripts/blog/paper-summarizer.ts)의 메타데이터→PDF→파싱→요약→저장 흐름만 참고했고 Claude 호출부는 사용하지 않았습니다. [PyMuPDF4LLM API](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html).

### 중단된 초안 복구

참고문헌 선택 등에서 중단된 논문은 `paper_pipeline.py add <ID>`로 다시 고정한 뒤 `paper_pipeline.py daily --resume-draft`로 재개할 수 있습니다. 저장된 초안의 제목·원문 링크를 확인하고 PDF를 다시 읽어 각 섹션의 구조·길이·수치·인용 제한을 재검증합니다. 통과한 그룹만 재사용하며 실패한 그룹은 기존 생성·재시도 규칙을 따릅니다. 마지막 전체 문서 검증과 Git 게시 절차도 그대로 적용합니다.
