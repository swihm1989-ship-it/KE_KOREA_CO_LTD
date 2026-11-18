"""Chromium E2E click test of actual Streamlit email-outbox UI.

Never logs in to production. No network access to Gmail, POP, SMTP, OpenAI, or
Supabase: the fixture entirely replaces these backends.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[3]
PORT=8612
URL="http://127.0.0.1:"+str(PORT)
OUTPUT=Path(os.getenv("BROWSER_SMOKE_DIR","/tmp/master-email-ui-smoke"))
OUTPUT.mkdir(parents=True,exist_ok=True)

def wait_for_server():
    for attempt in range(80):
        try:
            with urllib.request.urlopen(URL+"/_stcore/health",timeout=2) as response:
                if response.status==200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Streamlit test server did not become healthy")

def click_and_check():
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,args=["--no-sandbox"])
        try:
            page=browser.new_page(viewport={"width":1370,"height":900})
            page.set_default_timeout(25000)
            page.goto(URL+"/",wait_until="domcontentloaded")
            expect(page.get_by_text("mock-send-count: 0")).to_be_visible(timeout=25000)
            expect(page.get_by_text("입찰 건 관련",exact=False).first).to_be_visible()
            send=page.get_by_role("button",name="발송",exact=True)
            expect(send).to_be_disabled()
            page.screenshot(path=str(OUTPUT/"01_draft_no_ai.png"),full_page=True)

            # A diagnostic must not trigger without explicit opt-in.
            page.get_by_text("AI 연결 상태 진단 · 가상 데이터만 사용",exact=True).click()
            probe=page.get_by_role("button",name="API 연결 진단 실행")
            expect(probe).to_be_disabled()
            page.get_by_text("가상 AI 연결 테스트 실행에 동의합니다.",exact=True).click()
            expect(probe).to_be_enabled()
            probe.click()
            expect(page.get_by_text("진단 성공: 가상 AI 서버 응답")).to_be_visible()
            page.screenshot(path=str(OUTPUT/"02_diagnostic_mock.png"),full_page=True)

            # Generate three fake candidates only after AI consent.
            page.get_by_text(
                "이 메일의 제목·본문을 OpenAI에 보내 AI 회신 후보를 생성하는 데 동의합니다.",
                exact=True,
            ).click()
            candidate_button=page.get_by_role("button",name="AI 회신 후보 3개 생성")
            expect(candidate_button).to_be_enabled()
            candidate_button.click()
            expect(page.get_by_text("AI 추천 회신 후보 3개")).to_be_visible()
            expect(page.get_by_text("후보 1 · 간결한 비즈니스형")).to_be_visible()
            expect(page.get_by_text("후보 2 · 친근한 협력형")).to_be_visible()
            expect(page.get_by_text("후보 3 · 상세하고 정중한 형식")).to_be_visible()
            page.screenshot(path=str(OUTPUT/"03_three_candidates.png"),full_page=True)

            # Editing cannot trigger send; final confirmation is mandatory.
            textarea=page.get_by_label("메일 내용 (직접 수정 가능)")
            textarea.fill("안녕하세요. 문의 내용을 검토한 후 다시 연락드리겠습니다.")
            expect(send).to_be_disabled()
            page.get_by_text(
                "받는 사람·제목·본문·서명을 모두 확인했습니다. 발송 버튼을 누르면 실제 이메일이 전송됩니다.",
                exact=True,
            ).click()
            expect(send).to_be_enabled()
            page.screenshot(path=str(OUTPUT/"04_approved_only.png"),full_page=True)

            # THIS IS MOCK TRANSPORT, NEVER REAL SMTP.
            send.click()
            expect(page.get_by_text("mock-send-count: 1")).to_be_visible()
            expect(page.get_by_text("미발송 메일이 없습니다.")).to_be_visible()
            page.screenshot(path=str(OUTPUT/"05_mock_sent_once.png"),full_page=True)
            print("MASTER_BROWSER_UI_SMOKE_OK: draft, consent, synthetic AI, 3 candidates,"
                  " editable text, approval gate, exactly one mocked send")
        finally:
            browser.close()

if __name__=="__main__":
    cmd=[
        sys.executable,"-m","streamlit","run",
        str(Path(__file__).with_name("browser_fixture.py")),
        "--server.address=127.0.0.1",
        "--server.port="+str(PORT),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.fileWatcherType=none",
    ]
    process=subprocess.Popen(cmd,cwd=str(ROOT),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    try:
        wait_for_server()
        click_and_check()
    finally:
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
