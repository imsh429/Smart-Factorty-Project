# 🏭 Smart Factory Intelligence

> **클라우드 기반 지능형 스마트 팩토리 통합 관제 시스템**  
> Cloud-Native Real-time Monitoring & Predictive Maintenance

---

## 📌 프로젝트 개요

### 문제 인식
스마트 팩토리 도입으로 초당 수천 개의 IoT 센서 데이터가 발생하는 환경에서, 기존 시스템은 다음과 같은 한계를 가졌습니다.

1. **트래픽 폭주 시 서버 다운** — 단일 처리 구조로 인한 가용성 부재
2. **장애 발생 시 수동 복구의 한계** — 운영 비효율 및 데이터 유실 위험
3. **데이터는 쌓이지만 분석되지 않는 비효율** — 누적 데이터 활용 불가

### 개발 목표
> **Loose Coupling · Serverless · Fault Tolerance**

세 가지 원칙을 기반으로, 데이터 수집부터 이상 탐지·자가 복구·시각화까지 이어지는 완전한 서버리스 파이프라인을 구축했습니다.

---

## 🏗️ 시스템 아키텍처

### 최종 아키텍처 (고도화 후)

```
[IoT 시뮬레이터 - simulator.py]
  50대 가상 기계 (M_001 ~ M_050)
          │
          ▼ HTTP POST
   [API Gateway]  ── SmartFactoryAPI (/ingest POST)
          │
          ▼
  [FactoryIngestFunction - Lambda]
   API GW 데이터 수신 → SNS Topic 발행 (Fan-out 시작점)
          │
          ▼
   [Amazon SNS - factory-data-sns]
          │
    ┌─────┴─────┐
    ▼           ▼
[SQS Queue]  [Storage Lambda]
factory-     SNS → S3에 원본 데이터 직접 저장
data-queue   (raw/year/month/day/machine_id/event_id.json)
    │              └─▶ 실패 시 → [DLQ: factory-data-dlq]
    ▼
[FactoryConsumerFunction - Lambda]
 이상 탐지 (온도 > 80°C) + DynamoDB 저장 전용
    │
    ▼
[DynamoDB - FactoryLatestState]    [S3 - smart-factory-data-seohyeon-2025]
  기계별 최신 상태 (Hot Data)           원시 로그 장기 보관 (Cold Data)
                                              │
                                              ▼
                                       [Amazon Athena]
                                     표준편차 기반 통계 분석
                                              │
                                              ▼
                              [Streamlit Dashboard - app.py]
                               실시간 모니터링 & 예지 보전 UI

※ DLQ 장애 감지 시:
[EventBridge Scheduler] → [Step Functions: factory-data-fault-recovery-flow]
  CheckDLQStatus → HasMessages? → ExecuteReplayLambda (FactoryDataReplay)
  복구 람다가 SNS로 재발행 → DB/S3 양쪽 정상 저장 보장
```

### 아키텍처 진화 과정

| 단계 | 구조 | 문제점 |
|------|------|--------|
| **초기** | API GW → Lambda → SQS → Consumer Lambda (DB저장 + S3저장 통합) | Consumer 하나가 이상탐지·DB·S3를 모두 처리 → 코드 복잡, 쓰로틀링 발생 |
| **고도화** | API GW → Lambda → **SNS Topic** → Consumer Lambda / Storage Lambda (역할 분리) | 장애 격리 + 병렬 처리 + 유지보수 명확화 |

---

## ✨ 주요 기능

### 1. 🌡️ 실시간 장비 상태 모니터링 (Hot Data)
- DynamoDB `FactoryLatestState` 테이블에서 기계별 최신 센서 값 실시간 조회
- `machine_id`, `value`, `timestamp`, `is_anomaly` 기반 현황 테이블 표시

### 2. 🔮 지능형 예지 보전 알림 (Cold Data)
- Athena로 S3 누적 데이터에서 기계별 온도 **표준편차(불안정 지수)** 산출
- 불안정 지수 > `5.0` 초과 장비를 **잠재적 결함 징후**로 자동 탐지 및 경고 카드 표시

```sql
-- Athena 예지 보전 쿼리
SELECT machine_id,
       ROUND(STDDEV(value), 2) AS instability,  -- 불안정 지수
       ROUND(AVG(value), 2)    AS avg_value,
       COUNT(*)                AS record_count
FROM "factory_db"."sensor_data"
GROUP BY machine_id
ORDER BY instability DESC;
```

