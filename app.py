import streamlit as st
import pandas as pd
import boto3
import time
import plotly.express as px
from botocore.exceptions import ClientError
import os
from dotenv import load_dotenv

load_dotenv()

# --- [설정] AWS 환경 변수 ---
REGION = os.getenv("REGION")
DATABASE = os.getenv("DATABASE")
OUTPUT_S3 = os.getenv("OUTPUT_S3")
DLQ_NAME = os.getenv("DLQ_NAME")
DYNAMO_TABLE = os.getenv("DYNAMO_TABLE")
STATE_MACHINE_ARN = os.getenv("STATE_MACHINE_ARN")

# 분석 임계치 (표준편차 기반)
INSTABILITY_THRESHOLD = 5.0

st.set_page_config(page_title="Smart Factory Intelligence", layout="wide", initial_sidebar_state="expanded")

# --- [스타일링] CSS 강화 ---
st.markdown("""
    <style>
    html, body, [class*="st-"] { font-size: 1.1rem !important; }
    h1 { font-size: 3.5rem !important; font-weight: 800 !important; color: #FF4B4B !important; }
    h2, h3 { font-size: 2.2rem !important; font-weight: 700 !important; }
    [data-testid="stMetricValue"] { font-size: 2.8rem !important; font-weight: bold !important; }
    </style>
    """, unsafe_allow_html=True)

# --- [함수 1] Athena: 통계 및 이력 분석 (Cold Data) ---
@st.cache_data(ttl=60)
def run_athena_query(query):
    client = boto3.client('athena', region_name=REGION)
    response = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={'Database': DATABASE},
        ResultConfiguration={'OutputLocation': OUTPUT_S3}
    )
    query_id = response['QueryExecutionId']
    while True:
        status = client.get_query_execution(QueryExecutionId=query_id)['QueryExecution']['Status']['State']
        if status in ['SUCCEEDED', 'FAILED', 'CANCELLED']: break
        time.sleep(0.5)
    
    if status == 'SUCCEEDED':
        s3_client = boto3.client('s3')
        bucket = OUTPUT_S3.split('/')[2]
        key = f"athena-results/{query_id}.csv"
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        return pd.read_csv(obj['Body'])
    return pd.DataFrame()

# --- [함수 2] DynamoDB: 실시간 현재 상태 조회 (Hot Data) ---
def get_latest_status():
    try:
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        table = dynamodb.Table(DYNAMO_TABLE)
        response = table.scan() # 기계 수가 수천 대 미만일 때 효율적
        return pd.DataFrame(response['Items'])
    except Exception as e:
        st.error(f"DynamoDB 데이터 로드 실패: {e}")
        return pd.DataFrame()

# --- [함수 3] SQS: DLQ 메시지 확인 ---
def get_dlq_count():
    try:
        sqs = boto3.client('sqs', region_name=REGION)
        queue_url = sqs.get_queue_url(QueueName=DLQ_NAME)['QueueUrl']
        response = sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=['ApproximateNumberOfMessages'])
        return int(response['Attributes']['ApproximateNumberOfMessages'])
    except: return 0

# --- [함수 4] Step Functions: 자가 복구 실행 ---
def trigger_self_healing():
    try:
        sfn = boto3.client('stepfunctions', region_name=REGION)
        sfn.start_execution(stateMachineArn=STATE_MACHINE_ARN)
        return True
    except Exception as e:
        st.sidebar.error(f"복구 실행 실패: {e}")
        return False

# --- 데이터 로딩 ---
with st.spinner('실시간 인프라 데이터를 동기화 중입니다...'):
    # Athena 분석 데이터
    vol_df = run_athena_query(f"SELECT machine_id, round(stddev(value), 2) as instability, avg(value) as avg_value FROM sensor_data GROUP BY machine_id ORDER BY instability DESC")
    total_data_count = run_athena_query("SELECT count(*) as cnt FROM sensor_data")
    # DynamoDB 실시간 데이터
    current_status_df = get_latest_status()

# --- 사이드바: 제어판 ---
st.sidebar.title("🛠️ 운영 제어판")
dlq_num = get_dlq_count()

if dlq_num > 0:
    st.sidebar.warning(f"⚠️ 장애 데이터 {dlq_num}건 감지")
    if st.sidebar.button('🚀 자가 복구(Step Functions) 가동', use_container_width=True):
        if trigger_self_healing():
            st.sidebar.success("복구 프로세스 시작됨!")
            time.sleep(2)
            st.rerun()
else:
    st.sidebar.success("✅ 시스템 정상 작동 중")

if st.sidebar.button('🔄 데이터 강제 새로고침', use_container_width=True):
    st.rerun()

# --- 메인 대시보드 화면 ---
st.title("🏭 Smart Factory Intelligence")
st.markdown("### **Real-time Monitoring & Predictive Maintenance**")

# 1. KPI Metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("시스템 건전성", "안정" if dlq_num == 0 else "위험", delta=-dlq_num)
m2.metric("총 누적 데이터(S3)", f"{total_data_count['cnt'][0]:,}")
#m3.metric("활성 장비 수", f"{len(current_status_df)}대")
m4.metric("미처리 메시지(DLQ)", f"{dlq_num}건")

st.divider()

# 2. 실시간 현황 섹션 (DynamoDB 활용)
st.subheader("🌡️ 기계별 실시간 현재 상태 (Hot Data - DynamoDB)")
if not current_status_df.empty:
    # 온도에 따라 색상 하이라이트
    st.dataframe(
        current_status_df[['machine_id', 'value', 'timestamp']].sort_values('machine_id'),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("실시간 데이터를 불러오는 중입니다.")

# 3. 예지 보전 섹션 (Athena 통계 활용)
st.divider()
unstable_targets = vol_df[vol_df['instability'] > INSTABILITY_THRESHOLD]
if not unstable_targets.empty:
    st.error(f"## 🚨 분석 결과: {len(unstable_targets)}대의 장비에서 잠재적 결함 징후 포착")
    with st.container(height=350):
        cols_per_row = 4
        for i in range(0, len(unstable_targets), cols_per_row):
            row_targets = unstable_targets.iloc[i : i + cols_per_row]
            cols = st.columns(cols_per_row)
            for j, (_, row) in enumerate(row_targets.iterrows()):
                with cols[j]:
                    st.warning(f"**ID: {row['machine_id']}**\n\n불안정 지수: `{row['instability']}`")

# 4. 분석 탭
tab1, tab2 = st.tabs(["🕒 통계 분석", "🔍 상세 로그"])
with tab1:
    st.markdown("### **장비별 온도 변동성 분석 (Athena)**")
    fig = px.bar(vol_df.head(20), x='machine_id', y='instability', color='instability', 
                 title="상위 20개 장비 불안정 지수", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown("### **전체 분석 리포트**")
    st.table(vol_df.head(10))