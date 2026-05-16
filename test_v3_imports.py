"""Quick import test for v3.0 modules."""
import sys
sys.path.insert(0, ".")

# AI modules
from datawarehouse.ai.llm_client import LLMClient, load_llm_config
from datawarehouse.ai.schema_inferrer import SchemaInferrer
from datawarehouse.ai.text_to_sql import TextToSQLEngine

# Storage modules
from datawarehouse.storage.duckdb_engine import DuckDBEngine
from datawarehouse.storage.minio_client import MinIOClient

# Ingestion modules
from datawarehouse.ingestion.proxy_pool import ProxyPool, Proxy
from datawarehouse.ingestion.playwright_fetcher import PlaywrightFetcher
from datawarehouse.ingestion.dlt_loader import DLTLoader

# Test instantiation (no external services needed)
pool = ProxyPool()
pool.add_proxy("http://1.2.3.4:8080")
assert pool.size == 1

engine = DuckDBEngine(":memory:")
engine.ingest_csv_directory = lambda *a, **k: 0  # skip actual ingest
assert engine.list_tables() == []

proxy = Proxy(url="http://test:8080")
assert proxy.score == 10.0

print("All v3.0 modules OK")
print("- AI: LLMClient, SchemaInferrer, TextToSQLEngine")
print("- Storage: DuckDBEngine, MinIOClient")
print("- Ingestion: ProxyPool, PlaywrightFetcher, DLTLoader")
