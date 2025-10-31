from pathlib import Path
import os

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parents[1]

# 프로젝트 루트(.env) → setting/.env 순으로 환경 변수 읽기
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL:
    raise RuntimeError("Supabase 환경변수가 설정되지 않았습니다. .env 파일의 SUPABASE_URL을 확인하세요.")

SUPABASE_KEY = SERVICE_ROLE_KEY or ANON_KEY

if not SUPABASE_KEY:
    raise RuntimeError(
        "Supabase Key가 설정되지 않았습니다. 서버에서 쓰기 작업을 하려면 SUPABASE_SERVICE_ROLE_KEY(권장) "
        "또는 SUPABASE_ANON_KEY가 필요합니다."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
