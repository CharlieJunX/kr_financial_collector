import io, zipfile
from kr_financial_collector.corp_mapper import CorpMapper

def test_parse_zip_keeps_leading_zero():
    xml=b"<result><list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name><stock_code>005930</stock_code></list><list><corp_code>12345678</corp_code><corp_name>Private</corp_name><stock_code></stock_code></list></result>"
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z: z.writestr("CORPCODE.xml",xml)
    assert CorpMapper.parse_zip(buf.getvalue()) == {"005930":{"corp_code":"00126380","corp_name":"Samsung"}}
