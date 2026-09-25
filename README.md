# Paper Blog

AI와 보안 분야의 논문을 모아 한국어로 정리하는 개인 연구 블로그입니다. **AI 기반 암호분석**과 **AI 기반 디지털 포렌식**을 중심으로, 관심 있는 연구의 핵심을 빠르게 파악하고 원문을 다시 찾아 읽을 수 있도록 기록합니다.

원문 기반 정리는 한국어 초록 번역, 문제 정의와 핵심 기여, 방법론, 실험 결과, 한계와 결론을 담습니다. 목록에서는 짧은 주제 요약과 게재처·출처, 정리 모델, 정리 날짜를 확인할 수 있습니다. 저널·학회 정보는 원문 메타데이터를 사용하며, 게재 정보가 확인되지 않으면 arXiv·IACR ePrint 출처를 표시합니다. 모델명은 CLI가 반환한 실제 모델 ID를 기록하고, 과거 버전 정보가 없는 글은 미기록으로 표시합니다.

글은 Markdown으로 저장하고 GitHub Pages로 게시합니다. AI가 정리한 내용이므로 중요한 해석과 수치는 함께 제공하는 원문·PDF 링크에서 확인하세요.

[블로그 둘러보기](https://youngjin0305.github.io/paper-blog/)

## 시작하기

아래 명령은 **Windows PowerShell에서 프로젝트 폴더를 연 상태**로 실행합니다.

1. Python과 Git, 사용할 모델의 CLI를 설치합니다. Gemini 웹 조사에는 Node.js도 필요합니다.
2. `start.cmd`를 실행합니다. 가상환경이 없으면 Python 의존성을 설치하고, 로컬 관리 화면을 엽니다: **http://127.0.0.1:8765**.
3. 사용할 CLI에 같은 Windows 계정으로 로그인합니다. Claude는 `claude`, Codex는 `codex login`을 실행합니다.
4. **설정** 화면에서 모델과 관심 분야를 지정합니다.

공개 GitHub Pages는 읽기 전용입니다. 설정과 실행 관리는 로컬에서 합니다. 자동 게시를 사용하려면 Git 원격 저장소·업스트림과 푸시 인증을 준비하고, GitHub 저장소의 **Settings → Pages → Source**를 **GitHub Actions**로 설정하세요.

## 논문 한 편 수동으로 정리하기

원하는 논문을 대기 목록에 추가한 뒤, 다음 한 편을 처리합니다. 아래 arXiv ID는 정리할 논문의 ID로 바꾸세요.

```powershell
# 1. 원하는 논문 추가 — arXiv ID 또는 원문 URL
.\.venv\Scripts\python.exe -B paper_pipeline.py add 2609.24359 --note "관심 논문"

# 2. 처리 순서 확인
.\.venv\Scripts\python.exe -B paper_pipeline.py list

# 3. 다음 한 편 정리 — 초안이 있으면 검증 후 재사용
.\.venv\Scripts\python.exe -u -B paper_pipeline.py daily --resume-draft
```

`add`에는 arXiv 페이지, `https://eprint.iacr.org/연도/번호` 형식의 ePrint 페이지, 공개 HTTPS PDF URL도 사용할 수 있습니다. `--note`는 관리용 메모이며 요약 지침을 바꾸지는 않습니다.

**`daily`는 목록의 첫 번째 논문 한 편을 처리합니다.** 수동 추가한 `pinned` 논문이 일반 후보보다 우선이고, pinned끼리는 최초 추가 시각 순서입니다. 다른 pinned가 있으면 방금 추가한 논문보다 먼저 처리될 수 있으므로 `list`로 확인하세요. 이미 게시한 논문은 다시 추가해도 기존 글을 덮어쓰지 않습니다.

원문 다운로드 → 한국어 정리 → 구조·수치·인용 검증을 거쳐, **성공하면 새 글과 대기 목록을 자동으로 커밋·푸시**합니다. GitHub Actions 배포가 끝나면 공개 블로그에 반영됩니다. 검증 실패 시에는 게시하지 않고 초안과 오류를 남깁니다.

로컬 화면의 **지금 논문 조사하기**는 arXiv **초록 기반 조사**입니다. PDF 전문을 읽는 위 명령의 원문 기반 정리와 별도로 동작하며, 웹 조사만으로 GitHub에 자동 푸시하지는 않습니다.

## 모델 바꾸기

설정 화면의 **AI 모델** 또는 `config.json`의 최상위 `model`을 바꿉니다.

| 설정 예시 | 사용 모델 |
| --- | --- |
| `claude/opus` | Claude CLI의 Opus 별칭 |
| `claude/sonnet` | Claude CLI의 Sonnet 별칭 |
| `claude/claude-opus-5` | 해당 계정에서 사용 가능한 경우 Opus 5 명시 지정 |
| `codex` 또는 `codex/모델ID` | Codex CLI의 기본 모델 또는 지정 모델 |
| `gemini-3.8-flash-high` | Gemini 계열 모델 지정 |

현재 저장된 설정은 `claude/opus`이며, 모델 설정을 비우면 앱의 기본 Gemini 모델을 사용합니다. 별칭이 가리키는 버전은 바뀔 수 있으므로 게시글에는 응답에서 확인한 실제 모델명을 남깁니다.

`pipeline.model`이 빈 문자열이면 최상위 모델 설정을 따릅니다. 원문 기반 정리만 다른 모델을 쓰고 싶으면 여기에 별도로 지정하세요. 예약 작업에서 CLI를 찾지 못하면 `pipeline.claude_path`, `pipeline.codex_path`, `pipeline.agy_path`에 실행 파일의 절대 경로를 지정할 수 있습니다.

Gemini는 웹 조사에서 `login-gemini.cmd`로 로그인하고, 원문 기반 정리에서는 별도의 Antigravity CLI(`agy`) 로그인이 필요합니다. Gemini 파이프라인을 처음 사용할 때만 다음 명령으로 전용 작업 폴더 권한을 설정합니다. Claude·Codex에는 필요하지 않습니다.

```powershell
.\.venv\Scripts\python.exe -B paper_pipeline.py setup-agy
```

## 대기 목록과 실패 작업 관리

| 작업 | 방법 |
| --- | --- |
| 최근 논문 수집·평가 | `.\.venv\Scripts\python.exe -B paper_pipeline.py weekly` |
| 처리할 목록 확인 | `.\.venv\Scripts\python.exe -B paper_pipeline.py list` |
| 다음 한 편 처리 | `.\.venv\Scripts\python.exe -u -B paper_pipeline.py daily --resume-draft` |
| 실패한 논문 재시도 | 해당 ID로 `add`를 다시 실행한 뒤 `daily --resume-draft` |
| 사용량 제한 후 재개 | 모델을 변경하거나 한도 회복 후 `daily --resume-draft` |

`weekly`는 후보를 수집·평가하고 목록에 넣으며 글을 게시하지 않습니다. 같은 주에 완료된 작업은 중복 실행을 건너뜁니다. `list`는 처리 대상만 보여주고, 전체 상태는 `data/paper-queue.json`에서 확인할 수 있습니다: `pinned`는 수동 지정, `candidate`는 일반 후보, `done`은 완료, `failed`는 실패, `expired`는 제외된 후보입니다.

실패 원인은 `logs/`와 `drafts/*.validation.json`에서 확인하세요. 사용량 제한은 자동으로 반복 요청하지 않으며 대기 상태를 유지합니다. `failed` 상태는 재추가해야 다시 처리됩니다. 게시 도중 커밋·푸시가 중단되면 다음 변경 명령이 먼저 미완료 게시를 복구하고 종료하므로, 새 논문을 처리하려면 복구 완료 후 다시 실행하세요. 복구 중에는 `data/paper-publish-pending.json`을 삭제하거나 대기 목록을 수정하지 마세요.

## 글 수정과 자동 실행

게시글은 `content/<분야>/`의 Markdown을 수정하면 됩니다. `## 한눈에 보기`는 목록 요약, `## 초록`은 한국어 초록입니다. 수정 후 정적 페이지를 로컬에서 확인할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -B app.py export
```

생성된 `site/index.html`을 브라우저로 열어 확인합니다. `export`는 로컬 파일만 만들므로, 공개 블로그에 반영하려면 수정한 원본 Markdown이나 코드를 커밋·푸시하세요. `site/` 자체는 커밋하지 않습니다.

Windows 작업 스케줄러에 주간 후보 선정과 일간 한 편 정리를 등록할 수도 있습니다.

```powershell
# 등록 내용 미리 확인
.\scripts\register-paper-tasks.ps1 -WhatIf

# 매주 월요일 08:00 후보 선정, 매일 09:00 한 편 정리
.\scripts\register-paper-tasks.ps1 -WeeklyDay Monday -WeeklyTime '08:00' -DailyTime '09:00'

# 자동 실행 일시 중지
Disable-ScheduledTask -TaskName 'PaperBlog-weekly'
Disable-ScheduledTask -TaskName 'PaperBlog-daily'
```

시간은 Windows 로컬 시간 기준입니다. PC가 켜져 있고 등록한 사용자가 로그인한 상태여야 하며, 해당 계정의 모델 CLI와 Git 인증이 필요합니다. 다시 켜려면 위 두 작업에 `Enable-ScheduledTask`를 사용하세요. 로컬 웹 설정의 자동 조사는 별도의 초록 조사 기능입니다.

## 보관할 파일

| 위치 | 내용 |
| --- | --- |
| `config.json` | 모델·관심 분야·파이프라인 설정 |
| `content/` | 게시글 Markdown과 글별 메타데이터 |
| `data/paper-queue.json` | 논문 대기 목록과 처리 상태 |
| `data/garden.sqlite3` | 로컬 웹 조사 글의 인덱스와 실행 기록 |
| `drafts/`, `logs/`, `data/papers/` | 실패 초안·오류 기록·추출한 원문 |

백업할 때는 설정, 게시글, 대기 목록, 로컬 DB를 함께 보관하세요. 파이프라인 게시 전에는 다른 작업의 staged 변경이 없어야 합니다. 관리 중 코드 변경을 확인하려면 아래 테스트를 실행합니다. 실제 모델은 호출하지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```
