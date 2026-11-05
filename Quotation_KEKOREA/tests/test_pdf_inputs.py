"""PDF and mixed image/PDF inputs use the existing document extraction path."""
import base64
import json
import unittest
from Quotation_KEKOREA.agent.attachments import prepare_uploads
from Quotation_KEKOREA.agent.extractor import extract_trade_data
from Quotation_KEKOREA.agent.workflow_state import SavedUpload
from Quotation_KEKOREA.tests.test_extractor import FakeResponse


PDF = b'%PDF-1.7\n% synthetic two-page input: page 1 / page 2\n%%EOF'


class PdfInputsTests(unittest.TestCase):
    def test_pdf_payload_is_complete_for_every_output_document(self):
        for dtype, packing in (('PO', False), ('PI', False), ('CI', False), ('PL', True), ('CI', True)):
            with self.subTest(dtype=dtype, packing=packing):
                captured = {}
                def opener(request, timeout):
                    captured.update(json.loads(request.data))
                    return FakeResponse({'output': [{'content': [{'type': 'output_text', 'text': '{"items":[]}'}]}]})
                inputs = prepare_uploads([SavedUpload('source.PDF', 'application/pdf', PDF)])
                extract_trade_data('Extract this document', images=inputs, env={'OPENAI_API_KEY': 'test'},
                                   opener=opener, requested_document_type=dtype, packing_source=packing)
                part = captured['input'][0]['content'][1]
                self.assertEqual(part['type'], 'input_file')
                self.assertEqual(part['filename'], 'source.PDF')
                self.assertEqual(base64.b64decode(part['file_data'].split(',', 1)[1]), PDF)
                self.assertIn(dtype, captured['instructions'])

    def test_mixed_uploads_keep_original_order_and_image_encoding(self):
        captured = {}
        def opener(request, timeout):
            captured.update(json.loads(request.data))
            return FakeResponse({'output': [{'content': [{'type': 'output_text', 'text': '{"items":[]}'}]}]})
        inputs = prepare_uploads([SavedUpload('order.png', 'image/png', b'png'),
                                  SavedUpload('invoice.pdf', 'application/octet-stream', PDF)])
        extract_trade_data('Extract', images=inputs, env={'OPENAI_API_KEY': 'test'}, opener=opener)
        parts = captured['input'][0]['content']
        self.assertEqual([p['type'] for p in parts], ['input_text', 'input_image', 'input_file'])
        self.assertEqual(base64.b64decode(parts[1]['image_url'].split(',', 1)[1]), b'png')
        self.assertEqual(inputs[-1]['mime_type'], 'application/pdf')

    def test_invalid_files_and_existing_shared_limits_fail_before_network(self):
        cases = ([SavedUpload('empty.pdf', 'application/pdf', b'')],
                 [SavedUpload('fake.pdf', 'application/pdf', b'not a PDF')],
                 [SavedUpload('source.exe', 'application/octet-stream', b'x')],
                 [SavedUpload('huge.pdf', 'application/pdf', PDF + b'x' * (10 * 1024 * 1024))],
                 [SavedUpload('a.pdf', 'application/pdf', PDF)] * 6,
                 [SavedUpload('a.pdf', 'application/pdf', PDF + b'x' * (7 * 1024 * 1024))] * 3)
        for files in cases:
            with self.subTest(count=len(files)):
                with self.assertRaises(ValueError):
                    prepare_uploads(files)

    def test_pdf_header_may_appear_within_the_first_1024_bytes(self):
        uploaded = SavedUpload('prefixed.pdf', 'application/pdf', b'\x00' * 20 + PDF)
        self.assertEqual(prepare_uploads([uploaded])[0]['data'], uploaded.data)

    def test_saved_pdf_survives_workspace_switch_without_becoming_an_image(self):
        from Quotation_KEKOREA.agent.workflow_state import DocumentWorkspaces
        work = DocumentWorkspaces()
        state = {}
        work.activate(state, 'PI 만들기')
        work.remember_uploads('PI 만들기', [SavedUpload('pi.pdf', 'application/pdf', PDF)])
        work.activate(state, 'PO 만들기')
        work.activate(state, 'PI 만들기')
        self.assertEqual(prepare_uploads(work.uploads['PI 만들기'])[0]['data'], PDF)
