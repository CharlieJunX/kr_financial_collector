"""Conservative parser for annual common-stock cash dividends."""
import logging
from .validator import parse_amount

LOG = logging.getLogger(__name__)

def collect_dividend(response):
    rows = response.get("list", []) if response.get("status") == "000" else []
    if not rows:
        return {"dividend_per_share_krw":None, "total_dividend_krw":None, "dividend_status":"조회 실패/자료 없음", "receipt":""}
    common = [r for r in rows if "보통주" in str(r.get("stock_knd", ""))]
    dps_rows = [r for r in common if "주당" in str(r.get("se", "")) and "현금" in str(r.get("se", ""))]
    inferred_share_class = False
    if not dps_rows:
        dps_rows = [r for r in rows if str(r.get("stock_knd", "")).strip() in {"", "-", "–"} and "주당" in str(r.get("se", "")) and "현금" in str(r.get("se", ""))]
        inferred_share_class = True
    total_rows = [r for r in rows if "현금배당금총액" in str(r.get("se", ""))]
    dps_vals = {parse_amount(r.get("thstrm")) for r in dps_rows}
    total_vals = set()
    for r in total_rows:
        val = parse_amount(r.get("thstrm"))
        if val is not None:
            # API labels this field in 백만원; only apply conversion when label states it.
            unit = 1_000_000 if "백만원" in str(r.get("se", "")) else 1
            total_vals.add(val * unit)
    dps_vals.discard(None)
    if inferred_share_class:
        # When DART leaves every share-class label blank or '-', use the first
        # numeric DPS row in the API's original order as the common-share value.
        dps = next((parse_amount(r.get("thstrm")) for r in dps_rows
                    if parse_amount(r.get("thstrm")) is not None), None)
    else:
        dps = next(iter(dps_vals)) if len(dps_vals) == 1 else None
    total = next(iter(total_vals)) if len(total_vals) == 1 else None
    # A declared no-dividend result is only zero when API explicitly returns numeric zero.
    status = "정상" if dps is not None and total is not None and not inferred_share_class else "검증 필요"
    receipt = next((r.get("rcept_no", "") for r in rows if r.get("rcept_no")), "")
    return {"dividend_per_share_krw":dps, "total_dividend_krw":total, "dividend_status":status, "receipt":receipt}
