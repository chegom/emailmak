# 📧 Email Crawler

사람인(Saramin)에서 기업 정보를 검색하고 이메일을 추출하는 웹 크롤러입니다.

## ✨ 기능

- 🔍 사람인 기업 검색
- 🏢 기업 홈페이지에서 이메일 자동 추출
- 🌐 웹 기반 인터페이스
- 📋 결과 목록 표시

## 🛠️ 기술 스택

- **Backend**: Python, FastAPI
- **Frontend**: HTML, CSS, JavaScript
- **Crawler**: Playwright

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

## 📁 프로젝트 구조

```
email/
├── server.py           # FastAPI 서버
├── requirements.txt    # Python 의존성
├── crawlers/
│   ├── base.py         # 크롤러 베이스 클래스
│   ├── saramin.py      # 사람인 크롤러
│   └── email_extractor.py  # 이메일 추출기
└── static/
    ├── index.html      # 웹 인터페이스
    ├── style.css       # 스타일
    └── app.js          # 프론트엔드 로직
```

## 📝 License

MIT License
