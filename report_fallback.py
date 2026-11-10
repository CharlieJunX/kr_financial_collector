"""Extract clearly labelled annual totals from a DART report attachment."""
import io
import re
import unicodedata
import zipfile
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
from .validator import parse_amount

def _plain(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or ""))

def _account(label):
    label = _plain(label)
    label = re.sub(r"^(?:[IVXL]+|\d+)\.", "", label, flags=re.IGNORECASE)
    return re.sub(r"\(주석[^)]*\)$", "", label)

def _cells(row):
    for tag in row.find_all(["td", "th", "te", "tu"], recursive=False):
        yield tag.get_text(" ", strip=True), int(tag.get("colspan", 1))

def _statement_context(table, year):
    headings = []
    for tag in table.find_all_previous(["table", "p", "title"], limit=30):
        if tag.find_parent("table"):
            continue
        line = _plain(tag.get_text(" ", strip=True))
        if len(line) > 400 or tag.name == "title":
            break
        headings.insert(0, line)
        if re.match(r"^(?:[가-힣]\.)?연결(?:포괄)?손익계산서", line):
            break
    context = "".join(headings)
    if not re.match(r"^(?:[가-힣]\.)?연결(?:포괄)?손익계산서", context):
        return None
    years = re.findall(r"(\d{4})년", context)
    unit = re.search(r"단위:(백만원|천원|원)\)", context)
    if not years or years[0] != str(year) or not unit:
        return None
    return context, {"원": 1, "천원": 1000, "백만원": 1000000}[unit[1]]

def _statement_values(table, year):
    rows = table.find_all("tr")
    if not rows:
        return None
    header = list(_cells(rows[0]))
    if len(header) < 3 or _plain(header[0][0]) not in {"과목", "계정과목"}:
        return None
    period = next((i for i, (label, _) in enumerate(header) if re.fullmatch(
        r"당기|제\d+(?:\(당\))?기", _plain(label)
    )), None)
    if period is None:
        return None
    context = _statement_context(table, year)
    if context is None:
        return None
    heading, multiplier = context
    period_label = _plain(header[period][0])
    if "당" not in period_label and not re.search(
        re.escape(period_label) + rf":?\(?{year}년", heading
    ):
        return None
    start = sum(width for _, width in header[:period])
    end = start + header[period][1]
    width = sum(span for _, span in header)
    accounts = {}
    labels = {"매출액", "영업수익", "총영업수익", "보험수익", "영업이익", "영업손익", "영업이익(손실)"}
    for row in rows[1:]:
        cells = [label for label, span in _cells(row) for _ in range(span)]
        if len(cells) != width or _account(cells[0]) not in labels:
            continue
        amounts = {parse_amount(cell) for cell in cells[start:end]}
        amounts.discard(None)
        if len(amounts) == 1:
            accounts.setdefault(_account(cells[0]), set()).add(
                (cells[0], amounts.pop() * multiplier)
            )
    revenue = set().union(*(accounts.get(label, set()) for label in ("매출액", "영업수익", "총영업수익")))
    if not revenue:
        revenue = accounts.get("보험수익", set())
    profit = set().union(*(accounts.get(label, set()) for label in ("영업이익", "영업손익", "영업이익(손실)")))
    if len(revenue) == 1 or len(profit) == 1:
        return (
            next(iter(revenue)) if len(revenue) == 1 else ("", None),
            next(iter(profit)) if len(profit) == 1 else ("", None),
        )
    return None

def extract_annual_totals(payload: bytes, year: int):
    """Read unambiguous amounts from the current-year consolidated statement."""
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        return None
    attachments, body = set(), set()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for filename in archive.namelist():
            if not filename.lower().endswith(".xml"):
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
                soup = BeautifulSoup(archive.read(filename), "html.parser")
            titles = [_plain(tag.get_text(" ", strip=True)) for tag in soup.find_all("title")]
            attached = "_" in filename
            if attached and not any("연결재무제표" in title for title in titles):
                continue
            matches = attachments if attached else body
            for table in soup.find_all("table"):
                match = _statement_values(table, year)
                if match:
                    matches.add(match)
    matches = attachments or body
    if len(matches) != 1:
        return None
    (revenue_name, revenue_value), (profit_name, profit_value) = matches.pop()
    return {"fs_type":"CFS", "revenue_krw":revenue_value, "operating_profit_krw":profit_value,
            "revenue_account_name":revenue_name, "revenue_account_id":"", "profit_account_name":profit_name}
