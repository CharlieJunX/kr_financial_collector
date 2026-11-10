from kr_financial_collector.dividend_collector import collect_dividend

def test_common_dps_and_million_won_total():
    response={"status":"000","list":[
        {"se":"주당 현금배당금(원)","stock_knd":"보통주","thstrm":"1,444","rcept_no":"20240301000001"},
        {"se":"주당 현금배당금(원)","stock_knd":"우선주","thstrm":"1,445"},
        {"se":"현금배당금총액(백만원)","stock_knd":"","thstrm":"9,800"}]}
    result=collect_dividend(response)
    assert result["dividend_per_share_krw"]==1444
    assert result["total_dividend_krw"]==9_800_000_000
    assert result["dividend_status"]=="정상"

def test_missing_is_not_zero():
    result=collect_dividend({"status":"013","list":[]})
    assert result["dividend_per_share_krw"] is None
    assert result["dividend_status"]=="조회 실패/자료 없음"

def test_total_survives_unlabelled_share_classes():
    response={"status":"000","list":[
        {"se":"현금배당금총액(백만원)","stock_knd":"-","thstrm":"329,938","rcept_no":"20200330003962"},
        {"se":"주당 현금배당(원)","stock_knd":"-","thstrm":"2,000"},
        {"se":"주당 현금배당(원)","stock_knd":"-","thstrm":"2,050"}]}
    result=collect_dividend(response)
    assert result["total_dividend_krw"]==329_938_000_000
    assert result["dividend_per_share_krw"]==2000
    assert result["dividend_status"]=="검증 필요"

def test_single_numeric_unlabelled_dps_is_preserved_for_review():
    result=collect_dividend({"status":"000","list":[
        {"se":"주당 현금배당금(원)","stock_knd":"-","thstrm":"10,000"},
        {"se":"주당 현금배당금(원)","stock_knd":"-","thstrm":"-"},
        {"se":"현금배당금총액(백만원)","stock_knd":"-","thstrm":"730,098"}]})
    assert result["dividend_per_share_krw"]==10000
    assert result["total_dividend_krw"]==730_098_000_000
    assert result["dividend_status"]=="검증 필요"
