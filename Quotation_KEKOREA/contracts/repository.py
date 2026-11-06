"""Server-only Supabase persistence for private contract records."""
import json
import urllib.error
import urllib.parse
import urllib.request


class ContractRepositoryError(RuntimeError):
    pass


class ContractRepository:
    def __init__(self, env, *, opener=urllib.request.urlopen, timeout=20):
        self.base_url = str(env.get("SUPABASE_URL", "")).rstrip("/")
        self.key = str(env.get("SUPABASE_SECRET_KEY", ""))
        parsed = urllib.parse.urlparse(self.base_url)
        if (parsed.scheme != "https" or not parsed.hostname
                or not parsed.hostname.endswith(".supabase.co")
                or parsed.query or parsed.fragment):
            raise ValueError("Configure a valid HTTPS SUPABASE_URL for private contract storage.")
        if not self.key:
            raise ValueError("SUPABASE_SECRET_KEY is required for private contract storage.")
        self.opener = opener
        self.timeout = timeout

    def request(self, method, path, *, payload=None, query=None, headers=None):
        url = f"{self.base_url}/rest/v1/{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request_headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
        }
        request_headers.update(headers or {})
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                data = response.read()
                if not data:
                    return None
                return json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                raise ContractRepositoryError("This contract changed in another session. Reload the latest revision.") from None
            if exc.code in (401, 403):
                raise ContractRepositoryError("Private contract storage rejected the server credentials or database policy.") from None
            raise ContractRepositoryError(f"Private contract storage failed (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError):
            raise ContractRepositoryError("Private contract storage could not be reached. No save was confirmed.") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ContractRepositoryError("Private contract storage returned an invalid response.") from None

    def rpc(self, name, payload):
        result = self.request("POST", f"rpc/{name}", payload=payload)
        if isinstance(result, dict) and result.get("error"):
            code = result.get("error")
            if code == "revision_conflict":
                raise ContractRepositoryError("This contract changed in another session. Reload the latest revision.")
            raise ContractRepositoryError("The contract transaction could not be committed.")
        return result

    def list_contracts(self):
        return self.request("GET", "kekorea_contracts",
                            query=[("select", "id,title,contract_type,language,status,current_revision,updated_at"),
                                   ("order", "updated_at.desc"), ("limit", "100")]) or []

    def create_contract(self, record, snapshot):
        result = self.rpc("kekorea_contract_create", {
            "p_contract": record, "p_snapshot": snapshot,
        })
        if not isinstance(result, dict) or not result.get("id"):
            raise ContractRepositoryError("Contract creation was not confirmed by the database.")
        return result

    def load_contract(self, contract_id):
        safe_id = urllib.parse.quote(str(contract_id), safe="")
        rows = self.request("GET", "kekorea_contract_revisions",
                            query=[("select", "revision,snapshot,change_summary,created_at"),
                                   ("contract_id", f"eq.{safe_id}"),
                                   ("order", "revision.desc"), ("limit", "100")])
        return rows or []

    def commit_revision(self, contract_id, expected_revision, snapshot, change_summary):
        result = self.rpc("kekorea_contract_commit_revision", {
            "p_contract_id": str(contract_id),
            "p_expected_revision": int(expected_revision),
            "p_snapshot": snapshot,
            "p_change_summary": str(change_summary)[:500],
        })
        if not isinstance(result, dict) or not result.get("revision"):
            raise ContractRepositoryError("The revision was not confirmed by the database.")
        return result

    def add_message(self, contract_id, role, content):
        self.request("POST", "kekorea_contract_messages", payload={
            "contract_id": str(contract_id), "role": role, "content": content,
        }, headers={"Prefer": "return=minimal"})

    def list_messages(self, contract_id):
        return self.request("GET", "kekorea_contract_messages",
                            query=[("select", "id,role,content,created_at"),
                                   ("contract_id", f"eq.{contract_id}"),
                                   ("order", "created_at.asc"), ("limit", "200")]) or []

    def save_annotation(self, annotation):
        self.request("POST", "kekorea_contract_annotations", payload=annotation,
                     headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def list_annotations(self, contract_id):
        return self.request("GET", "kekorea_contract_annotations",
                            query=[("select", "id,contract_id,sentence_id,base_revision,instruction,proposal,status,created_at"),
                                   ("contract_id", f"eq.{contract_id}"),
                                   ("order", "created_at.desc"), ("limit", "300")]) or []

    def save_reference(self, record):
        rows = self.request("POST", "kekorea_contract_references", payload=record,
                            headers={"Prefer": "return=representation"})
        return rows[0] if isinstance(rows, list) and rows else record

    def list_references(self):
        return self.request("GET", "kekorea_contract_references",
                            query=[("select", "id,contract_id,filename,content_hash,extraction_status,extracted_text,created_at"),
                                   ("order", "created_at.desc"), ("limit", "100")]) or []

    def list_library_records(self, approved_only=False):
        query = [('select', 'id,filename,content_hash,storage_path,extraction_status,source_locations,created_at'),
                 ('contract_id', 'is.null'), ('order', 'created_at.desc'), ('limit', '500')]
        if approved_only:
            query.append(('extraction_status', 'eq.library_approved'))
        return self.request('GET', 'kekorea_contract_references', query=query) or []

    def get_library_record(self, reference_id):
        rows = self.request('GET', 'kekorea_contract_references', query=[
            ('select', '*'), ('id', f'eq.{reference_id}'), ('contract_id', 'is.null')]) or []
        return rows[0] if rows else None

    def update_library_record(self, reference_id, payload, *, expected_revision=None):
        query = [('id', f'eq.{reference_id}'), ('contract_id', 'is.null')]
        if expected_revision is not None:
            query.append(('source_locations->0->manifest->>revision', f'eq.{expected_revision}'))
        rows = self.request('PATCH', 'kekorea_contract_references', payload=payload,
                            query=query, headers={'Prefer': 'return=representation'})
        if not rows:
            raise ContractRepositoryError('The shared sample changed or is unavailable. Reload before editing.')

    def private_bucket(self, bucket):
        request = urllib.request.Request(f'{self.base_url}/storage/v1/bucket/{urllib.parse.quote(bucket, safe="")}',
                                         headers={'apikey': self.key, 'Authorization': f'Bearer {self.key}'})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise ContractRepositoryError('Could not verify the private sample bucket.') from None

    def delete_reference(self, reference_id):
        self.request("DELETE", "kekorea_contract_references",
                     query=[("id", f"eq.{reference_id}")])

    def contract_references(self, contract_id):
        return self.request("GET", "kekorea_contract_references",
                                   query=[("select", "id,filename,content_hash,storage_path,extraction_status,extracted_text,source_locations,created_at"),
                                          ("contract_id", f"eq.{contract_id}"),
                                          ("order", "created_at.desc"), ("limit", "100")]) or []

    def list_preferred_clauses(self):
        return self.request("GET", "kekorea_preferred_clauses",
                            query=[("select", "id,text,language,contract_types,roles,category,source_refs,approved_at,active"),
                                   ("order", "approved_at.desc"), ("limit", "300")]) or []

    def save_preferred_clause(self, clause):
        rows = self.request("POST", "kekorea_preferred_clauses", payload=clause,
                            headers={"Prefer": "return=representation"})
        return rows[0] if isinstance(rows, list) and rows else clause

    def set_preferred_clause_active(self, clause_id, active):
        self.request("PATCH", "kekorea_preferred_clauses",
                     query=[("id", f"eq.{clause_id}")], payload={"active": bool(active)},
                     headers={"Prefer": "return=minimal"})

    def save_export(self, record):
        self.request("POST", "kekorea_contract_exports", payload=record,
                     headers={"Prefer": "return=minimal"})

    def delete_export(self, contract_id, revision, file_format, storage_path):
        self.request("DELETE", "kekorea_contract_exports",
                     query=[("contract_id", f"eq.{contract_id}"),
                            ("revision", f"eq.{revision}"),
                            ("format", f"eq.{file_format}"),
                            ("storage_path", f"eq.{storage_path}")])

    def list_exports(self, contract_id):
        return self.request("GET", "kekorea_contract_exports",
                            query=[("select", "id,contract_id,revision,language,format,storage_path,content_hash,created_at"),
                                   ("contract_id", f"eq.{contract_id}"),
                                   ("order", "created_at.desc"), ("limit", "100")]) or []

    def upload_private_file(self, bucket, path, data, content_type):
        url = f"{self.base_url}/storage/v1/object/{bucket}/{urllib.parse.quote(path, safe='/')}"
        request = urllib.request.Request(url, data=data, method="POST", headers={
            "apikey": self.key, "Authorization": f"Bearer {self.key}",
            "Content-Type": content_type, "x-upsert": "false",
        })
        try:
            with self.opener(request, timeout=self.timeout) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            raise ContractRepositoryError(f"Private file upload failed (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError):
            raise ContractRepositoryError("Private file storage could not be reached.") from None

    def download_private_file(self, bucket, path):
        url = f"{self.base_url}/storage/v1/object/{bucket}/{urllib.parse.quote(path, safe='/')}"
        request = urllib.request.Request(url, headers={"apikey": self.key,
            "Authorization": f"Bearer {self.key}"}, method="GET")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ContractRepositoryError(f"Private file download failed (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError):
            raise ContractRepositoryError("Private file storage could not be reached.") from None

    def delete_private_file(self, bucket, path):
        url = f"{self.base_url}/storage/v1/object/{bucket}"
        request = urllib.request.Request(url, data=json.dumps({"prefixes": [path]}).encode("utf-8"),
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"}, method="DELETE")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            raise ContractRepositoryError(f"Private file deletion failed (HTTP {exc.code}).") from None
        except (urllib.error.URLError, TimeoutError):
            raise ContractRepositoryError("Private file storage could not be reached.") from None

    def delete_contract(self, contract_id):
        self.rpc("kekorea_contract_delete", {"p_contract_id": str(contract_id)})
