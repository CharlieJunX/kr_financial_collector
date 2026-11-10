"""Load and cache the ZIP/XML corporation-code map."""
from pathlib import Path
import io, json, logging, zipfile
import xml.etree.ElementTree as ET

LOG = logging.getLogger(__name__)

class CorpMapper:
    def __init__(self, cache_path: Path, client):
        self.cache_path, self.client = Path(cache_path), client
        self.by_stock: dict[str, dict[str, str]] = {}

    @staticmethod
    def parse_zip(payload: bytes) -> dict[str, dict[str, str]]:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            xml_name = next((n for n in archive.namelist() if n.lower().endswith(".xml")), None)
            if not xml_name: raise ValueError("corpCode ZIP에 XML 파일이 없습니다")
            root = ET.fromstring(archive.read(xml_name))
        result = {}
        for node in root.findall("list"):
            stock = (node.findtext("stock_code") or "").strip()
            corp = (node.findtext("corp_code") or "").strip()
            if len(stock) == 6 and stock.isdigit() and len(corp) == 8:
                result[stock] = {"corp_code": corp, "corp_name": (node.findtext("corp_name") or "").strip()}
        return result

    def load(self, refresh=False):
        if self.cache_path.exists() and not refresh:
            self.by_stock = json.loads(self.cache_path.read_text(encoding="utf-8")); return
        self.by_stock = self.parse_zip(self.client.get_corp_codes_zip())
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.by_stock, ensure_ascii=False, indent=2), encoding="utf-8")

    def find(self, stock_code: str): return self.by_stock.get(stock_code)
