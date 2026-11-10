# kr_financial_collector

## 유럽 주식 수집

`data/input/eu_stocks.csv`는 헤더 없는 `티커,회사명` 형식입니다. Yahoo Finance의 연간 손익계산서·현금흐름표 및 배당 이력을 yfinance로 수집합니다. API 키는 필요하지 않습니다. 실행 시점을 기준으로 최근 완료된 5개 연도만 허용합니다.

```powershell
.\.venv\Scripts\python.exe run_eu_collector.py
.\.venv\Scripts\python.exe run_eu_collector.py --start-year 2023 --end-year 2025
```

결과는 `data/output/eu_financial_5years.csv`, 오류는 `data/output/eu_collection_errors.csv`에 저장합니다. `year`의 재무 수치는 회계연도 종료 연도, 주당 배당금은 배당락일의 달력연도에 귀속합니다. `currency`는 재무제표 통화, `dividend_currency`는 Yahoo 거래 통화입니다. 주당 배당금은 해당 연도 Yahoo 배당 이력을 합산하고, 총배당금은 현금흐름표의 현금배당 지급액 절댓값을 사용합니다. 두 배당 수치는 귀속 기간이 다를 수 있어 `검증 필요` 상태로 저장합니다. 결측치는 빈 칸이며 0으로 추정하지 않습니다.

