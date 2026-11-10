"""Yahoo Finance collector for five recent European fiscal years."""
import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .us_collector import read_stocks

FIELDS = ["stock_code", "company_name", "year", "currency", "dividend_currency", "revenue", "operating_profit", "dividend_per_share", "total_dividend", "fs_type", "revenue_account_name", "revenue_account_id", "dividend_status", "data_status", "source_receipt_no", "collected_at"]
ERROR_FIELDS = ["stock_code", "company_name", "year", "error_type", "message"]


def field(frame, column, tags):
    if column is None or frame is None or frame.empty:
        return None, ""
    for tag in tags:
        if tag in frame.index:
            value = frame.at[tag, column]
            if hasattr(value, "item"):
                value = value.item()
            if value is not None and str(value).lower() not in {"nan", "nat", "none"}:
                return value, tag
    return None, ""


def year_columns(frame):
    columns = {}
    if frame is not None and not frame.empty:
        for column in frame.columns:
            year = column.year
            if year not in columns or column > columns[year]:
                columns[year] = column
    return columns


def collect_rows(ticker, name, income, cash, history, financial_currency, dividend_currency, start_year, end_year):
    income_cols, cash_cols = year_columns(income), year_columns(cash)
    dividends = {}
    if history is not None and not history.empty and "Dividends" in history:
        for year, amounts in history["Dividends"].groupby(history.index.year):
            positive = amounts[amounts > 0]
            if not positive.empty:
                dividends[int(year)] = positive.sum()
    rows = []
    for year in range(start_year, end_year + 1):
        revenue, revenue_tag = field(income, income_cols.get(year), ("TotalRevenue", "OperatingRevenue"))
        operating, _ = field(income, income_cols.get(year), ("OperatingIncome",))
        paid, _ = field(cash, cash_cols.get(year), ("CashDividendsPaid", "CommonStockDividendPaid"))
        dps = dividends.get(year)
        rows.append({"stock_code": ticker, "company_name": name, "year": year,
                     "currency": financial_currency, "dividend_currency": dividend_currency,
                     "revenue": revenue, "operating_profit": operating,
                     "dividend_per_share": dps, "total_dividend": abs(paid) if paid is not None else None,
                     "fs_type": "YEARLY", "revenue_account_name": revenue_tag,
                     "revenue_account_id": f"Yahoo:{revenue_tag}" if revenue_tag else "",
                     "dividend_status": "검증 필요" if dps is not None or paid is not None else "조회 실패/자료 없음",
                     "data_status": "검증 필요" if any(v is not None for v in (revenue, operating, dps, paid)) else "일부 누락",
                     "source_receipt_no": "", "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return rows


def run(start_year=None, end_year=None, input_path=None, output_path=None, ticker_factory=None):
    current = datetime.now(timezone.utc).year
    end_year = current - 1 if end_year is None else end_year
    start_year = end_year - 4 if start_year is None else start_year
    if not current - 5 <= start_year <= end_year <= current - 1 or end_year - start_year >= 5:
        raise ValueError(f"최근 5개 완료 연도({current-5}~{current-1}) 중 최대 5년만 조회할 수 있습니다")
    if ticker_factory is None:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance가 필요합니다: pip install -r requirements.txt") from exc
        ticker_factory = yf.Ticker
    input_path = Path(input_path or ROOT / "data/input/eu_stocks.csv")
    output_path = Path(output_path or ROOT / "data/output/eu_financial_5years.csv")
    stocks, duplicates = read_stocks(input_path)
    errors = [{"stock_code": s["stock_code"], "company_name": s["company_name"], "year": "", "error_type": "duplicate_ticker", "message": "중복 티커를 제거했습니다"} for s in duplicates]
    rows = []
    for stock in stocks:
        ticker, name = stock["stock_code"], stock["company_name"]
        if not re.fullmatch(r"[A-Z0-9]+\.(DE|PA|AS)", ticker) or not name:
            errors.append({"stock_code": ticker, "company_name": name, "year": "", "error_type": "invalid_input", "message": "티커 또는 회사명이 잘못되었습니다"})
            continue
        try:
            source = ticker_factory(ticker)
            income = source.get_income_stmt(pretty=False)
            cash = source.get_cash_flow(pretty=False)
            history = source.history(start=f"{start_year}-01-01", end=f"{end_year+1}-01-01", actions=True, auto_adjust=False)
            try:
                info = source.info or {}
            except Exception:
                info = {}
            currency = info.get("financialCurrency") or ""
            dividend_currency = info.get("currency") or ""
            for row in collect_rows(ticker, name, income, cash, history, currency, dividend_currency, start_year, end_year):
                rows.append(row)
                missing = [key for key in ("revenue", "operating_profit", "dividend_per_share", "total_dividend") if row[key] is None]
                if missing or currency and dividend_currency and currency != dividend_currency:
                    message = "누락 항목: " + ", ".join(missing) if missing else ""
                    if currency and dividend_currency and currency != dividend_currency:
                        message += f"; 재무 통화 {currency}, 배당 통화 {dividend_currency}"
                    errors.append({"stock_code": ticker, "company_name": name, "year": row["year"], "error_type": "incomplete_data", "message": message})
        except Exception as exc:
            errors.append({"stock_code": ticker, "company_name": name, "year": "", "error_type": "collection_error", "message": str(exc)})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for path, fields, values in ((output_path, FIELDS, rows), (output_path.parent / "eu_collection_errors.csv", ERROR_FIELDS, errors)):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)
    print(f"완료: {len(rows)}행, 오류·누락 {len(errors)}건")
    print(f"출력: {output_path}")
    return rows, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Yahoo Finance 유럽 주식 최근 5년 재무·배당 수집기")
    parser.add_argument("--start-year", type=int)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--input", type=Path, default=ROOT / "data/input/eu_stocks.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/output/eu_financial_5years.csv")
    args = parser.parse_args(argv)
    try:
        run(args.start_year, args.end_year, args.input, args.output)
    except (RuntimeError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
