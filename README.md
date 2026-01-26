# 📧 Email Crawler

채용 사이트(사람인, 잡코리아, 원티드)에서 기업 정보를 검색하고 홈페이지를 방문하여 담당자 이메일을 자동으로 수집하는 웹 크롤러입니다.

## ✨ 기능

- **멀티 소스 지원**: 사람인, 잡코리아, 원티드 3사 크롤링 지원
- **이메일 자동 추출**: 기업 홈페이지 탐색 후 연락처(이메일) 자동 수집
- **실시간 내보내기**:
  - 📥 CSV 파일 다운로드
  - 📊 **Google Sheets(구글 시트) 바로 저장**

## 🛠️ 기술 스택

- **Backend**: Python, FastAPI
- **Frontend**: HTML5, CSS3, Vanilla JS
- **Crawling**: 
  - `httpx` (비동기 HTTP 요청)
  - `BeautifulSoup4` (HTML 파싱)
  - `Playwright` (동적 페이지 처리)
- **Integration**: `gspread` (Google Sheets API)

## 🚀 실행 방법

### 1. 의존성 설치

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 서버 실행

```bash
python server.py
```

### 3. 접속

브라우저에서 `http://localhost:8000` 접속

## 📊 구글 시트 연동 설정 (Google Sheets)

구글 시트로 데이터를 바로 내보내려면 **Google Cloud Service Account** 설정이 필요합니다.

### 1. 구글 서비스 계정 키 발급
1. [Google Cloud Console](https://console.cloud.google.com/) 접속 및 프로젝트 생성
2. **"Google Sheets API"** 검색 후 [사용(Enable)] 클릭
3. **IAM 및 관리자 > 서비스 계정** 메뉴 이동
4. [+ 서비스 계정 만들기] 클릭하여 계정 생성
5. 생성된 계정 클릭 > **[키]** 탭 > [키 추가] > **[새 키 만들기] (JSON)**
6. 다운로드된 JSON 파일 보관

### 2. 환경 변수 설정
다운로드 받은 JSON 파일의 **내용 전체**를 환경 변수로 등록해야 합니다.

- **변수명**: `GOOGLE_CREDENTIALS_JSON`
- **값**: `{"type": "service_account", ...}` (JSON 파일 내용 전체)

> **Railway 배포 시**: Variables 탭에서 위 변수를 추가하면 됩니다.

### 3. 시트 공유
1. 데이터를 저장할 구글 시트 생성
2. 크롤러의 [구글 시트] 버튼 클릭 시 나오는 **봇 이메일** 복사
3. 구글 시트의 **[공유]** 버튼 클릭 후 봇 이메일을 **'편집자'**로 추가

## 📁 프로젝트 구조

```
email/
├── server.py           # FastAPI 서버 메인
├── requirements.txt    # 의존성 목록
├── crawlers/           # 크롤러 모듈
│   ├── base.py         # 베이스 클래스
│   ├── saramin.py      # 사람인 크롤러
│   ├── jobkorea.py     # 잡코리아 크롤러
│   ├── wanted.py       # 원티드 크롤러
│   └── email_extractor.py # 이메일 추출 로직
├── utils/
│   └── google_sheets.py # 구글 시트 연동 유틸리티
└── static/             # 프론트엔드 리소스
    ├── index.html
    ├── style.css
    └── app.js
```

## 📝 License

MIT License