### 3. 🚨 Fault Tolerance & 자동 복구
- SQS DLQ에 쌓인 오류 메시지를 실시간 감지
- **EventBridge 스케줄러** → **Step Functions** 자동 실행 → `FactoryDataReplay` 람다 호출
    - 재시도 횟수 < 3회: SNS로 재발행 → DB/S3 양쪽 정상 저장
    - 재시도 횟수 ≥ 3회: S3 별도 격리 저장 + SNS 위험 알림 발송

### 4. 📊 KPI 대시보드
| 지표 | 설명 |
|------|------|
| 시스템 건전성 | DLQ 메시지 유무에 따른 안정/위험 상태 |
| 총 누적 데이터(S3) | Athena로 집계한 전체 센서 레코드 수 |
| 미처리 메시지(DLQ) | 처리 실패한 오류 메시지 건수 |

### 5. 🔍 분석 탭
- **통계 분석**: 상위 20개 장비 불안정 지수 Plotly 바차트
- **상세 로그**: 전체 Athena 분석 리포트 테이블

---

## 📁 프로젝트 구조

```
Smart-Factory-Project/
├── app.py                # Streamlit 메인 대시보드
├── simulator.py          # IoT 센서 데이터 시뮬레이터
├── requirements.txt      # Python 패키지 목록
├── 프로젝트_보고서.pdf    # 프로젝트 상세 보고서
└── .gitignore
```

> Lambda 함수 코드(`FactoryIngestFunction`, `FactoryConsumerFunction`, `storageLambda`, `FactoryDataReplay`)는 AWS 콘솔에서 직접 관리되어 별도 파일로 포함되지 않습니다.

---

## 🛠️ 기술 스택

### AWS 서비스

| 서비스 | 역할 |
|--------|------|
| **API Gateway** (`SmartFactoryAPI`) | IoT 데이터 수신 RESTful 엔드포인트 (`/ingest POST`) |
| **AWS Lambda** × 4 | Ingest / Consumer / Storage / Replay 역할 분리 |
| **Amazon SNS** (`factory-data-sns`) | 팬아웃(Fan-out) 메시지 브로커 |
| **Amazon SQS** (`factory-data-queue`) | 비동기 메시지 버퍼 (Decoupling) |
| **Amazon SQS DLQ** (`factory-data-dlq`) | 처리 실패 메시지 Dead Letter Queue |
| **Amazon DynamoDB** (`FactoryLatestState`) | 기계별 최신 상태 Hot Storage |
| **Amazon S3** (`smart-factory-data-seohyeon-2025`) | 원시 데이터 Cold Storage (날짜/기계 파티션) |
| **Amazon Athena** | S3 데이터 SQL 통계 분석 (표준편차 기반 예지 보전) |
| **AWS Step Functions** | 자가 복구 워크플로우 오케스트레이션 |
| **Amazon EventBridge** | Step Functions 주기적 자동 실행 스케줄러 |
| **Amazon CloudWatch** | 인프라 전 계층 모니터링 대시보드 |

### 왜 Kinesis 대신 SQS를 선택했나?

| 비교 항목 | SQS ✅ | Kinesis |
|-----------|--------|---------|
| 확장성 | 거의 무제한 자동 확장 | 샤드 개수에 따라 수동 확장 필요 |
| 비용 | 사용한 만큼만 지불 | 시간당 샤드 유지 비용 발생 |
| 복잡도 | Lambda 연동 쉬움 | 샤드 관리 및 설정 필요 |
| 적합성 | 발생 즉시 판별이 중요한 시나리오에 적합 | 대규모 순서 보장 스트리밍에 적합 |

### Frontend / Visualization

| 라이브러리 | 역할 |
|------------|------|
| **Streamlit** | 웹 대시보드 UI |
| **Plotly Express** | 인터랙티브 차트 |
| **Pandas** | 데이터 처리 |
| **boto3** | AWS SDK |

---

## 🤖 IoT 시뮬레이터 스펙

| 항목 | 값 |
|------|----|
| 가상 기계 수 | 50대 (`M_001` ~ `M_050`) |
| 정상 온도 범위 | 40 ~ 60°C |
| 이상치 온도 범위 | 85 ~ 110°C (발생 확률 10%) |
| 오류 데이터 비율 | 5% (`SENSOR_ERROR` → DLQ 유도) |
| 전송 간격 | 0.01s (부하 테스트 시 조절) |
| 병렬 전송 | `ThreadPoolExecutor` (10 workers) |
| Factory ID | `SEOUL_FACT_01` |

---

## ⚙️ 환경 설정

### 1. 패키지 설치

```bash
pip install -r requirements.txt
pip install streamlit boto3 pandas plotly python-dotenv
```

