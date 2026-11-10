import io
import zipfile
from kr_financial_collector.report_fallback import extract_annual_totals

def test_extracts_current_year_connected_totals_only():
    xml = """<DOCUMENT><TITLE>(첨부) 연결 재무 제표</TITLE>
    <TABLE><TR><TD>연결 포괄 손익 계산서</TD></TR>
    <TR><TD>제73(당)기 (2022년 01월 01일부터 2022년 12월 31일까지)</TD></TR>
    <TR><TD>(단위: 원)</TD></TR></TABLE>
    <TABLE><TR><TH>과목</TH><TH>당기</TH><TH>전기</TH></TR>
    <TR><TD>I. 영업수익</TD><TD>25,784,423,160,935</TD><TD>24,444,257,521,333</TD></TR>
    <TR><TD>III. 영업이익</TD><TD>1,606,141,482,182</TD><TD>1,506,861,736,073</TD></TR></TABLE></DOCUMENT>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("filing_001.xml", xml)
    result = extract_annual_totals(buf.getvalue(), 2022)
    assert result["fs_type"] == "CFS"
    assert result["revenue_krw"] == 25_784_423_160_935
    assert result["operating_profit_krw"] == 1_606_141_482_182
    assert extract_annual_totals(buf.getvalue(), 2021) is None

def test_bank_statement_reads_million_won_and_skips_notes_and_prior_year():
    xml = """<DOCUMENT>
    <P>나. 연결손익계산서(포괄손익계산서)</P>
    <TABLE><TR><TD>제 22기 : 2022년 1월 1일부터 2022년 12월 31일까지</TD></TR>
    <TR><TD>제 21기 : 2021년 1월 1일부터 2021년 12월 31일까지</TD></TR></TABLE>
    <TABLE><TR><TD>(단위: 백만원)</TD></TR></TABLE>
    <TABLE><TR><TH>과목</TH><TH>주석</TH><TH COLSPAN="2">제 22기</TH><TH COLSPAN="2">제 21기</TH></TR>
    <TR><TD>Ⅰ.영업이익</TD><TD>39</TD><TD></TD><TD>5,888,079</TD><TD></TD><TD>5,952,096</TD></TR>
    <TR><TD>1.보험수익</TD><TD></TD><TD>6,890,905</TD><TD></TD><TD>6,484,523</TD><TD></TD></TR>
    </TABLE></DOCUMENT>"""

    def read(document):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("filing.xml", document)
        return extract_annual_totals(buf.getvalue(), 2022)

    result = read(xml)
    assert result["revenue_krw"] == 6_890_905_000_000
    assert result["revenue_account_name"] == "1.보험수익"
    assert result["operating_profit_krw"] == 5_888_079_000_000
    result = read(xml.replace("6,890,905", ""))
    assert result["revenue_krw"] is None
    assert result["operating_profit_krw"] == 5_888_079_000_000
