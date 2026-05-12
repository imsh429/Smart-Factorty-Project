import requests
import json
import time
import random
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import os
from dotenv import load_dotenv

load_dotenv()

# API Gateway URL
API_URL = os.getenv("API_URL")

# [실험 변수] 이 수치를 조절하며 실험합니다.
NUM_DEVICES = 50       # 기계 대수를 5대에서 50대로 확장
INTERVAL = 0.01       # 전송 간격 (부하 증가 테스트 때 사용)
ERROR_RATE = 0.05      # 5% 확률로 고장난 데이터(DLQ용) 발송
ANOMALY_RATE = 0.1     # 10% 확률로 이상치(80도 이상) 발송

def send_data(device_id):
    # 1. 에러/이상치/정상 데이터 생성 로직
    rand_val = random.random()
    
    if rand_val < ERROR_RATE:
        # [시나리오] 센서 고장으로 인한 문자열 데이터 (DLQ 유도)
        temp_value = "SENSOR_ERROR"
    elif rand_val < (ERROR_RATE + ANOMALY_RATE):
        # [시나리오] 실제 기계 과열 (이상 탐지 로그 유도)
        temp_value = round(random.uniform(85, 110), 2)
    else:
        # [시나리오] 정상 가동
        temp_value = round(random.uniform(40, 60), 2)

    payload = {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "factory_id": "SEOUL_FACT_01",
        "machine_id": device_id,
        "sensor_type": "temperature",
        "value": temp_value,
        "unit": "Celsius"
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=5)
        print(f"[{device_id}] Status: {response.status_code} | Value: {temp_value}")
    except Exception as e:
        print(f"Error sending from {device_id}: {e}")

def run_factory():
    devices = [f"M_{str(i).zfill(3)}" for i in range(1, NUM_DEVICES + 1)]
    print(f"--- 공장 가동 시작 (기계 {NUM_DEVICES}대, 간격 {INTERVAL}s) ---")
    
    with ThreadPoolExecutor(max_workers=10) as executor: # 병렬 전송
        while True:
            for d_id in devices:
                executor.submit(send_data, d_id)
                time.sleep(INTERVAL / NUM_DEVICES) # 부하 분산

if __name__ == "__main__":
    run_factory()