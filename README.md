# 주도픽 조건검색

큰 글씨와 단순한 동선으로 만든 키움 REST API 조건검색 실행기입니다. 기존 주도픽과 분리된 독립 프로젝트이며, 원본 주도픽 파일을 수정하지 않습니다.

## 현재 제공 기능

- 처음 실행 시 사용자 본인의 키움 REST API 키 연결
- 앱 안에서 바로 보는 큰 글씨의 단계별 API 키 발급 가이드
- 키움 공식 발급 화면 이미지와 공식 홈페이지 바로가기
- 다운로드 폴더에서 App Key와 App Secret 파일 자동 찾기 및 연결
- 자동 검색이 어려울 때 키 파일 2개 직접 선택

- 조건식 추가·수정·삭제 및 자동 저장
- 수식과 함께 쓰는 선택형 현재가·등락률·거래량·거래대금·시가총액 필터
- 코스피·코스닥 선택과 ETF·ETN·스팩 등 제외
- 사용자 정의 차트 수식 전체 붙여넣기, 별도 일봉·분봉 선택, 최근 봉 신호 검색
- 앱 안의 맥·윈도우 다운로드 링크 복사 버튼
- 조건식 복사와 다른 사용자에게 공유
- 영웅문에 저장된 조건식 목록 불러오기 및 단발 검색
- 키움 App Key·Secret Key 설정과 연결 확인
- 조건검색 중 진행률과 쉬운 오류 안내
- 완료된 종목 목록을 100개씩 표시하고, 앱을 다시 열어도 마지막 결과 복원
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

## 수식과 추가 필터

```text
A=MA(C,20);
C>A && C(1)<=A(1)
```

새 조건식에는 수식을 통째로 붙여넣고 차트 봉을 선택합니다. 추가 필터는 기본값이 없으며, 필요할 때만 `필터 추가`를 누릅니다. 예를 들어 `시가총액 1,000억 원 이상`을 추가하면 수식 신호와 이 필터를 모두 만족하는 종목만 결과에 나옵니다. 필터는 각 행의 `×`로 삭제할 수 있습니다. 시가총액·거래대금 등은 조회 시점의 종목 정보로 확인하고, 수식은 선택한 차트 봉으로 계산합니다.

세미콜론으로 계산식을 나누고 마지막에는 신호식을 입력합니다. 이전 봉은 `C(1)` 또는 `REF(C,1)`로 표시합니다. 이전 버전에서 만든 필터 전용 조건식은 삭제하지 않고 계속 읽을 수 있습니다.

사용 가능 항목: `O` 시가, `H` 고가, `L` 저가, `C` 종가, `V` 거래량, `DATE` 날짜, `TIME` 시각. 사용 가능 함수: `IF`, `SUM`, `MA`/`AVG`, `EMA`, `HHV`, `LLV`, `ABS`, `MAX`, `MIN`, `REF`, `VALUEWHEN`, `CROSS`, `CROSSUP`, `CROSSDOWN`. `&&`, `||`, `!` 및 비교·사칙연산을 지원합니다. 지원하지 않는 문법·함수는 검색 전에 오류로 알려 줍니다. 영웅문의 모든 함수와 100% 동일한 계산을 보장하는 범용 해석기는 아니며, 수식은 프로그램 코드로 실행하지 않습니다.

수식은 영웅문 저장 조건식과 별개이며, 키움 `ka10080` 분봉 또는 `ka10081` 일봉 데이터를 앱 안에서 계산합니다. 종목별 차트 조회가 필요하므로 전 종목 검색은 몇 분 이상 걸릴 수 있고, 종목마다 조회 시각이 달라 장중 결과가 변동할 수 있습니다. 최신 봉은 진행 중일 수도 있습니다.

```text
TP=(H+L+C)/3;
P=TP/1000;
W0=V/100000000;
CW=Sum(W0);
CP=Sum(P*W0);
NEW=DATE!=DATE(1);
BW=ValueWhen(1,NEW,CW(1));
BP=ValueWhen(1,NEW,CP(1));
W=CW-BW;
PW=CP-BP;
VW=IF(W==0,0,(PW/W)*1000);
UP=VW>VW(1);
BRK=C(1)<=VW(1) && C>VW;
SUP=C(1)>VW(1) && L<=VW && C>VW;
SIG=NEW==0 && VW>0 && UP && (BRK || SUP);
SIG && SIG(1)==0
```

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

현재 자동 빌드 파일에는 Apple Developer 서명·공증과 Windows 배포자 서명이 없습니다. 따라서 다른 컴퓨터에서 macOS Gatekeeper 또는 Windows SmartScreen 경고가 나올 수 있습니다. 이 경고를 없애려면 정식 서명·공증 정보가 별도로 필요합니다.

GitHub의 `Windows 설치 파일 만들기` 작업을 실행하면 실제 Windows 빌드 컴퓨터에서 자동 테스트 후 설치 프로그램을 만들고 지정한 릴리스에 올립니다.

## 보안

- `.env`, 사용자 키, 접근 토큰, 로컬 DB는 Git에서 제외됩니다.
- 설치형 앱에서는 키를 macOS 키체인 또는 Windows 자격 증명 관리자에 저장합니다.
- 운영체제 보안 저장소를 사용할 수 없는 환경에서만 사용자 데이터 폴더의 권한 제한 파일로 대체합니다.
- 개발용 상위 폴더의 키는 빌드 파일에 포함되지 않습니다.

## 테스트

```bash
python -m pytest -q
```

이 도구는 조회 전용입니다. 주문 API는 포함하지 않습니다.
