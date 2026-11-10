import csv, json
from kr_financial_collector.main import run

class Fake:
    def __init__(self): self.calls=0
    def get_corp_codes_zip(self):
        import io,zipfile
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z: z.writestr("corp.xml","<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list></result>")
        return b.getvalue()
    def financials(self,corp,year,fs):
        self.calls+=1
        if fs=="CFS": return {"status":"000","list":[{"sj_div":"IS","account_id":"ifrs-full_revenue","account_nm":"매출액","thstrm_amount":"100"},{"sj_div":"IS","account_id":"ifrs-full_operatingprofitloss","account_nm":"영업이익","thstrm_amount":"-1"}]}
        return {"status":"013","list":[]}
    def dividends(self,corp,year): return {"status":"000","list":[{"se":"주당 현금배당금(원)","stock_knd":"보통주","thstrm":"0","rcept_no":"20240301000001"},{"se":"현금배당금총액(원)","thstrm":"0"}]}

def test_run_writes_one_row_and_reuses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("kr_financial_collector.main.ROOT",tmp_path)
    (tmp_path/"data/input").mkdir(parents=True)
    inp=tmp_path/"stocks.csv"; inp.write_text("stock_code,company_name\n005930,삼성전자\n",encoding="utf-8")
    out=tmp_path/"data/output/result.csv"; fake=Fake()
    rows,errors=run(2023,2023,input_path=inp,output_path=out,client=fake)
    assert len(rows)==1 and rows[0]["stock_code"]=="005930"
    assert rows[0]["operating_profit_krw"]==-1 and rows[0]["fs_type"]=="CFS"
    assert (tmp_path/"data/output/collection_errors.csv").exists()
    n=fake.calls
    run(2023,2023,input_path=inp,output_path=out,client=fake)
    assert fake.calls==n
