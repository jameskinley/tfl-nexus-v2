from dotenv import load_dotenv
import os
from logging import getLogger

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "https://openrouter.ai/api/v1")
API_KEY = os.getenv("API_KEY", "")
MODEL = os.getenv("MODEL", "openai/gpt-oss-20b:free")
MCP_SSE_URL = os.getenv("MCP_SSE_URL", "http://tfl-nexus-api:9002/sse")

logger = getLogger(__name__)

logger.info(f"Configuration loaded: BASE_URL={BASE_URL}, MODEL={MODEL}, API_KEY={'***' if API_KEY else '(not set)'}")