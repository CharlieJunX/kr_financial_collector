"""Collect annual US financials and dividends from SEC Company Facts."""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from .config import ROOT

FIELDS = ["stock_code", "company_name", "year", "revenue_usd", "operating_profit_usd",
          "dividend_per_share_usd", "total_dividend_usd", "fs_type", "revenue_account_name",
          "revenue_account_id", "dividend_status", "data_status", "source_receipt_no", "collected_at"]
ERROR_FIELDS = ["stock_code", "company_name", "year", "error_type", "message"]
REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues",
                "SalesRevenueNet", "RevenueFromContractWithCustomer", "SalesRevenueGoodsNet",
                "RevenueFromContractWithCustomerNetOfInterestExpense", "InterestAndDividendIncomeOperating",
                "InterestIncomeExpenseNet", "InvestmentBankingRevenue", "InsurancePremiumsRevenue"]
OPERATING_TAGS = ["OperatingIncomeLoss"]
DPS_TAGS = ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]
TOTAL_TAGS = ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsForRepurchaseOfCommonStockAndDividends"]


def read_stocks(path):
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with path.open(encoding=encoding, newline="") as handle:
                lines = list(csv.reader(handle))
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("입력 CSV 인코딩을 읽을 수 없습니다")
    if lines and lines[0] and lines[0][0].strip().lower() in {"ticker", "stock_code", "symbol"}:
        lines = lines[1:]
    stocks, duplicates, seen = [], [], set()
    for line in lines:
        if not line or not any(cell.strip() for cell in line):
            continue
        ticker = line[0].strip().upper()
        name = line[1].strip() if len(line) > 1 else ""
        item = {"stock_code": ticker, "company_name": name}
        if ticker in seen:
            duplicates.append(item)
        else:
            stocks.append(item)
            seen.add(ticker)
    return stocks, duplicates


class SecClient:
    def __init__(self, user_agent, cache_dir, refresh=False):
        if not user_agent or "@" not in user_agent:
            raise ValueError("SEC_USER_AGENT에 소속명과 연락처 이메일을 설정하세요")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.cache_dir = Path(cache_dir)
        self.refresh = refresh
        self.last_request = 0.0

    def get(self, url, cache_name):
        path = self.cache_dir / cache_name
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for attempt in range(4):
            delay = 0.2 - (time.monotonic() - self.last_request)
            if delay > 0:
                time.sleep(delay)
            try:
                response = self.session.get(url, timeout=35)
                self.last_request = time.monotonic()
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == 3:
                        response.raise_for_status()
                    time.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    def ticker_map(self):
        data = self.get("https://www.sec.gov/files/company_tickers.json", "tickers.json")
        return {v["ticker"].upper(): v for v in data.values()}

    def companyfacts(self, cik):
        return self.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
                        f"companyfacts_{int(cik):010d}.json")


