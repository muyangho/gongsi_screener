import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import zipfile
import io
import xml.etree.ElementTree as ET

# --- API Endpoints ---
DART_LIST_API = "https://opendart.fss.or.kr/api/list.json"
DART_CONTRACT_API = "https://opendart.fss.or.kr/api/sscpktsl.json"          # 단일판매
DART_EQUITY_API = "https://opendart.fss.or.kr/api/piicDecsn.json"            # 유상증자
DART_INVEST_API = "https://opendart.fss.or.kr/api/otcprStkInvsmentDcsn.json" # 타법인출자
DART_FREE_ISSUE_API = "https://opendart.fss.or.kr/api/fricDecsn.json"        # 무상증자
DART_CB_API = "https://opendart.fss.or.kr/api/cvbdIsDecsn.json"              # 전환사채(CB)
DART_TREASURY_API = "https://opendart.fss.or.kr/api/tsstkAqDecsn.json"       # 자기주식취득

st.set_page_config(page_title="퀀트 공시 스크리너 V3", layout="wide")

@st.cache_data(ttl=86400)
def get_corp_code_mapping(api_key):
    """6자리 종목코드를 DART 8자리 고유번호로 매핑"""
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    res = requests.get(url, params={'crtfc_key': api_key})
    mapping = {}
    if res.status_code == 200:
        try:
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                xml_data = z.read('CORPCODE.xml')
            root = ET.fromstring(xml_data)
            for item in root.findall('list'):
                stock_code = item.find('stock_code').text
                corp_code = item.find('corp_code').text
                if stock_code and stock_code.strip():
                    mapping[stock_code.strip()] = corp_code.strip()
        except Exception as e:
            st.error(f"고유번호 매핑 실패: {e}")
    return mapping

def get_recent_filings(api_key, bgn_de, end_de, corp_code=""):
    params = {'crtfc_key': api_key, 'bgn_de': bgn_de, 'end_de': end_de, 'page_no': 1, 'page_count': 100}
    if corp_code:
        params['corp_code'] = corp_code
    response = requests.get(DART_LIST_API, params=params)
    if response.status_code == 200:
        data = response.json()
        if data.get('status') == '000':
            return data.get('list', [])
    return []

# --- 개별 공시 분석 함수들 ---
def parse_contract(api_key, corp_code, rcept_no):
    params = {'crtfc_key': api_key, 'corp_code': corp_code, 'bns_dt': datetime.today().strftime('%Y')}
    res = requests.get(DART_CONTRACT_API, params=params).json()
    if res.get('status') == '000':
        for item in res['list']:
            if item['rcept_no'] == rcept_no:
                contract_amt = int(item.get('cntrct_amt', 0).replace(',', ''))
                sales_amt = int(item.get('srtm_sls_amt', 0).replace(',', ''))
                ratio = (contract_amt / sales_amt * 100) if sales_amt > 0 else 0
                return f"계약금: {contract_amt:,}원 (매출대비 {ratio:.1f}%)"
    return "-"

def parse_equity(api_key, corp_code, rcept_no):
    params = {'crtfc_key': api_key, 'corp_code': corp_code, 'bns_dt': datetime.today().strftime('%Y')}
    res = requests.get(DART_EQUITY_API, params=params).json()
    if res.get('status') == '000':
        for item in res['list']:
            if item['rcept_no'] == rcept_no:
                return f"방식: {item.get('allo_mthd', 'N/A')} | 발행가: {item.get('nstk_est_is_prc', 'N/A')}원"
    return "-"

def parse_invest(api_key, corp_code, rcept_no):
    params = {'crtfc_key': api_key, 'corp_code': corp_code, 'bns_dt': datetime.today().strftime('%Y')}
    res = requests.get(DART_INVEST_API, params=params).json()
    if res.get('status') == '000':
        for item in res['list']:
            if item['rcept_no'] == rcept_no:
                return f"목적: {item.get('acq_purps', 'N/A')} | 금액: {item.get('acq_amt', 'N/A')}원"
    return "-"

def parse_free_issue(api_key, corp_code, rcept_no):
    params = {'crtfc_key': api_key, 'corp_code': corp_code, 'bns_dt': datetime.today().strftime('%Y')}
    res = requests.get(DART_FREE_ISSUE_API, params=params).json()
    if res.get('status') == '000':
        for item in res['list']:
            if item['rcept_no'] == rcept_no:
                ratio = item.get('nstk_asn_1_stk_rt', 'N/A')
                return f"🔥 1주당 신주배정: {ratio}주 (비율이 높을수록 폭발적 호재)"
    return "-"

def parse_cb(api_key, corp_code, rcept_no):
    params = {'crtfc_key': api_key, 'corp_code': corp_code, 'bns_dt': datetime.today().strftime('%Y')}
    res = requests.get(DART_CB_API, params=params).json()
    if res.get('status') == '000':
        for item in res['list']:
            if item['rcept_no'] == rcept_no:
                ops_fund = item.get('op_fnd', '0')
                fac_fund = item.get('fclt_fnd', '0')
                invest_fund = item.get('otcpr_scrt_acq_fnd', '0')
                purpose = []
                if ops_fund != '0' and ops_fund != '-': purpose.append("운영(악재성)")
                if fac_fund != '0' and fac_fund != '-': purpose.append("시설(호재성)")
                if invest_fund != '0' and invest_fund != '-': purpose.append("타법인취득(M&A)")
                return f"⚠️ 목적: {', '.join(purpose) if purpose else '기타'} | 만기이자율: {item.get('mty_ir', 'N/A')}%"
    return "-"

