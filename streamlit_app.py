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


def get_account_info(spreadsheet_id: str, sheet_name: str, user_name: str, user_ssn: str) -> dict:
    if not user_name or not user_ssn:
        return {"status": "error", "message": "이름과 주민번호를 모두 입력해주세요."}

    client = get_gspread_client()
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except Exception:
        return {"status": "error", "message": "스프레드시트에 접근할 수 없습니다. ID와 권한을 확인해주세요."}

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        available_sheets = [ws.title for ws in spreadsheet.worksheets()]
        return {
            "status": "error",
            "error_type": "worksheet_not_found",
            "message": "시트(탭) 이름이 잘못되었습니다. 올바른 시트를 선택해주세요.",
            "available_sheets": available_sheets,
        }
    except Exception:
        return {"status": "error", "message": "시트를 열 수 없습니다. 시트 이름과 권한을 확인해주세요."}

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

    spreadsheet_id, configured_sheet_name = get_config()

    client = None
    sheet_names: list[str] | None = None
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        sheet_names = [ws.title for ws in spreadsheet.worksheets()]
    except Exception:
        sheet_names = None

    if "selected_sheet_name" not in st.session_state:
        st.session_state.selected_sheet_name = configured_sheet_name

    selected_sheet_name = configured_sheet_name
    if sheet_names:
        default_index = 0
        if st.session_state.selected_sheet_name in sheet_names:
            default_index = sheet_names.index(st.session_state.selected_sheet_name)
        elif configured_sheet_name in sheet_names:
            default_index = sheet_names.index(configured_sheet_name)

        selected_sheet_name = st.selectbox(
            "시트(탭) 선택",
            options=sheet_names,
            index=default_index,
        )
        st.session_state.selected_sheet_name = selected_sheet_name
    else:
        selected_sheet_name = st.text_input("시트(탭) 이름", value=st.session_state.selected_sheet_name)
        st.session_state.selected_sheet_name = selected_sheet_name

    with st.expander("진단", expanded=False):
        masked_id = spreadsheet_id
        if len(masked_id) > 10:
            masked_id = f"{spreadsheet_id[:6]}...{spreadsheet_id[-4:]}"
        st.write({"spreadsheet_id": masked_id, "sheet_name": selected_sheet_name})
        if sheet_names:
            st.write({"available_sheets": sheet_names})
        else:
            st.warning("시트 목록을 불러오지 못했습니다. Secrets/권한/스프레드시트 ID를 확인해주세요.")

    user_name = st.text_input("이름", placeholder="예: 홍길동")
    user_ssn = st.text_input("주민등록번호", placeholder="예: 000101-1000000")

    if st.button("조회하기", use_container_width=True):
        if not user_name or not user_ssn:
            st.error("이름과 주민등록번호를 모두 입력해주세요.")
            return

        with st.spinner("조회 중..."):
            try:
                res = get_account_info(spreadsheet_id, selected_sheet_name, user_name, user_ssn)
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
            if res.get("error_type") == "worksheet_not_found" and res.get("available_sheets"):
                st.info({"available_sheets": res.get("available_sheets")})
        else:
            st.error("일치하는 정보가 없습니다. 입력 값을 확인해주세요.")


if __name__ == "__main__":
    main()

