from kr_financial_collector.validator import parse_amount, read_stocks

def test_number_formats():
    assert parse_amount("(1,234)")==-1234
    assert parse_amount("") is None
    assert parse_amount("-") is None

def test_csv_dedup_and_zeros(tmp_path):
    path=tmp_path/"stocks.csv"
    path.write_text("005930,삼성전자\n005930,중복\n",encoding="utf-8-sig")
    rows, dup=read_stocks(path)
    assert rows[0]["stock_code"]=="005930" and len(dup)==1
