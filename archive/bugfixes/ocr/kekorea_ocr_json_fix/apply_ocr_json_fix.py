from pathlib import Path
from datetime import date
import ast

root = Path(__file__).resolve().parent.parent
p = root / 'Quotation_KEKOREA/contracts/service.py'
s = p.read_text(encoding='utf-8')
old = '{"type": "input_text", "text": f"Reference document page {page_number}. Transcribe readable printed text."},'
new = '{"type": "input_text", "text": f"Reference document page {page_number}. Transcribe readable printed text. Return a JSON object with keys text and uncertain; do not guess missing content."},'
if new in s:
    print('Already applied to service.py')
elif s.count(old) == 1:
    updated = s.replace(old,new,1)
    ast.parse(updated)
    p.write_text(updated,encoding='utf-8')
    print('Patched OCR input message')
else:
    raise SystemExit('Expected input_text anchor not found uniquely. Nothing changed.')

files = ['README.md','Quotation_KEKOREA/README.md','Quotation_KEKOREA/README_CONTRACTS.md','Quotation_KEKOREA/Team/README.md','Quotation_KEKOREA/Presentation/README.md']
line = '\n- **2026-11-09 OCR JSON 400 오류 수정:** 스캔 PDF 참조자료 OCR의 OpenAI Responses API 요청에서 `json_object` 출력 형식을 사용할 때 `input_text`에 JSON 응답 요청을 명시했습니다. 기존 OCR 상단 78% 범위, 사용자 전송 동의, 필드 검증 및 실패 처리 방식은 유지합니다.\n'
for f in files:
    q=root/f
    content=q.read_text(encoding='utf-8')
    if '2026-11-09 OCR JSON 400 오류 수정' not in content:
        q.write_text(content.rstrip()+ '\n' + line, encoding='utf-8')
        print('Updated',f)

q=root/'Quotation_KEKOREA/tests/test_contract_reference_ocr_json_request.py'
if not q.exists():
    q.write_text('''"""Regress OpenAI JSON mode HTTP 400 for scanned-reference OCR."""\nimport io\nimport json\nimport unittest\nfrom unittest.mock import patch\n\nfrom PIL import Image\nfrom Quotation_KEKOREA.contracts.service import extract_reference_page\n\n\nclass Response:\n    def __enter__(self):\n        return self\n\n    def __exit__(self, *_):\n        return False\n\n    def read(self, *args):\n        body = {"output": [{"content": [{"type": "output_text", "text": json.dumps({"text": "Example", "uncertain": []})}]}]}\n        return json.dumps(body).encode("utf-8")\n\n\nclass ReferenceOCRJSONTests(unittest.TestCase):\n    def test_json_mode_mentions_json_in_input_message(self):\n        image = Image.new("RGB", (100, 100), "white")\n        file = io.BytesIO()\n        image.save(file, format="PNG")\n        seen = []\n\n        def opener(request, timeout):\n            payload = json.loads(request.data.decode("utf-8"))\n            seen.append(payload)\n            return Response()\n\n        result = extract_reference_page(file.getvalue(), 1, env={"OPENAI_API_KEY": "test", "OPENAI_MODEL": "mock"}, client=opener)\n        self.assertEqual(result, "Example")\n        self.assertEqual(seen[0]["text"]["format"]["type"], "json_object")\n        messages = [part["text"] for message in seen[0]["input"] for part in message["content"] if part["type"] == "input_text"]\n        self.assertTrue(any("json" in message.lower() for message in messages))\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',encoding='utf-8')
    print('Added OCR request regression test')
print('DONE')
