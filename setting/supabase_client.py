from pathlib import Path
import os

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase 환경변수가 설정되지 않았습니다. .env 파일의 SUPABASE_URL과 SUPABASE_ANON_KEY를 확인하세요.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
