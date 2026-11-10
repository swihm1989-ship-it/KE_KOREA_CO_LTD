"""Deterministic contract completeness checks; not legal advice."""
from decimal import Decimal, InvalidOperation
from Quotation_KEKOREA.contracts.commission_policy import payment_policy_issues
from Quotation_KEKOREA.contracts.normalize_terms import normalize_term_keys


COMMON_REQUIRED = (
    "contract_date", "scope", "governing_law", "dispute_resolution",
)
TYPE_REQUIRED = {
    "sale": ("buyer", "seller", "products", "quantity", "unit", "unit_price",
             "currency", "payment_trigger", "payment_deadline", "delivery",
             "inspection_claims"),
    "trade_commission": ("client", "intermediary", "commission_payer",
                         "covered_transaction", "scope", "commission_formula",
                         "commission_basis", "currency", "success_trigger",
                         "payment_deadline", "term_or_deal_scope"),
    "investment_commission": ("client", "fundraiser", "commission_payer",
                              "project", "funding_type", "scope", "success_trigger",
                              "commission_formula", "currency", "payment_deadline",
                              "term_or_deal_scope"),
}
LABELS = {
    "contract_date": "계약일 또는 효력 발생 기준",
    "scope": "거래/업무 범위",
    "governing_law": "준거법 확인 또는 조항 제외 결정",
    "dispute_resolution": "분쟁 해결 확인 또는 조항 제외 결정",
    "buyer": "Buyer", "seller": "Seller", "products": "제품 및 필수 규격",
    "quantity": "수량", "unit": "수량 단위", "unit_price": "단가 또는 확정 산식",
    "currency": "통화", "payment_trigger": "결제 트리거",
    "payment_deadline": "결제 기한", "delivery": "인도 조건/장소/일정",
    "inspection_claims": "검수/클레임 처리", "client": "의뢰인",
    "intermediary": "중개인", "commission_payer": "커미션 지급자",
    "covered_transaction": "대상 거래", "commission_formula": "커미션 산식",
    "commission_basis": "산정 기준금액", "success_trigger": "성공 조건",
    "term_or_deal_scope": "적용 기간 또는 특정 거래 범위",
    "fundraiser": "유치 담당자", "project": "투자 대상 프로젝트/법인",
    "funding_type": "자금 형태",
    # The sale UI uses a dedicated label; commission policy is in its own workflow.
    "payment_trigger": "매매대금 또는 수수료 지급 조건",
    "late_interest_legal_review": "연체이율 적용 검토 (지급자 국가·준거법·커미션 채무)",
    "late_interest_source": "연체이율 검토 근거 (법령·검토 문서 및 확인일)",
}
NOT_APPLICABLE = {"n/a", "na", "not applicable", "none", "해당 없음", "없음"}


def _term_map(snapshot):
    return {str(term.get("key")): term for term in snapshot.get("terms", [])}


