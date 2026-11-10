"""Collect annual Korean listed-company financial and dividend data."""
import argparse, csv, json, logging, sys
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, load_settings
from .corp_mapper import CorpMapper
from .dart_client import DartClient, DartError, RateLimitError
from .dividend_collector import collect_dividend
from .financial_collector import collect_financial
from .validator import read_stocks, valid_stock_code

FIELDS = ["stock_code", "company_name", "year", "revenue_krw", "operating_profit_krw", "dividend_per_share_krw", "total_dividend_krw", "fs_type", "revenue_account_name", "revenue_account_id", "dividend_status", "data_status", "source_receipt_no", "collected_at"]
ERROR_FIELDS = ["stock_code", "company_name", "year", "error_type", "message"]
LOG = logging.getLogger(__name__)

def _load_cache(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}

def _save_cache(path, cache):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def run(start_year=2016, end_year=2025, refresh=False, input_path=None, output_path=None, client=None):
    input_path = Path(input_path or ROOT / "data/input/kr_stocks.csv")
    output_path = Path(output_path or ROOT / "data/output/kr_financial_10years.csv")
    cache_dir = ROOT / "data/cache"
    log_dir = ROOT / "logs"; log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "collector.log", level=logging.INFO, encoding="utf-8", format="%(asctime)s %(levelname)s %(message)s")
    if start_year < 2015 or end_year < start_year: raise ValueError("기간은 2015년 이상이며 시작 연도는 종료 연도보다 작거나 같아야 합니다")
    if client is None:
        settings = load_settings()
        client = DartClient(settings.api_key, settings.timeout, settings.retries, settings.request_interval)
    stocks, duplicates = read_stocks(input_path)
    errors = [{"stock_code":r.get("stock_code", ""),"company_name":r.get("company_name", ""),"year":"","error_type":"duplicate_stock_code","message":"중복 종목코드를 제거했습니다"} for r in duplicates]
    mapper = CorpMapper(cache_dir / "corp_codes.json", client); mapper.load(refresh=refresh)
    output_cache = cache_dir / "financial_rows.json"
    cache = {} if refresh else _load_cache(output_cache)
    rows, ok, failed, missing = [], 0, 0, 0
    stop_for_rate_limit = False
    for stock in stocks:
        if stop_for_rate_limit: break
        code, name = stock.get("stock_code", ""), (stock.get("company_name") or "").strip()
        if not valid_stock_code(code) or not name:
            errors.append({"stock_code":code,"company_name":name,"year":"","error_type":"invalid_input","message":"종목코드는 6자리 숫자, 회사명은 필수입니다"}); failed += end_year-start_year+1; continue
        mapped = mapper.find(code)
        if not mapped:
            errors.append({"stock_code":code,"company_name":name,"year":"","error_type":"corp_code_not_found","message":"OpenDART 기업고유번호 매핑을 찾지 못했습니다"}); failed += end_year-start_year+1; continue
        if mapped.get("corp_name") and mapped["corp_name"].casefold() != name.casefold():
            errors.append({"stock_code":code,"company_name":name,"year":"","error_type":"company_name_mismatch","message":f"입력 회사명과 DART 법인명 불일치: {mapped['corp_name']}"})
        for year in range(start_year, end_year + 1):
            key = f"{code}:{year}"
            # Retry incomplete records on the next run so parser improvements can
            # fill previously missing finance-sector accounts without --refresh.
            if key in cache and cache[key].get("data_status") == "정상":
                row = cache[key].copy(); rows.append(row); ok += row["data_status"] == "정상"; missing += row["data_status"] != "정상"; continue
            try:
                div = collect_dividend(client.dividends(mapped["corp_code"], year))
                fin = collect_financial(client, mapped["corp_code"], year, div.get("receipt", ""))
                receipts = [fin.get("receipt"), div.get("receipt")]
                status = "정상" if fin["financial_status"] == "정상" and div["dividend_status"] == "정상" else ("검증 필요" if "검증 필요" in {fin["financial_status"], div["dividend_status"]} else "일부 누락")
                row = {"stock_code":code,"company_name":name,"year":year,"revenue_krw":fin["revenue_krw"],"operating_profit_krw":fin["operating_profit_krw"],"dividend_per_share_krw":div["dividend_per_share_krw"],"total_dividend_krw":div["total_dividend_krw"],"fs_type":fin["fs_type"],"revenue_account_name":fin["revenue_account_name"],"revenue_account_id":fin["revenue_account_id"],"dividend_status":div["dividend_status"],"data_status":status,"source_receipt_no":";".join(dict.fromkeys(x for x in receipts if x)),"collected_at":datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
                rows.append(row); cache[key] = row; _save_cache(output_cache, cache)
                if status == "정상": ok += 1
                else:
                    missing += 1
                    detail = fin.get("financial_detail", "")
                    errors.append({"stock_code":code,"company_name":name,"year":year,"error_type":"incomplete_data","message":f"재무={fin['financial_status']}[{detail}]; 배당={div['dividend_status']}"})
            except RateLimitError as exc:
                errors.append({"stock_code":code,"company_name":name,"year":year,"error_type":"rate_limit","message":str(exc)})
                LOG.error("요청 한도 초과로 수집을 중단합니다"); stop_for_rate_limit = True; break
            except Exception as exc:
                errors.append({"stock_code":code,"company_name":name,"year":year,"error_type":"collection_error","message":str(exc)}); failed += 1
                row = {field:"" for field in FIELDS}; row.update(stock_code=code, company_name=name, year=year, dividend_status="조회 실패/자료 없음", data_status="조회 실패", collected_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")); rows.append(row)
                LOG.exception("수집 실패 stock=%s year=%s", code, year)
    # Keep a company-year row for unrequested years when the API quota stopped the run.
    if stop_for_rate_limit:
        present = {(r["stock_code"], int(r["year"])) for r in rows}
        for stock in stocks:
            code = str(stock.get("stock_code", "")).strip()
            if not valid_stock_code(code) or not mapper.find(code): continue
            for year in range(start_year, end_year + 1):
                if (code, year) in present: continue
                row = {field:"" for field in FIELDS}
                row.update(stock_code=code, company_name=(stock.get("company_name") or "").strip(), year=year, dividend_status="조회 실패/자료 없음", data_status="조회 실패", collected_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
                rows.append(row)
                errors.append({"stock_code":code,"company_name":row["company_name"],"year":year,"error_type":"rate_limit","message":"요청 한도 초과로 조회하지 못했습니다"})
                failed += 1
    # Avoid duplicate rows when an interrupted cache is resumed.
    dedup = {(r["stock_code"], int(r["year"])):r for r in rows}
    rows = sorted(dedup.values(), key=lambda r:(r["stock_code"], int(r["year"])))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer=csv.DictWriter(f, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    error_path = output_path.parent / "collection_errors.csv"
    with error_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer=csv.DictWriter(f, fieldnames=ERROR_FIELDS); writer.writeheader(); writer.writerows(errors)
    _save_cache(output_cache, cache)
    print(f"완료: 정상 {ok}건, 일부 누락 {missing}건, 실패 {failed}건, 중복 제거 {len(duplicates)}건")
    print(f"출력: {output_path}\n오류: {error_path}")
    return rows, errors

def main(argv=None):
    parser=argparse.ArgumentParser(description="OpenDART 한국 상장기업 연간 재무·배당 데이터 수집기")
    parser.add_argument("--start-year", type=int, default=2016); parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--input", type=Path, default=ROOT/"data/input/kr_stocks.csv")
    parser.add_argument("--output", type=Path, default=ROOT/"data/output/kr_financial_10years.csv")
    parser.add_argument("--refresh", action="store_true", help="기업코드 및 수집 캐시를 갱신합니다")
    args=parser.parse_args(argv)
    try: run(args.start_year,args.end_year,args.refresh,args.input,args.output)
    except (RuntimeError, ValueError, DartError) as exc: print(f"오류: {exc}", file=sys.stderr); return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
