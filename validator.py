"""Parsing and validation helpers."""
import re
from decimal import Decimal, InvalidOperation

def parse_amount(value):
    if value is None or str(value).strip() in {"", "-", "–"}: return None
    cleaned = str(value).strip().replace(",", "").replace("원", "")
    if cleaned.startswith("(") and cleaned.endswith(")"): cleaned = "-" + cleaned[1:-1]
    try: return int(Decimal(cleaned))
    except (InvalidOperation, ValueError): return None

def valid_stock_code(value): return bool(re.fullmatch(r"\d{6}", str(value or "").strip()))

def read_stocks(path):
    import csv
    from pathlib import Path
    path = Path(path)
    last_error = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                lines = list(csv.reader(f))
            if lines and len(lines[0]) >= 2 and [cell.strip().lower() for cell in lines[0][:2]] == ["stock_code", "company_name"]:
                lines = lines[1:]
            unique, duplicates = [], []
            seen = set()
            for line in lines:
                if not line or not any(cell.strip() for cell in line): continue
                row = {"stock_code": line[0].strip(), "company_name": line[1].strip() if len(line) > 1 else ""}
                code = row["stock_code"]
                if code in seen: duplicates.append(row); continue
                seen.add(code); unique.append(row)
            return unique, duplicates
        except UnicodeDecodeError as exc: last_error = exc
    raise ValueError(f"CSV 인코딩을 읽을 수 없습니다: {last_error}")
