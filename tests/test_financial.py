from kr_financial_collector.financial_collector import collect_financial

class Client:
    def __init__(self): self.calls=[]
    def financials(self, corp, year, fs):
        self.calls.append(fs)
        if fs=="CFS": return {"status":"013","list":[]}
        return {"status":"000","list":[
            {"sj_div":"IS","account_id":"ifrs-full_Revenue","account_nm":"매출액","thstrm_amount":"1,234","rcept_no":"20240301000001"},
            {"sj_div":"IS","account_id":"ifrs-full_OperatingProfitLoss","account_nm":"영업이익(손실)","thstrm_amount":"-25"}]}

def test_cfs_then_ofs_and_negative_values():
    c=Client(); data=collect_financial(c,"12345678",2023)
    assert c.calls==["CFS","OFS"]
    assert data["fs_type"]=="OFS" and data["revenue_krw"]==1234
    assert data["operating_profit_krw"]==-25 and data["receipt"]=="20240301000001"

def test_ambiguous_candidates_are_not_guessed():
    from kr_financial_collector.financial_collector import pick_account, REVENUE_IDS, REVENUE_NAMES
    first={"account_nm":"매출액","account_id":"unknown","thstrm_amount":"100"}
    second={"account_nm":"매출액","account_id":"unknown","thstrm_amount":"120"}
    assert pick_account([first,second],REVENUE_IDS,REVENUE_NAMES)[1]=="검증 필요"

def test_financial_sector_revenue_and_profit_aliases():
    class FinanceClient:
        def financials(self, corp, year, fs):
            if fs == "OFS": return {"status":"013","list":[]}
            return {"status":"000","list":[
                {"sj_div":"IS","account_id":"custom_revenue","account_nm":"영업수익(주석 4)","thstrm_amount":"8,765"},
                {"sj_div":"CIS","account_id":"custom_revenue","account_nm":"영업수익(주석 4)","thstrm_amount":"8,765"},
                {"sj_div":"IS","account_id":"custom_op_profit","account_nm":"영업손익","thstrm_amount":"-210"}]}
    result=collect_financial(FinanceClient(),"12345678",2024)
    assert result["fs_type"]=="CFS"
    assert result["revenue_krw"]==8765 and result["operating_profit_krw"]==-210
    assert result["revenue_account_name"]=="영업수익(주석 4)"
    assert result["financial_status"]=="검증 필요"

def test_distinguishes_api_no_data_from_account_match_failure():
    class EmptyClient:
        def financials(self, corp, year, fs): return {"status":"013","message":"조회된 데이터가 없습니다.","list":[]}
    result=collect_financial(EmptyClient(),"00139214",2022)
    assert result["financial_status"]=="API 자료 없음"
    assert result["financial_detail"]=="CFS=013;OFS=013"

def test_similar_name_fallback_with_nonstandard_ids():
    from kr_financial_collector.financial_collector import pick_account, REVENUE_IDS, REVENUE_NAMES, OPERATING_IDS, OPERATING_NAMES
    rows=[
        {"sj_div":"IS","account_id":"-표준계정코드 미사용-","account_nm":"연결 영업수익 합계","thstrm_amount":"100"},
        {"sj_div":"IS","account_id":"-표준계정코드 미사용-","account_nm":"영업 이익 합계","thstrm_amount":"20"},
        {"sj_div":"IS","account_id":"-표준계정코드 미사용-","account_nm":"영업이익률","thstrm_amount":"20"}]
    revenue, rs=pick_account(rows,REVENUE_IDS,REVENUE_NAMES)
    operating, os=pick_account(rows,OPERATING_IDS,OPERATING_NAMES)
    assert revenue["account_nm"]=="연결 영업수익 합계" and rs=="검증 필요"
    assert operating["account_nm"]=="영업 이익 합계" and os=="검증 필요"
