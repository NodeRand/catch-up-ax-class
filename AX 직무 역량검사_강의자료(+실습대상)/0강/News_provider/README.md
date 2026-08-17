# 일일 뉴스 브리핑 (News Brief)

매일 아침 07:00, 지난 24시간의 주요 뉴스를 4개 관심 카테고리로 정리해 이메일로 보냅니다.

- **관심 카테고리**: 🎓 대학입시 · 🤖 AI 기술·업체 동향 · 🧑‍💼 취업시장·플랫폼 · 💻 IT 일반
- **수집 소스**: 언론사/GeekNews RSS · 구글뉴스 키워드 RSS · Hacker News · Reddit
- **분류·요약**: Gemini API · **발송**: Gmail SMTP

## 파이프라인

```
수집(RSS·HN·Reddit·구글뉴스) → 분류(키워드+Gemini) → 중복제거 → 요약(Gemini) → HTML 렌더 → Gmail 발송
```

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate          # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 설정

1. `.env.example` 를 `.env` 로 복사하고 값 입력:
   - `GEMINI_API_KEY` — https://aistudio.google.com/apikey 에서 발급
   - `EMAIL_USER` / `EMAIL_APP_PASSWORD` — Gmail 계정 + **앱 비밀번호**
     (Gmail → 계정 → 보안 → 2단계 인증 → 앱 비밀번호)
   - `EMAIL_TO` — 받는 사람 (쉼표로 여러 명)
   - `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` *(선택)* — https://www.reddit.com/prefs/apps
     에서 "script" 앱 생성. 있으면 upvote 점수 포함 정밀 수집, 없으면 RSS 폴백.
2. 소스/카테고리/임계값은 `config/*.yaml` 에서 조정.

### 발송 이력 (중복 방지)

발송한 기사 URL 은 `data/archive.db`(SQLite)에 기록되어, 같은 사건이 며칠에 걸쳐
반복 노출되는 것을 막습니다. 이력은 14일 후 자동 정리됩니다. `--dry-run` 은 이력을
조회만 하고 기록하지 않습니다.

## 실행

```bash
python -m newsbrief.main --dry-run    # 메일 발송 없이 out/briefing.html 로 미리보기
python -m newsbrief.main --no-llm     # Gemini 없이 키워드 규칙만으로 동작 확인
python -m newsbrief.main              # 실제 발송
```

## 매일 07:00 자동 실행 (Windows 작업 스케줄러)

PowerShell(관리자)에서 — 경로는 실제 환경에 맞게 수정:

```powershell
schtasks /Create /SC DAILY /ST 07:00 /TN "NewsBrief" `
  /TR "cmd /c cd /d C:\Git\News_provider && .venv\Scripts\python.exe -m newsbrief.main >> logs\run.log 2>&1"
```

확인: `schtasks /Query /TN "NewsBrief"` · 즉시 실행: `schtasks /Run /TN "NewsBrief"`

## 비용/품질 메모

- 분류는 제목+스니펫만, 요약은 카테고리별 상위 N건만 LLM 호출 → 호출량 최소화.
- 영어 소스(HN/Reddit)는 요약 시 한국어로 번역.
- 커뮤니티 점수(HN points / Reddit upvotes)를 중요도에 반영해 트렌드 상위만 노출.

## 주의

- 언론사 RSS URL 은 사이트 개편 시 바뀔 수 있습니다. 특정 소스가 0건이면 `config/sources.yaml` 의 URL 을 점검하세요. (구글뉴스 RSS 는 비교적 안정적)
- Threads/Instagram/X 는 트렌드 파악 목적상 HN·Reddit·언론사로 충분히 커버되며, 자동 수집은 약관·안정성 문제로 제외했습니다.