def annual_fact(facts, tags, unit, year):
    """Select an annual duration ending in the stated fiscal year, preferring restatements."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        concept = gaap.get(tag, {})
        candidates = []
        for fact in concept.get("units", {}).get(unit, []):
            if fact.get("form") not in {"10-K", "10-K/A"} or not fact.get("start") or not fact.get("end"):
                continue
            try:
                start = date.fromisoformat(fact["start"])
                end = date.fromisoformat(fact["end"])
            except ValueError:
                continue
            duration = (end - start).days
            if end.year != year or not 300 <= duration <= 380 or not isinstance(fact.get("val"), (int, float)):
                continue
            candidates.append(fact)
        if candidates:
            # Prefer the current year's 10-K, then the latest comparative/restated fact.
            candidates.sort(key=lambda f: (f.get("fy") == year and f.get("fp") == "FY",
                                           f.get("filed", ""), f.get("accn", "")), reverse=True)
            return candidates[0]["val"], concept.get("label", tag), f"us-gaap:{tag}", candidates[0].get("accn", "")
    return None, "", "", ""


def collect_row(ticker, name, year, facts):
    revenue = annual_fact(facts, REVENUE_TAGS, "USD", year)
    operating = annual_fact(facts, OPERATING_TAGS, "USD", year)
    dps = annual_fact(facts, DPS_TAGS, "USD/shares", year)
    total = annual_fact(facts, TOTAL_TAGS[:2], "USD", year)
    # PaymentsForRepurchaseOfCommonStockAndDividends includes buybacks, so it is excluded.
    dividend_status = ("정상" if dps[0] is not None and total[0] is not None
                       and total[2] == "us-gaap:PaymentsOfDividendsCommonStock" else "검증 필요")
    status = "정상" if revenue[0] is not None and operating[0] is not None and dividend_status == "정상" else "검증 필요"
    return {"stock_code": ticker, "company_name": name, "year": year,
            "revenue_usd": revenue[0], "operating_profit_usd": operating[0],
            "dividend_per_share_usd": dps[0], "total_dividend_usd": total[0],
            "fs_type": "CONSOLIDATED", "revenue_account_name": revenue[1],
            "revenue_account_id": revenue[2], "dividend_status": dividend_status,
            "data_status": status,
            "source_receipt_no": ";".join(dict.fromkeys(x[3] for x in (revenue, operating, dps, total) if x[3])),
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def run(start_year=2016, end_year=2025, input_path=None, output_path=None, refresh=False, client=None):
    if start_year < 2009 or end_year < start_year:
        raise ValueError("기간을 확인하세요 (시작 연도 2009년 이상)")
    input_path = Path(input_path or ROOT / "data/input/us_stocks.csv")
    output_path = Path(output_path or ROOT / "data/output/us_financial_10years.csv")
    stocks, duplicates = read_stocks(input_path)
    errors = [{"stock_code": x["stock_code"], "company_name": x["company_name"], "year": "",
               "error_type": "duplicate_ticker", "message": "중복 티커를 제거했습니다"} for x in duplicates]
    if client is None:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        client = SecClient(os.getenv("SEC_USER_AGENT", ""), ROOT / "data/cache/sec", refresh)
    mapping = client.ticker_map()
    rows = []
    for stock in stocks:
        ticker, name = stock["stock_code"], stock["company_name"]
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker) or not name:
            errors.append({"stock_code": ticker, "company_name": name, "year": "",
                           "error_type": "invalid_input", "message": "티커 또는 회사명이 잘못되었습니다"})
            continue
        match = mapping.get(ticker)
        if not match:
            errors.append({"stock_code": ticker, "company_name": name, "year": "",
                           "error_type": "cik_not_found", "message": "SEC 티커/CIK 매핑을 찾지 못했습니다"})
            continue
        try:
            facts = client.companyfacts(match["cik_str"])
            for year in range(start_year, end_year + 1):
                row = collect_row(ticker, name, year, facts)
                rows.append(row)
                if row["data_status"] != "정상":
                    missing = [key for key in ("revenue_usd", "operating_profit_usd", "dividend_per_share_usd", "total_dividend_usd") if row[key] is None]
                    errors.append({"stock_code": ticker, "company_name": name, "year": year,
                                   "error_type": "incomplete_data", "message": "누락 항목: " + ", ".join(missing)})
        except requests.RequestException as exc:
            errors.append({"stock_code": ticker, "company_name": name, "year": "",
                           "error_type": "sec_request_error", "message": str(exc)})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for path, fields, values in ((output_path, FIELDS, rows),
                                  (output_path.parent / "us_collection_errors.csv", ERROR_FIELDS, errors)):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)
    print(f"완료: {len(rows)}행, 검증 필요 {sum(r['data_status'] != '정상' for r in rows)}행, 오류 {len(errors)}건")
    print(f"출력: {output_path}")
    return rows, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="SEC 미국 주식 연간 재무·배당 수집기")
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--input", type=Path, default=ROOT / "data/input/us_stocks.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/output/us_financial_10years.csv")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    try:
        run(args.start_year, args.end_year, args.input, args.output, args.refresh)
    except (ValueError, requests.RequestException) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
