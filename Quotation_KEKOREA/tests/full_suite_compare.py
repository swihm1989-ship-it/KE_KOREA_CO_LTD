"""Compare ALL app tests against main baseline without leaking credentials.

This is an audit: pre-existing data-dependent failures remain explicitly
reported, while NEW failures on the feature branch fail CI.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BASELINE=Path("/tmp/ke-korea-main-baseline")
GUARD=ROOT/"Quotation_KEKOREA"/"tests"/"offline_guard"
ARTIFACT=Path("/tmp/master-full-suite-audit.json")
COMMAND=[sys.executable,"-m","unittest","discover","-s","Quotation_KEKOREA/tests",
         "-p","test_*.py","-q"]


def check(name,repo_root):
    env=os.environ.copy()
    env["PYTHONPATH"]=str(GUARD)+os.pathsep+str(repo_root)+os.pathsep+env.get("PYTHONPATH","")
    # Neither baseline nor branch can contact external providers.
    for key in ("OPENAI_API_KEY","WHOIS_POP_PASSWORD","WHOIS_SMTP_PASSWORD",
                "SUPABASE_SECRET_KEY","DATABASE_URL"):
        env[key]=""
    try:
        finished=subprocess.run(COMMAND,cwd=str(repo_root),env=env,
                                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                text=True,timeout=600,check=False)
        output=finished.stdout
        returncode=finished.returncode
    except subprocess.TimeoutExpired as exc:
        output=(exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout,bytes) else (exc.stdout or "")
        returncode=124
    matches=re.findall(r"^(?:ERROR|FAIL): .+$",output,re.M)
    size=re.search(r"Ran (\d+) tests",output)
    summary=re.search(r"^FAILED \(.+\)|^OK(?: \(.+\))?$",output,re.M)
    return {"suite":name,"tests":int(size.group(1)) if size else None,
            "status":returncode,"failures":sorted(set(matches)),
            "all_failed_entries":len(matches),"summary":summary.group(0) if summary else "no-summary"}


def main():
    if not BASELINE.is_dir():
        raise SystemExit("Baseline checkout missing")
    current=check("feature_branch",ROOT)
    baseline=check("main_baseline",BASELINE)
    added=sorted(set(current["failures"])-set(baseline["failures"]))
    removed=sorted(set(baseline["failures"])-set(current["failures"]))
    total_compatible=(current["tests"] is not None and baseline["tests"] is not None
                      and current["tests"]>=baseline["tests"])
    result={"feature_branch":current,"main_baseline":baseline,
            "new_failures":added,"resolved_failures":removed,
            "test_coverage_not_reduced":total_compatible}
    ARTIFACT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("BASELINE "+str(baseline["tests"])+" tests | "+baseline["summary"])
    print("BRANCH   "+str(current["tests"])+" tests | "+current["summary"])
    print("Known baseline failures: "+str(len(baseline["failures"])))
    print("New branch-only failures: "+str(len(added)))
    for item in added[:25]:
        print("NEW-FAILURE "+item)
    if (not total_compatible or added or current["status"]==124 or
            (baseline["status"]==0 and current["status"]!=0)):
        print("FAILED: all-suite regression exceeded the main baseline")
        return 1
    if current["status"]!=0:
        print("WARNING: pre-existing offline data/fixture failures remain. See audit artifact.")
    else:
        print("PASS: all app tests passed")
    return 0


if __name__=="__main__":
    sys.exit(main())