### 2. 환경 변수 설정 (`.env`)

```env
# AWS 기본 설정
REGION=ap-northeast-2

# Athena
DATABASE=factory_db
OUTPUT_S3=s3://smart-factory-data-seohyeon-2025/athena-results/

# DynamoDB
DYNAMO_TABLE=FactoryLatestState

# SQS DLQ
DLQ_NAME=factory-data-dlq

# Step Functions
STATE_MACHINE_ARN=arn:aws:states:ap-northeast-2:xxxxxxxxxxxx:stateMachine:factory-data-fault-recovery-flow

# API Gateway (시뮬레이터용)
API_URL=https://wnfb6kkl9c.execute-api.ap-northeast-2.amazonaws.com/ingest
```

### 3. AWS 자격 증명

```bash
aws configure
```

필요 IAM 권한: `AmazonAthenaFullAccess`, `AmazonDynamoDBReadOnlyAccess`, `AmazonSQSReadOnlyAccess`, `AWSStepFunctionsFullAccess`, `AmazonS3ReadOnlyAccess`

---

## 🚀 실행 방법

### 시뮬레이터 실행 (IoT 데이터 생성)

```bash
python simulator.py
```

```
--- 공장 가동 시작 (기계 50대, 간격 0.01s) ---
[M_001] Status: 200 | Value: 52.37
[M_002] Status: 200 | Value: 48.55
[M_003] Status: 200 | Value: SENSOR_ERROR   ← DLQ 유도
[M_004] Status: 200 | Value: 97.14          ← 이상치 탐지
```

### 대시보드 실행

```bash
streamlit run app.py
```

> 브라우저에서 `http://localhost:8501` 접속

---

## 📊 데이터 스키마

```json
{
  "event_id":    "uuid-v4",
  "timestamp":   "2025-12-20T13:07:11",
  "factory_id":  "SEOUL_FACT_01",
  "machine_id":  "M_001",
  "sensor_type": "temperature",
  "value":       46.33,
  "unit":        "Celsius",
  "is_anomaly":  false
}
```

S3 저장 경로: `raw/year={YYYY}/month={MM}/day={DD}/{machine_id}/{event_id}.json`

---

## 🔄 Fault Tolerance 동작 흐름

```
정상 데이터: SNS → SQS → Consumer Lambda → DynamoDB ✅
                └─→ Storage Lambda → S3 ✅

오류 데이터: SNS → SQS → Consumer Lambda 처리 실패
                         → DLQ(factory-data-dlq) 격리

자동 복구:  EventBridge (주기적) → Step Functions 실행
             └─▶ CheckDLQStatus: DLQ 메시지 존재?
                  ├─ Yes → ExecuteReplayLambda (FactoryDataReplay)
                  │         ├─ 재시도 < 3회: SNS 재발행 → DB/S3 정상 저장
                  │         └─ 재시도 ≥ 3회: S3 격리 저장 + SNS 위험 알림
                  └─ No  → Finished (정상 종료)
```

**개선 효과:**
- **데이터 유실 Zero** — DLQ 보관 후 복구 람다가 SNS로 재발행, DB/S3 모두 정상 저장 확인
- **수동 복구 자동화** — Step Functions가 정해진 시간에 자동 실행
- **에러 분석 환경** — 반복 실패 데이터는 격리 후 별도 분석 가능

---

## 💡 개발 회고

1. **회복력 있는 시스템의 중요성** — 실제 트래픽을 넣어보니 장애는 언제든 날 수 있다는 것을 알았습니다. 에러를 막는 것보다 스스로 복구하는 탄력적 아키텍처가 왜 클라우드의 핵심인지 직접 체감했습니다.

2. **아키텍처 수정 시 데이터 정합성** — 단순히 SQS로 복구하면 S3 저장 경로가 누락되는 문제를 발견했고, 복구 지점을 SNS Topic으로 상향 조정하면서 서비스 간 결합도를 낮추고 데이터 정합성을 완벽하게 맞췄을 때 가장 큰 성취감을 느꼈습니다.

3. **현실적인 제약 안에서의 최적화** — 비용 문제로 Kinesis 대신 SQS를 선택했지만, 오히려 각 서비스의 비용 대비 성능을 꼼꼼히 따져보는 경험을 할 수 있었습니다.

**앞으로의 계획:** 이번에 구축한 파이프라인에 SageMaker 같은 AI 모델을 붙여서, 단순 통계를 넘어선 AI 기반 예지 보전 시스템으로 발전시킬 예정입니다.

---

## 📄 라이선스

MIT License © 2026 [imsh429](https://github.com/imsh429)