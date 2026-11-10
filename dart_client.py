"""Small, rate-limited OpenDART HTTP client."""
import logging
import time
from typing import Any
import requests

LOG = logging.getLogger(__name__)
BASE = "https://opendart.fss.or.kr/api"

class DartError(RuntimeError):
    pass

class RateLimitError(DartError):
    pass

class DartClient:
    def __init__(self, api_key: str, timeout: float = 30, retries: int = 3, interval: float = .25, session=None, sleeper=time.sleep):
        self.api_key, self.timeout, self.retries, self.interval = api_key, timeout, retries, interval
        self.session = session or requests.Session()
        self.sleeper, self._last_call = sleeper, 0.0

    def _request(self, endpoint: str, params: dict[str, str] | None = None, binary: bool = False):
        query = {"crtfc_key": self.api_key, **(params or {})}
        for attempt in range(self.retries + 1):
            delay = self.interval - (time.monotonic() - self._last_call)
            if delay > 0: self.sleeper(delay)
            try:
                response = self.session.get(f"{BASE}/{endpoint}", params=query, timeout=self.timeout)
                self._last_call = time.monotonic()
                response.raise_for_status()
                if binary:
                    return response.content
                data = response.json()
                status = str(data.get("status", ""))
                if status == "000": return data
                if status == "013": return data
                if status == "020": raise RateLimitError("OpenDART 요청 한도 초과(status=020)")
                raise DartError(f"OpenDART 오류 status={status}: {data.get('message', '알 수 없는 오류')}")
            except RateLimitError:
                raise
            except (requests.RequestException, ValueError, DartError) as exc:
                if isinstance(exc, DartError) and not isinstance(exc, requests.RequestException): raise
                if attempt >= self.retries: raise DartError(f"{endpoint} 요청 실패: {exc}") from exc
                self.sleeper(min(2 ** attempt, 8))
        raise DartError(f"{endpoint} 요청 실패")

    def get_corp_codes_zip(self) -> bytes:
        return self._request("corpCode.xml", binary=True)

    def document(self, receipt_no: str) -> bytes:
        return self._request("document.xml", {"rcept_no": receipt_no}, binary=True)

    def financials(self, corp_code: str, year: int, fs_div: str) -> dict[str, Any]:
        return self._request("fnlttSinglAcntAll.json", {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011", "fs_div": fs_div})

    def dividends(self, corp_code: str, year: int) -> dict[str, Any]:
        return self._request("alotMatter.json", {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011"})

    def filings(self, corp_code: str, year: int) -> dict[str, Any]:
        return self._request("list.json", {"corp_code": corp_code, "bgn_de": f"{year}0101", "end_de": f"{year+1}0630", "pblntf_ty": "A", "page_count": "100"})
