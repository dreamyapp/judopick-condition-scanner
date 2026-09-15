# 주도픽 조건검색

큰 글씨와 단순한 동선으로 만든 키움 REST API 조건검색 실행기입니다. 기존 주도픽과 분리된 독립 프로젝트이며, 원본 주도픽 파일을 수정하지 않습니다.

## 현재 제공 기능

- 처음 실행 시 사용자 본인의 키움 REST API 키 연결
- 앱 안에서 바로 보는 큰 글씨의 단계별 API 키 발급 가이드
- 키움 공식 발급 화면 이미지와 공식 홈페이지 바로가기
- 다운로드 폴더에서 App Key와 App Secret 파일 자동 찾기 및 연결
- 자동 검색이 어려울 때 키 파일 2개 직접 선택

- 조건식 추가·수정·삭제 및 자동 저장
- 현재가, 등락률, 거래량, 거래대금, 시가총액 조건
- 코스피·코스닥 선택과 ETF·ETN·스팩 등 제외
- 전체 한글 조건식 붙여넣기 및 해석 내용 확인
- 조건식 복사와 다른 사용자에게 공유
- 영웅문에 저장된 조건식 목록 불러오기 및 단발 검색
- 키움 App Key·Secret Key 설정과 연결 확인
- 조건검색 중 진행률과 쉬운 오류 안내
- Windows·macOS 실행기 빌드 구성

## 내려받기

설치 파일은 GitHub의 최신 릴리스에서 받을 수 있습니다.

- Windows 10/11 64비트: `Judopick-ConditionScanner-Windows-x64-Setup.exe`
- Apple Silicon Mac(M1 이후): `Judopick-ConditionScanner-macOS-arm64.dmg`

처음 실행하면 사용자가 본인의 키움 REST API App Key와 App Secret을 연결합니다. 설치 파일에는 주도픽이나 개발자의 API 키가 들어 있지 않습니다.

## 개발 실행

```bash
cd condition_search_tool
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python desktop.py
```

개발 상태에서는 이 폴더의 `.env`를 먼저 읽고, 없으면 한 단계 위 주도픽 루트의 `.env`를 읽습니다. 배포 앱에는 실제 키가 포함되지 않으며 각 사용자가 자신의 키를 최초 한 번 입력합니다.

브라우저로 화면만 확인하려면 `python app.py` 실행 후 `http://127.0.0.1:5217`을 엽니다.

## 조건식 붙여넣기 예시

```text
조건식명: 거래량 급증주
시장: 코스피, 코스닥
등락률: 3% 이상
현재가: 1만원 이상 5만원 이하
거래대금: 100억 원 이상
제외: ETF, ETN, 스팩
```

지원하지 않는 문장은 무시하지 않고 화면에 경고합니다. 검색 전에 앱이 이해한 조건을 사용자가 확인할 수 있습니다.

## 실행기 만들기

macOS에서:

```bash
bash build_macos.sh
```

Windows에서:

```bat
build_windows.bat
```

Windows 빌드에는 [Inno Setup 6](https://jrsoftware.org/isdl.php)이 필요합니다. 운영체제별 빌드는 해당 운영체제에서 실행해야 합니다. 결과물은 `dist` 폴더에 생성됩니다. 공개 배포 시에는 macOS 코드 서명·공증과 Windows 코드 서명을 권장합니다.

GitHub의 `Windows 설치 파일 만들기` 작업을 실행하면 실제 Windows 빌드 컴퓨터에서 자동 테스트 후 설치 프로그램을 만들고 지정한 릴리스에 올립니다.

## 보안

- `.env`, 사용자 키, 접근 토큰, 로컬 DB는 Git에서 제외됩니다.
- 설치형 앱에서는 키를 macOS 키체인 또는 Windows 자격 증명 관리자에 저장합니다.
- 운영체제 보안 저장소를 사용할 수 없는 환경에서만 사용자 데이터 폴더의 권한 제한 파일로 대체합니다.
- 개발용 상위 폴더의 키는 빌드 파일에 포함되지 않습니다.

## 테스트

```bash
pytest -q
```

이 도구는 조회 전용입니다. 주문 API는 포함하지 않습니다.
