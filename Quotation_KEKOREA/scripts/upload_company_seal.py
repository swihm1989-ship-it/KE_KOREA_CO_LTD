"""Upload the requested company seal to the user's private Supabase project."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from Quotation_KEKOREA.agent.branding import COMPANY_SEAL_SHA256
from Quotation_KEKOREA.agent.extractor import load_env
from Quotation_KEKOREA.agent.seal_storage import upload_company_seal


def main():
    env = load_env()
    if str(env.get("SUPABASE_URL") or "").rstrip("/") != "https://jusozufdsnpdxezxptfp.supabase.co":
        raise ValueError("The configured Supabase project is not the KE KOREA project")
    path = ROOT / "assets" / "image.png"
    if not path.is_file():
        raise ValueError("The requested assets/image.png was not found")
    outcome = upload_company_seal(env, path.read_bytes(), COMPANY_SEAL_SHA256)
    print(f"Private company seal: {outcome} and verified.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Could not configure private company seal: {exc}", file=sys.stderr)
        raise SystemExit(1)
