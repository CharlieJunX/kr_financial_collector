"""Account matching and CFS-first annual financial extraction."""
import logging
import re
from difflib import SequenceMatcher
from .validator import parse_amount

LOG = logging.getLogger(__name__)
REVENUE_IDS = {"ifrs-full_revenue", "ifrs_revenue", "dart_revenue", "ifrs-full_revenuefromcontractswithcustomers"}
OPERATING_IDS = {"ifrs-full_operatingprofitloss", "ifrs_operatingprofitloss", "dart_operatingprofitloss"}
REVENUE_NAMES = {"매출액", "매출", "수익(매출액)", "영업수익", "영업수익(손실)", "영업수익(매출액)", "총영업수익", "보험수익"}
OPERATING_NAMES = {"영업이익", "영업이익(손실)", "영업손익"}
INDUSTRY_REVENUE_NAMES = {"영업수익", "영업수익(손실)", "영업수익(매출액)", "총영업수익", "보험수익"}

def _key(text): return "".join(str(text or "").lower().replace("-", "").replace("_", "").split())

def _name_key(text):
    """Normalize statement labels while dropping trailing note references."""
    name = str(text or "").strip()
    name = re.sub(r"\s*\((?:주석?\s*)?\d+(?:[^)]*)\)\s*$", "", name)
    return re.sub(r"\s+", "", name)

def _similar_name(text, names, revenue):
    """Conservative fallback for unstandardized account labels."""
    label = re.sub(r"[^가-힣A-Za-z0-9]", "", _name_key(text))
    if label.startswith("연결"):
        label = label[2:]
    if label.endswith(("합계", "총액")):
        label = label[:-2]
    if label.startswith("총"):
        label = label[1:]
    if revenue:
        if not any(root in label for root in ("매출", "영업수익", "보험수익")):
            return False
        if any(part in label for part in ("원가", "총이익", "재보험", "보험료", "이자", "수수료", "기타")):
            return False
    else:
        if "영업" not in label or not any(part in label for part in ("이익", "손익", "손실")):
            return False
        if any(part in label for part in ("영업외", "이익률", "보험영업", "투자영업")):
            return False
    aliases = [re.sub(r"[^가-힣A-Za-z0-9]", "", _name_key(name)) for name in names]
    return max((SequenceMatcher(None, label, alias).ratio() for alias in aliases), default=0) >= 0.84

def pick_account(rows, ids, names):
    id_keys = {_key(i) for i in ids}
    candidates = [r for r in rows if _key(r.get("account_id")) in id_keys]
    match_type = "id"
    if not candidates:
        name_keys = {_name_key(n) for n in names}
        candidates = [r for r in rows if _name_key(r.get("account_nm")) in name_keys]
        match_type = "name"
    if not candidates:
        revenue = names == REVENUE_NAMES
        candidates = [r for r in rows if _similar_name(r.get("account_nm"), names, revenue)]
        match_type = "similar_name"
    # IS is the primary income statement. CIS often repeats the same accounts;
    # prefer IS when it has a matching candidate rather than treating that as ambiguous.
    is_candidates = [r for r in candidates if r.get("sj_div") == "IS"]
    if is_candidates:
        candidates = is_candidates
    # Collapse identical duplicate rows but retain ambiguity when the values differ.
    unique = {}
    for row in candidates:
        signature = (_key(row.get("account_id")), _name_key(row.get("account_nm")), str(row.get("thstrm_amount", "")).strip())
        unique[signature] = row
    candidates = list(unique.values())
    # Never guess between distinct totals or account candidates.
    if len(candidates) != 1: return None, "검증 필요" if candidates else "누락"
    return candidates[0], "검증 필요" if match_type == "similar_name" else "정상"

def collect_financial(client, corp_code, year, report_receipt=""):
    selected = None
    api_statuses = []
    for fs in ("CFS", "OFS"):
        result = client.financials(corp_code, year, fs)
        api_statuses.append(f"{fs}={result.get('status', 'unknown')}")
        if result.get("status") != "000" or not result.get("list"): continue
        rows = [r for r in result["list"] if r.get("sj_div") in {"IS", "CIS"}]
        revenue, rs = pick_account(rows, REVENUE_IDS, REVENUE_NAMES)
        operating, os = pick_account(rows, OPERATING_IDS, OPERATING_NAMES)
        if revenue or operating:
            selected = (fs, revenue, rs, operating, os, result); break
    if not selected:
        no_data = bool(api_statuses) and all(item.endswith("=013") for item in api_statuses)
        if no_data and report_receipt and hasattr(client, "document"):
            from .report_fallback import extract_annual_totals
            fallback = extract_annual_totals(client.document(report_receipt), year)
            if fallback:
                return {**fallback, "receipt":report_receipt, "financial_status":"검증 필요", "financial_detail":"공시 원본 연결 손익계산서 추출; " + ";".join(api_statuses)}
        return {"fs_type":"", "revenue_krw":None, "operating_profit_krw":None, "revenue_account_name":"", "revenue_account_id":"", "receipt":"", "financial_status":"API 자료 없음" if no_data else "계정 후보 매칭 실패", "financial_detail":";".join(api_statuses)}
    fs, rev, rs, op, os, result = selected
    revenue_value = parse_amount(rev.get("thstrm_amount")) if rev else None
    op_value = parse_amount(op.get("thstrm_amount")) if op else None
    account_name = rev.get("account_nm", "") if rev else ""
    status = "정상" if revenue_value is not None and op_value is not None and rs == os == "정상" else "검증 필요"
    if _name_key(account_name) in {_name_key(n) for n in INDUSTRY_REVENUE_NAMES}: status = "검증 필요"
    receipt = next((r.get("rcept_no", "") for r in result.get("list", []) if r.get("rcept_no")), "")
    return {"fs_type":fs, "revenue_krw":revenue_value, "operating_profit_krw":op_value, "revenue_account_name":account_name, "revenue_account_id":rev.get("account_id", "") if rev else "", "receipt":receipt, "financial_status":status, "financial_detail":";".join(api_statuses)}