def validate_snapshot(snapshot, *, for_export=False, env=None):
    issues = []
    terms = _term_map(snapshot)
    required = list(COMMON_REQUIRED) + list(TYPE_REQUIRED.get(snapshot.get("contract_type"), ()))
    role_keys = {
        "sale": {"buyer", "seller"},
        "trade_commission": {"client", "intermediary", "commission_payer"},
        "investment_commission": {"client", "fundraiser", "commission_payer"},
    }.get(snapshot.get("contract_type"), set())
    parties = snapshot.get("parties", [])
    assigned_roles = [role for party in parties for role in party.get("roles", [])]
    duplicates = {role for role in assigned_roles if assigned_roles.count(role) > 1}
    for role in sorted(duplicates):
        issues.append({"severity": "block", "code": "duplicate_party_role", "key": role,
                       "message": f"당사자 역할이 중복되었습니다. 한 명의 담당자를 확인해 주세요: {LABELS.get(role, role)}"})
    existing_roles = {role for party in parties for role in party.get("roles", [])}
    for key in required:
        if key in role_keys and key not in existing_roles:
            issues.append({"severity": "block", "code": "missing_party",
                           "key": key, "message": f"확인 필요: {LABELS.get(key, key)}"})
            continue
        if key in role_keys:
            party = next(item for item in parties if key in item.get("roles", []))
            if party.get("status", "missing") != "confirmed":
                issues.append({"severity": "block", "code": "suggested_party", "key": key,
                               "message": f"당사자 정보를 확인해 주세요: {LABELS.get(key, key)}"})
            for field in ("legal_name", "country", "address"):
                if not str(party.get(field) or "").strip():
                    issues.append({"severity": "block", "code": "missing_party_detail",
                                   "key": f"{key}.{field}",
                                   "message": f"당사자 정보가 필요합니다: {LABELS.get(key, key)} — {field}"})
                elif str(party.get(field)).strip().casefold() in NOT_APPLICABLE:
                    issues.append({"severity": "block", "code": "party_detail_cannot_be_na",
                                   "key": f"{key}.{field}",
                                   "message": f"당사자 법인 정보는 해당 없음으로 대체할 수 없습니다: {LABELS.get(key, key)} — {field}"})
            continue
        term = terms.get(key)
        if key in {"governing_law", "dispute_resolution"} and key in snapshot.get("omissions", {}):
            if not str(snapshot["omissions"].get(key, {}).get("reason") or "").strip():
                issues.append({"severity": "block", "code": "omission_reason",
                               "key": key, "message": f"{LABELS[key]} 제외 이유를 입력해 주세요."})
            continue
        if not term or term.get("status") == "missing" or term.get("value") in (None, ""):
            issues.append({"severity": "block", "code": "missing_term", "key": key,
                           "message": f"확인 필요: {LABELS.get(key, key)}"})
        elif term.get("status") == "suggested":
            issues.append({"severity": "block", "code": "suggested_term", "key": key,
                           "message": f"AI 제안을 확정하거나 수정해 주세요: {LABELS.get(key, key)}"})
        elif str(term.get("value")).strip().casefold() in NOT_APPLICABLE:
            issues.append({"severity": "block", "code": "required_term_cannot_be_na",
                           "key": key, "message": f"필수 사업 조건은 해당 없음으로 대체할 수 없습니다: {LABELS.get(key, key)}"})
    for issue in snapshot.get("issues", []):
        if (isinstance(issue, dict)
                and (issue.get("severity") == "block"
                     or (issue.get("severity") == "confirm" and not issue.get("confirmed")))):
            issues.append(issue)
    if for_export:
        # Final files must not silently certify text still containing explicit
        # placeholders. DRAFT files remain available with review annotations.
        import re
        unresolved_pattern = re.compile(
            r'\[(?:서명\s*전\s*확인|확인\s*필요|TBD(?:\s*/[^\]]*)?|TO\s*CONFIRM|'
            r'TO\s*BE\s*CONFIRMED|PENDING\s*CONFIRMATION)\]', re.IGNORECASE)
        for clause in snapshot.get('clauses', []):
            for sentence in clause.get('sentences', []):
                if unresolved_pattern.search(str(sentence.get('text') or '')):
                    issues.append({'severity': 'block', 'code': 'unresolved_clause_placeholder',
                                   'key': str(sentence.get('id') or ''),
                                   'message': '최종 계약서 본문에 미확정 표시가 남아 있습니다: '
                                              + str(sentence.get('text') or '')[:140]})
    if for_export and snapshot.get("pending_reconciliation"):
        issues.append({"severity": "block", "code": "pending_reconciliation",
                       "message": "조건 변경과 본문 조항의 대조가 적용 대기 중입니다."})
    if for_export:
        issues.extend(payment_policy_issues(snapshot, env=env))
    return issues


def validate_decimal_term(term):
    try:
        value = Decimal(str(term.get("value")))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return value.is_finite()


def apply_analysis(snapshot, analysis):
    """Merge extracted terms without upgrading AI guesses to confirmed facts."""
    updated = dict(snapshot)
    updated["contract_type"] = analysis["contract_type"]
    updated["parties"] = []
    for party in analysis.get("parties", []):
        candidate = dict(party)
        candidate.setdefault("id", f"party_{len(updated['parties']) + 1}")
        candidate["status"] = "suggested"
        updated["parties"].append(candidate)
    # The AI may repeat a commercial field under different language labels
    # (e.g. '수량' and 'quantity'). Normalize before creating the snapshot.
    # Keep the earliest nonblank suggestion; never auto-resolve conflicting data.
    normalized, conflicts = normalize_term_keys(analysis)
    updated["terms"] = []
    seen_keys = set()
    for term in normalized.get("terms", []):
        candidate = dict(term)
        key = str(candidate.get("key") or "").strip()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        candidate["status"] = "suggested" if str(candidate.get("value") or "").strip() else "missing"
        candidate.setdefault("id", f"term_{len(updated['terms']) + 1}")
        updated["terms"].append(candidate)
    updated["issues"] = list(analysis.get("issues", []))
    if conflicts:
        updated["clause_extraction_conflicts"] = conflicts
        updated["issues"].append({
            "code": "contract_term_extraction_conflict",
            "severity": "confirm",
            "message": (
                "AI 추출 조건에 중복·모호한 항목이 있습니다. "
                "BOX 2에서 원문과 값을 확인해 주세요. 자동 확정하지 않았습니다."
            ),
            "confirmed": False,
        })
    updated["questions"] = analysis.get("questions", [])
    return updated
