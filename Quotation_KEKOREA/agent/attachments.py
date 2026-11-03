"""Shared bounded image/PDF attachments; retain complete original file bytes."""
import base64
from pathlib import PurePath

_MIMES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
          '.webp': 'image/webp', '.pdf': 'application/pdf'}
_ALLOWED = set(_MIMES.values())


def validate_attachment(item):
    name = str(item.get('name') or 'uploaded file')
    mime = item.get('mime_type')
    if mime not in _ALLOWED:
        if mime in (None, '', 'application/octet-stream'):
            mime = _MIMES.get(PurePath(name).suffix.casefold())
        if mime not in _ALLOWED:
            raise ValueError(f'Unsupported attachment type for {name}; use PNG, JPG, WEBP or PDF')
    data = item.get('data')
    if not isinstance(data, bytes) or not data:
        raise ValueError(f'Uploaded attachment is empty: {name}')
    if len(data) > 10 * 1024 * 1024:
        raise ValueError(f'{name} exceeds the 10 MB per-file limit')
    if mime == 'application/pdf' and not data[:1024].lstrip().startswith(b'%PDF-'):
        raise ValueError(f'{name} is not a valid PDF file')
    return {'name': name, 'mime_type': mime, 'data': data}


def prepare_uploads(uploads):
    return validate_attachments([{'name': upload.name, 'mime_type': upload.type, 'data': upload.getvalue()}
                                 for upload in uploads or []])


def validate_attachments(items):
    if len(items) > 5:
        raise ValueError('Attach no more than 5 images/PDF files at a time')
    result = [validate_attachment(item) for item in items]
    if sum(len(item['data']) for item in result) > 20 * 1024 * 1024:
        raise ValueError('Attachments exceed the 20 MB combined limit')
    return result


def input_blocks(items):
    blocks = []
    for item in validate_attachments(items or []):
        data_url = f"data:{item['mime_type']};base64,{base64.b64encode(item['data']).decode('ascii')}"
        if item['mime_type'] == 'application/pdf':
            blocks.append({'type': 'input_file', 'filename': item['name'], 'file_data': data_url})
        else:
            blocks.append({'type': 'input_image', 'image_url': data_url, 'detail': 'high'})
    return blocks
