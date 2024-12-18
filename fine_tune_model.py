# 파인튜닝용 파일
import json
import time
import openai
import requests
import xml.etree.ElementTree as ET
from openai import OpenAI
from datetime import datetime, timedelta
from data_fetch import search_pubmed, get_nih_interaction_info

# API 키 로드
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

pubmed_api_key = secrets['pubmed_api_key']
openai_api_key = secrets['openai_api_key']
openai.api_key = openai_api_key

# 데이터 수집 및 JSONL 파일 생성 함수
supplements = [
    "Iron", "Calcium", "Magnesium", "Zinc"]
#"Zinc", "Vitamin D", "Iron", "Vitamin B12", "Folic Acid","Vitamin E", "Vitamin K", "Probiotics", "Collagen", "Biotin", "Melatonin", "Coenzyme Q10", "Ashwagandha","Turmeric", "Ginger", "Garlic", "Ginseng", "Green Tea Extract", "Curcumin", "Resveratrol", "L-Theanine"

def create_training_data_file(supplements):
    interaction_data = []

    for supplement in supplements:
        # NIH 데이터 수집
        nih_info = get_nih_interaction_info(supplement)
        if nih_info:
            interaction_data.append({
                "messages": [
                    {"role": "user", "content": f"What are the interactions of {supplement}?"},
                    {"role": "assistant", "content": nih_info}
                ]
            })

        # PubMed 데이터 수집
        pubmed_articles = search_pubmed([supplement], pubmed_api_key)
        if pubmed_articles:
            for article in pubmed_articles:
                interaction_data.append({
                    "messages": [
                        {"role": "user", "content": f"What does research say about {supplement}?"},
                        {"role": "assistant", "content": f"Title: {article['title']}\nAbstract: {article['abstract']}"}
                    ]
                })

    output_file = 'nih_pubmed_supplement_interactions_expanded.jsonl'
    with open(output_file, 'w', encoding='utf-8') as f:
        for data in interaction_data:
            f.write(json.dumps(data, ensure_ascii=False) + '\n')

    print(f"JSONL 파일 '{output_file}'이 생성되었습니다.")
    return output_file

# 파인튜닝 작업 생성
def fine_tune_model():
    client = OpenAI(api_key=openai_api_key)
    training_data_file = create_training_data_file(supplements)

    #파일 업로드
    upload_response = client.files.create(
        file=open(training_data_file, "rb"),
        purpose="fine-tune"
    )

    #파일 id 접근
    training_file_id = upload_response.id

    #파인튜닝 작업 생성
    fine_tune_response = client.fine_tuning.jobs.create(
    training_file=training_file_id,
    model="gpt-4o-mini-2024-07-18"
    )

    #파인튜닝 작업 id
    fine_tune_id = fine_tune_response.id
    print("파인튜닝 작업이 진행 중입니다. 완료될 때까지 기다려 주세요...")

    fine_tuned_model_id = None

    while True:
        #파인튜닝 작업 상태 확인
        fine_tune_status_response = client.fine_tuning.jobs.retrieve(fine_tune_id)
        status = fine_tune_status_response.status

        if status == "succeeded":
            # 작업이 완료되었으면 모델 ID 가져오기
            fine_tuned_model_id = fine_tune_status_response.fine_tuned_model
            print(f"파인튜닝 작업 완료. 모델 ID: {fine_tuned_model_id}")
            # 모델 ID를 파일에 저장
            with open('fine_tuned_model_id.txt', 'w') as model_file:
                model_file.write(fine_tuned_model_id)
            break
        elif status == "failed":
            print("파인튜닝 작업이 실패했습니다.")
            print(f"오류 메시지: {fine_tune_status_response.error}")
            break
        else:
            # 작업이 아직 완료되지 않았으면 30초 후 다시 확인
            time.sleep(30)
            print(f"현재 상태: {status}... 계속 대기 중...")

    if fine_tuned_model_id is None:
        raise Exception("파인튜닝 작업이 실패하거나 모델 ID를 가져올 수 없습니다.")

if __name__ == "__main__":
    fine_tune_model()