def parse_treasury(api_key, corp_code, rcept_no):
    params = {'crtfc_key': api_key, 'corp_code': corp_code, 'bns_dt': datetime.today().strftime('%Y')}
    res = requests.get(DART_TREASURY_API, params=params).json()
    if res.get('status') == '000':
        for item in res['list']:
            if item['rcept_no'] == rcept_no:
                amt = item.get('aq_estm_amt', '0')
                return f"💰 취득예정금액: {amt}원"
    return "-"


# --- UI 레이아웃 ---
st.title("📈 주가 모멘텀 & 가이던스 실시간 스크리너")
st.markdown("시장에 강한 임팩트를 주는 **무상증자, 자사주 취득, 전환사채(CB), 단일판매, 가이던스(IR)** 공시만 솎아냅니다.")

st.sidebar.header("설정")
api_key = st.sidebar.text_input("OpenDART API Key", type="password")
user_input_code = st.sidebar.text_input("종목코드 (6자리) 또는 고유번호", placeholder="비워두면 시장 전체 조회")
days_ago = st.sidebar.slider("조회 기간(일)", 1, 30, 1)

if st.sidebar.button("핵심 모멘텀 공시 스캔"):
    if not api_key:
        st.warning("API Key를 입력해주세요.")
    else:
        target_corp_code = ""
        if user_input_code:
            user_input_code = user_input_code.strip()
            if len(user_input_code) == 6:
                with st.spinner("종목코드 매핑 중..."):
                    code_map = get_corp_code_mapping(api_key)
                    target_corp_code = code_map.get(user_input_code)
                    if not target_corp_code:
                        st.error("DART 고유번호를 찾을 수 없습니다.")
                        st.stop()
            else:
                target_corp_code = user_input_code

        bgn_de = (datetime.today() - timedelta(days=days_ago)).strftime('%Y%m%d')
        end_de = datetime.today().strftime('%Y%m%d')

        with st.spinner("공시 데이터를 스캔하고 있습니다..."):
            filings = get_recent_filings(api_key, bgn_de, end_de, target_corp_code)
            
            if not filings:
                st.info("조건에 맞는 공시가 없습니다.")
            else:
                results = []
                for f in filings:
                    title = f.get('report_nm', '')
                    rcp_no = f.get('rcept_no', '')
                    ccode = f.get('corp_code', '')
                    company = f.get('corp_nm', '이름없음')
                    date = f.get('rcept_dt', '')
                    
                    summary, category, impact = "", "", ""
                    
                    # 1. 단일판매·공급계약 (실적 모멘텀)
                    if "단일판매" in title and "공급계약" in title:
                        category, impact = "공급계약", "🟢 매출"
                        summary = parse_contract(api_key, ccode, rcp_no)
                        
                    # 2. 무상증자 결정 (초대형 모멘텀)
                    elif "무상증자" in title and "결정" in title:
                        category, impact = "무상증자", "🔥 🚀 강세"
                        summary = parse_free_issue(api_key, ccode, rcp_no)
                        
                    # 3. 자기주식 (주주환원/밸류업)
                    elif "자기주식" in title and ("취득" in title or "소각" in title):
                        category, impact = "자사주(주주환원)", "💰 호재"
                        summary = parse_treasury(api_key, ccode, rcp_no) if "취득" in title else "주식 소각 (강력한 호재)"
                        
                    # 4. 전환사채(CB) / 신주인수권(BW) (희석 리스크 or M&A)
                    elif "전환사채" in title or "신주인수권" in title:
                        category, impact = "메자닌(CB/BW)", "⚠️ 목적확인"
                        summary = parse_cb(api_key, ccode, rcp_no)
                        
                    # 5. 유상증자
                    elif "유상증자" in title:
                        category, impact = "유상증자", "⚠️ 배정확인"
                        summary = parse_equity(api_key, ccode, rcp_no)
                        
                    # 6. IR / 공정공시 (포워드 가이던스)
                    elif "기업설명회" in title or "공정공시" in title:
                        category, impact = "가이던스(IR)", "📢 전망"
                        summary = "향후 매출 목표 또는 사업 방향성 제시 (원문 참조)"
                        
                    if category:
                        results.append({
                            "시간/일자": date,
                            "기업명": company,
                            "성격": impact,
                            "분류": category,
                            "보고서명": title,
                            "핵심 포인트 (API 자동분석)": summary,
                            "링크": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}"
                        })
                
                if results:
                    df = pd.DataFrame(results)
                    st.success(f"시장 핵심 모멘텀 공시 {len(df)}건 스캔 완료!")
                    st.data_editor(
                        df,
                        column_config={"링크": st.column_config.LinkColumn("원문 보기")},
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("해당 기간에 시장을 움직일 만한 타겟 공시가 없습니다.")