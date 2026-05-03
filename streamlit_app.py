import os
import re

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def normalize_key(user_name: str, user_ssn: str) -> str:
    raw = f"{user_name}{user_ssn}"
    return re.sub(r"[\s\-]+", "", raw).lower()


@st.cache_resource
def get_gspread_client() -> gspread.Client:
    service_account_info = st.secrets.get("gcp_service_account")
    if service_account_info:
        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )
        return gspread.authorize(credentials)

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path:
        credentials = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        return gspread.authorize(credentials)

    raise RuntimeError(
        "Google 인증 정보가 없습니다. Streamlit Secrets에 gcp_service_account를 설정하거나 "
        "환경변수 GOOGLE_APPLICATION_CREDENTIALS를 설정해주세요."
    )


def get_config() -> tuple[str, str]:
    spreadsheet_id = (
        st.secrets.get("spreadsheet_id")
        or os.getenv("SPREADSHEET_ID")
        or "1LXvb-OHg9nJuHBLjuB7Wv1GhaOdyoUK0c49SLWZhsH8"
    )
    sheet_name = st.secrets.get("sheet_name") or os.getenv("SHEET_NAME") or "계좌정보조회"
    return spreadsheet_id, sheet_name


def get_account_info(user_name: str, user_ssn: str) -> dict:
    if not user_name or not user_ssn:
        return {"status": "error", "message": "이름과 주민번호를 모두 입력해주세요."}

    spreadsheet_id, sheet_name = get_config()
    client = get_gspread_client()

    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)
    rows = worksheet.get_values("A:L")

    if len(rows) < 2:
        return {"status": "not_found"}

    target_key = normalize_key(user_name, user_ssn)

    for row in rows[1:]:
        key_cell = row[0] if len(row) > 0 else ""
        sheet_key = re.sub(r"[\s\-]+", "", str(key_cell)).lower()
        if sheet_key and sheet_key == target_key:
            bank = row[9] if len(row) > 9 else ""
            account = row[10] if len(row) > 10 else ""
            owner = row[11] if len(row) > 11 else ""
            return {"status": "success", "bank": bank, "account": account, "owner": owner}

    return {"status": "not_found"}


def main() -> None:
    st.set_page_config(page_title="직원 계좌정보 조회 시스템", layout="centered")
    st.title("계좌정보 조회")

    user_name = st.text_input("이름", placeholder="예: 홍길동")
    user_ssn = st.text_input("주민등록번호", placeholder="예: 000101-1000000")

    if st.button("조회하기", use_container_width=True):
        if not user_name or not user_ssn:
            st.error("이름과 주민등록번호를 모두 입력해주세요.")
            return

        with st.spinner("조회 중..."):
            try:
                res = get_account_info(user_name, user_ssn)
            except Exception:
                st.error("조회 중 오류가 발생했습니다. 설정값과 권한을 확인해주세요.")
                return

        if res.get("status") == "success":
            st.success("조회 완료")
            st.markdown(f"**은행:** {res.get('bank', '')}")
            st.markdown(f"**계좌번호:** {res.get('account', '')}")
            st.markdown(f"**예금주:** {res.get('owner', '')}")
        elif res.get("status") == "error":
            st.error(res.get("message", "입력 값을 확인해주세요."))
        else:
            st.error("일치하는 정보가 없습니다. 입력 값을 확인해주세요.")


if __name__ == "__main__":
    main()

