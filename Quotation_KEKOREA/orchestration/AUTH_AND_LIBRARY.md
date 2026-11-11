# MASTER GRAPH 로그인 + 기존 저장 계약서 조회

> 별도 `orchestration/ui/streamlit_page.py` 서비스만 대상. 기존 운영 `Quotation_KEKOREA/app.py` 및 기존 Render `render.yaml`은 변경하지 않습니다.

## 구현 범위

- 앱 모든 메뉴를 Streamlit OIDC `st.login` + `st.user.is_logged_in` + **`email_verified=True`** + 명시적 이메일 허용 목록으로 보호 (설정 없을 때 기본 거부)
- 허용된 사용자만 **저장된 계약서** 메뉴 사용
- 기존 `contracts.repository.ContractRepository`의 `list_contracts` / `load_contract`를 호출하여 저장된 계약서, 제목 검색, KO/EN, 현재 저장된 최대 100건, 리비전별 조항과 저장된 검토 이슈 확인
- **기존 룰 기반 분석**은 원본 데이터를 수정하지 않으며, AI 신규 호출/법률 자문이 아님
- CREATE/UPDATE/DELETE/RPC/저장/원본 계약서 수정/서명/PDF FINAL/SMTP/POP3는 추가하지 않음
- 실제 기존 계약서를 보기 위해서는 **동일한 Supabase 프로젝트/테이블**로 연결해야 함

## 1. OIDC 제공자(Google 예시) 설정

1. Google Cloud Console에서 OAuth 동의 화면 설정 후 Web application OAuth Client ID를 생성
2. Authorized redirect URI: 실제 별도 MASTER GRAPH URL에 **`/oauth2callback`** 추가
   - 예시: `https://<your-service>.onrender.com/oauth2callback`
   - Streamlit Cloud면: `https://<your-app>.streamlit.app/oauth2callback`
3. 설정 완료 후 Client ID / Client Secret 발급. **둘 다 GitHub 및 채팅 메시지에 기재하지 말 것**
4. Google 사용 시 OIDC discovery URL: `https://accounts.google.com/.well-known/openid-configuration`
5. 사용자 Gmail 주소가 OIDC에서 `email_verified=true`로 반환되고, 서버의 명시적 허용 이메일 목록에 일치해야 접근 가능
6. 사용자 목록 예시: `authorized-owner@example.com,authorized-reviewer@example.com`. 테스트 예시일 뿐 **실제 이메일은 호스팅 설정에만 입력**해야 함

## 2. Render (기존 Render 서비스와 별도)

Render의 신규 `ke-korea-orchestration-demo` 서비스에서 Environment에 아래 값을 추가합니다. GitHub 코드에 비밀 값은 없음.

| 환경변수 | 값 / 설명 |
| --- | --- |
| `ORCHESTRATION_ALLOWED_EMAILS` | 승인된 사용자 이메일 쉼표 구분, **와일드카드 불가** |
| `ORCHESTRATION_OIDC_CLIENT_ID` | Google/Microsoft OIDC Client ID |
| `ORCHESTRATION_OIDC_CLIENT_SECRET` | OIDC Client Secret |
| `ORCHESTRATION_OIDC_METADATA_URL` | OIDC HTTPS discovery URL |
| `ORCHESTRATION_OIDC_REDIRECT_URI` | 정확한 공개 MASTER GRAPH URL + `/oauth2callback` |
| `ORCHESTRATION_OIDC_COOKIE_SECRET` | 32자 이상의 랜덤 비밀 문자열 (예: `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `SUPABASE_URL` | 기존 KE KOREA 계약서가 저장된 Supabase 프로젝트 URL |
| `SUPABASE_SECRET_KEY` | 같은 프로젝트에 접근할 수 있는 서버 전용 비밀 키 |

배포 설정 `render-orchestration.yaml`에서 별도 Python 런처 `python -m Quotation_KEKOREA.orchestration.ui.secure_launch`를 실행합니다. 런처는 Render 서버 로컬의 `.streamlit/secrets.toml`을 런타임에 생성하고, 비밀 값을 로그나 GitHub에 출력하지 않습니다. 별도 서비스만 재배포하고 기존 `ke-korea-quotation`은 재배포/수정하지 마세요.

**운영 보안 주의:** 기존 Supabase 비밀 키가 광범위한 쓰기 권한을 갖는 경우가 있습니다. MASTER GRAPH 애플리케이션 코드는 GET만 호출하지만 **비밀 키 자체의 데이터베이스 권한이 읽기 전용이 되는 것은 아닙니다**. 운영 적용 전 전용 제한 권한 또는 보호된 백엔드 경계를 설계하는 것이 권장됩니다.

## 3. Streamlit Community Cloud

앱 Settings → Secrets에 다음과 같은 형식으로 등록합니다(값은 모두 호스팅 콘솔에서만 입력).

```toml
ORCHESTRATION_ALLOWED_EMAILS = "authorized-owner@example.com"
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "YOUR_SERVER_SIDE_SECRET"

[auth]
redirect_uri = "https://YOUR_APP.streamlit.app/oauth2callback"
cookie_secret = "LONG_RANDOM_SECRET"
client_id = "GOOGLE_CLIENT_ID"
client_secret = "GOOGLE_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

위 파일은 **예시일 뿐, 저장소에 실제 `secrets.toml`을 커밋하지 않습니다**. 해당 앱에만 적용하고 기존 운영 앱 설정을 바꾸지 마세요. 공개 데모 URL에 OIDC 설정이 없다면 기존 계약서 메뉴를 포함해 전체 앱 접근이 차단됩니다.

## 4. 검증 절차

1. 허용 목록 설정 전: **접근 차단** 화면만 표시
2. OIDC 미로그인: 로그인 버튼, 내부 메뉴 비표시
3. 승인되지 않은 이메일/미검증 이메일: 접근 거부
4. 허용 이메일 로그인: 메인 메뉴 → **저장된 계약서**
5. 계약명 검색/언어 선택 → 계약서 선택 → 리비전 선택 → 당사자·조항·거래조건·저장된 이슈 확인
6. 기존 계약서 검증 규칙으로 분석 보기 체크 → 기존 규칙 기반 점검 결과
7. 로그아웃 → 모든 메뉴에 대한 접근 다시 차단

**제약:** `list_contracts`가 최근 100건만 반환하도록 구현되어 있어 100건 이상일 때 과거 계약서는 나타나지 않을 수 있습니다. 기존 PDF 저장소의 파일 다운로드는 이번 연결에 포함되지 않습니다. 버전별 계약서 조항을 UI에서 열람하는 기능은 제공됩니다.

## 5. 테스트

```bash
python -m unittest discover -s Quotation_KEKOREA/orchestration/tests -p 'test_*.py' -v
```

코드의 Mock OIDC 계정은 unittest 내에서만 사용하며 운영에서 인증 우회용 플래그/테스트 비밀번호를 제공하지 않습니다.