원천: [Yahoo Finance 무료 재무제표 범위](https://finance.yahoo.com/about/plans/compare/), [yfinance 사용법](https://github.com/ranaroussi/yfinance).

## 미국 주식 수집

`data/input/us_stocks.csv`는 헤더 없이 `티커,회사명` 형식입니다. 미국 수집기는 SEC EDGAR Company Facts의 10-K 연간 XBRL 수치를 읽습니다. `.env`에 `SEC_USER_AGENT=회사명 contact@example.com`처럼 소속과 연락처 이메일을 설정하세요. SEC API 키는 필요하지 않습니다.

```powershell
.\.venv\Scripts\python.exe run_us_collector.py --start-year 2016 --end-year 2025
.\.venv\Scripts\python.exe run_us_collector.py --start-year 2023 --end-year 2025 --refresh
```

결과는 `data/output/us_financial_10years.csv`, 누락 내역은 `data/output/us_collection_errors.csv`에 저장합니다. 금액은 환산하지 않은 **미국 달러(USD)**입니다. `year`는 10-K의 회계연도 종료 연도이며, 달력연도와 다를 수 있습니다. 매출과 영업이익은 SEC US-GAAP 계정에서 찾고 실제 매출 계정명·태그·접수번호를 보존합니다. 주당 배당금은 연간 보통주 선언액 또는 지급액, 총배당금은 연간 보통주 현금 지급액을 우선 사용합니다. 총배당금에 보통주 구분이 없는 `PaymentsOfDividends`만 있으면 값은 보존하되 우선주 포함 가능성을 확인해야 합니다. 없는 수치는 빈 칸과 `검증 필요`로 남깁니다. SEC 응답은 `data/cache/sec`에 저장하며 `--refresh`로 다시 받습니다.

SEC 문서: [EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [자동 접근 지침](https://www.sec.gov/about/developer-resources).

한국 상장기업의 사업연도별 재무 및 배당 자료를 OpenDART에서 수집합니다. 기본 연도는 2016~2025년이며, 실제 API 키가 없으면 실행되지 않습니다. 샘플 입력 CSV만 제공하며 샘플 수집 결과를 실제 값으로 가장하지 않습니다.

## 설치 및 API 키

Python 3.11 이상을 설치하고 VS Code에서 이 폴더를 엽니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

OpenDART에서 API 인증키를 발급한 뒤 `.env`의 `OPENDART_API_KEY`에 입력하세요. `.env`는 Git 추적에서 제외됩니다. 인증키는 로그에 출력하지 않습니다.

## 입력 및 실행

`data/input/kr_stocks.csv`는 헤더 없이 첫 줄부터 `6자리 종목코드,회사명`을 입력합니다. 종목코드 셀을 텍스트로 유지하세요. UTF-8 BOM과 CP949를 지원하며 중복 코드는 첫 번째 행만 수집하고 오류 파일에 남깁니다.

```powershell
python run_collector.py --start-year 2016 --end-year 2025
python run_collector.py --start-year 2023 --end-year 2025 --refresh
```

이 스크립트는 프로젝트 폴더 안에서 실행하거나 전체 경로로 호출해도 패키지 경로를 자동으로 설정합니다. 프로젝트 폴더의 상위 경로에서 `python -m kr_financial_collector`를 실행하는 방식도 지원합니다.

## 출력

- `data/output/kr_financial_10years.csv`: 종목·연도별 자료, UTF-8 BOM
- `data/output/collection_errors.csv`: 잘못된 입력, 중복, 누락, 검증 필요, 통신 오류
- `data/cache/corp_codes.json`: 기업코드 매핑 캐시
- `data/cache/financial_rows.json`: 종목·연도 수집 캐시
- `logs/collector.log`: 실행 로그

중단 후 재실행하면 완료된 종목·연도 캐시를 사용합니다. `--refresh`는 캐시를 무시하고 갱신합니다. 요청 제한 응답(status=020)은 재시도하지 않고 안전하게 중단합니다. 일시적 네트워크 오류는 제한된 지수 백오프로 재시도합니다.

## 해석상 유의사항

재무제표는 연결(CFS)을 먼저 조회하고 없으면 별도(OFS)를 사용합니다. 표준 계정 ID를 우선 사용하고, 계정명이 `영업수익(주석 1)`처럼 주석 번호를 포함한 경우에도 매칭합니다. IS와 CIS에 같은 계정이 중복되면 IS를 우선하며, 서로 다른 복수 후보면 수치 선택을 보류합니다. 금융사 `영업수익`, 보험사 `보험수익`도 후보로 읽되 일반 제조업 매출과 바로 비교할 수 없으므로 `검증 필요` 상태를 남깁니다. 재무 API의 `thstrm_amount`를 사용합니다. 이전 실행에서 누락·검증 상태로 저장한 행은 다음 실행에서 다시 조회합니다.

표준 계정 ID와 정확한 계정명이 없을 때는 `IS/CIS`의 계정명을 보수적으로 유사 매칭하고 `검증 필요`로 표시합니다. 재무 API의 연결·별도 응답이 모두 `013`이면 해당 사업보고서의 연결 손익계산서를 확인합니다. 원본의 당기 금액을 원 단위로 환산하고, 매출 총계가 없을 때는 공시된 `보험수익`을 매출액 칸에 넣습니다. 이때 `revenue_account_name`에 원래 계정명을 남깁니다. 영업이익만 확인되면 영업이익만 저장합니다. 원본에서 읽은 행은 `검증 필요`로 표시하고 접수번호를 보존합니다.

배당 API의 `se`, `stock_knd`, `thstrm`을 사용합니다. 보통주 DPS와 총액을 분리하고 API 계정명이 명시한 백만원 단위 총액만 원으로 환산합니다. 사업보고서 API는 사업연도귀속의 연간 항목을 주지만, 중간·분기배당의 합산 여부나 미배당의 명시적 0이 응답에서 모호하면 값을 임의 생성하지 않고 검증 상태로 둡니다. API가 재무수치를 제공하지 않은 연도는 빈 셀입니다.

보통주 표시가 없고 주식 종류가 비어 있거나 `-`인 주당 현금배당 행이 여러 개면 API 응답 순서상 첫 번째 숫자 값을 보통주 DPS로 저장하고 `검증 필요`로 표시합니다.

OpenDART 재무 응답에는 `rcept_no`가 있고 배당 응답에도 접수번호가 있어 `source_receipt_no`에 각각 보존합니다.

## 테스트

```powershell
python -m pytest
```

테스트는 모의 응답만 사용하며 실제 공시 값과의 비교 검증은 API 키를 설정하고 수집한 뒤 공시 원문과 별도로 대조해야 합니다.

공식 API 가이드: [단일회사 전체 재무제표](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020), [배당에 관한 사항](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019005), [기업고유번호](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018).
