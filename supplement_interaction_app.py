# 실제 기능을 테스트하는 파일
import json
import time
import openai
import requests
import xml.etree.ElementTree as ET
import streamlit as st
from openai import OpenAI
from datetime import datetime, timedelta
from data_fetch import search_pubmed, get_nih_interaction_info
import re

# API 키 로드
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

pubmed_api_key = secrets['pubmed_api_key']
openai_api_key = secrets['openai_api_key']
openai.api_key = openai_api_key

client = OpenAI(api_key=openai_api_key)

# 파인튜닝된 모델 ID 로드
with open('fine_tuned_model_id.txt', 'r') as f:
    fine_tuned_model_id = f.read().strip()

def is_korean(text):
    """
    입력된 텍스트가 한국어인지 확인
    """
    return bool(re.search("[\uac00-\ud7a3]", text))

def translate_with_chatgpt(supplements):
    """
    한국어로 입력된 보충제 이름을 영어로 번역
    """
    prompt = f"""
    Translate the following supplement names into English:
    {', '.join(supplements)}
    Please provide the translations as a comma-separated list.
    """
    try:
        response = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-4o",
            max_tokens=100,
        )
        # 응답에서 번역 결과 추출
        translated_text = response.choices[0].message.content.strip()
        
        # 번역 결과를 리스트로 파싱
        # ChatGPT가 `- 아연: Zinc`와 같은 형식으로 응답하므로 파싱 처리
        if "\n" in translated_text:
            # 줄 단위로 분리
            lines = translated_text.split("\n")
            # 각 줄에서 `:` 뒤의 값만 가져와 리스트 생성
            translated_supplements = [
                line.split(":")[-1].strip() for line in lines if ":" in line
            ]
        else:
            # 단순한 쉼표 구분 결과일 경우
            translated_supplements = [item.strip() for item in translated_text.split(",")]
        
        return translated_supplements
    except Exception as e:
        print(f"번역 오류 발생: {e}")
        return supplements  # 번역 실패 시 원본 반환

def filter_direct_interactions(nih_data, pubmed_articles, supplements):
    """
    NIH 및 PubMed 데이터에서 두 성분 간의 직접적인 상호작용 정보만 추출.
    """
    # NIH 데이터 필터링
    direct_nih_info = []
    for supplement, info in zip(supplements, nih_data):
        if supplements[0] in info and supplements[1] in info:  # 두 성분이 모두 포함된 경우
            direct_nih_info.append(info)

    # PubMed 데이터 필터링
    direct_pubmed_articles = []
    for article in pubmed_articles:
        title_and_abstract = (article["title"] + " " + article["abstract"]).lower()
        if all(supp.lower() in title_and_abstract for supp in supplements):  # 두 성분이 모두 포함된 경우
            direct_pubmed_articles.append(article)

    return direct_nih_info, direct_pubmed_articles

# 영양제 상호작용을 분석하는 함수 (파인튜닝된 모델 사용)
def analyze_interactions(supplements):

# 1. 한국어 여부 확인 및 번역
    if any(is_korean(supp) for supp in supplements):
        translated_supplements = translate_with_chatgpt(supplements)
        print("번역된 보충제 이름:", translated_supplements)  # 디버깅용 출력
    else:
        translated_supplements = supplements  # 영어 입력은 그대로 사용

    nih_data = [get_nih_interaction_info(supplement) for supplement in translated_supplements]
    pubmed_articles = search_pubmed(translated_supplements, pubmed_api_key)

    # 직접적인 상호작용 정보 필터링
    direct_nih_info, direct_pubmed_articles = filter_direct_interactions(nih_data, pubmed_articles, translated_supplements)

    # NIH 및 PubMed 데이터 정리
    nih_text = "\n".join(direct_nih_info) if direct_nih_info else "두 성분 간의 NIH 상호작용 정보가 없습니다."
    articles_text = "\n\n".join([
        f"Title: {a['title']}\nAbstract: {a['abstract']}"
        for a in direct_pubmed_articles
    ]) if direct_pubmed_articles else "두 성분 간의 PubMed 논문이 없습니다."


    # === 디버깅 출력 ===
    print("NIH 데이터:", nih_text)  # NIH 데이터 확인
    print("PubMed 데이터:", articles_text)  # PubMed 데이터 확인
    print(f"검색된 PubMed 논문: {pubmed_articles}")  # PubMed 필터링 결과 확인
    # ===================

    
    prompt = f"""
    다음은 {' 와 '.join(supplements)} 간의 상호작용에 관한 NIH 정보와 PubMed 논문들입니다:

    NIH 정보:
    {nih_text}

    PubMed 논문들:
    {articles_text}

    다음 지침을 따르세요:
    1. 입력된 영양소({', '.join(supplements)}) 간의 상호작용에만 집중하세요.
    2. {', '.join(supplements)} 외에 다른 영양소에 대한 언급은 제외하세요.
    3. 위험한 상호작용이 없는 경우, 이를 명확히 설명하세요.

    NIH와 PubMed 논문에서 위험 관련 정보(예: 흡수 저하, 부작용, 독성 등)가 발견되었다면 이를 명확히 반영하세요. 아래 JSON 형식으로 응답하세요:
    {{
        "risk_description": "위험도에 대한 설명 (다음 중 하나: '안전한 조합이에요. 안심하고 복용하셔도 됩니다.', '주의가 필요해요. 전문가와 상담해보세요.', '위험한 조합이에요. 함께 복용하지 마세요.')",
        "explanation": "위험 또는 안전 근거를 구체적으로 설명하세요. NIH 정보와 PubMed 논문 내용을 바탕으로 간단한 언어로 작성."
    }}
    """


    response = client.chat.completions.create(
        model=fine_tuned_model_id,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=300
    )


    try:
        assistant_message = response.choices[0].message.content.strip()
        print("모델 응답 확인:", assistant_message)  # 디버깅 출력
    
        # JSON 파싱 시도
        if assistant_message.startswith("{") and assistant_message.endswith("}"):
            result_json = json.loads(assistant_message)
            risk_description = result_json.get("risk_description", "결과를 판단할 수 없습니다.")
            explanation = result_json.get("explanation", "결과를 판단할 수 없습니다.")
        else:
            risk_description = "결과를 판단할 수 없습니다."
            explanation = assistant_message  # JSON 형식이 아니더라도 내용 반환

        return risk_description, explanation

    except json.JSONDecodeError as e:
        print("JSONDecodeError 발생:", e, "\n응답 내용:", assistant_message)
        return "결과를 판단할 수 없습니다.", assistant_message  # JSONDecodeError 발생 시 원문 반환
    except Exception as e:
        print("예기치 않은 오류 발생:", e)
        return "결과를 판단할 수 없습니다.", "예기치 않은 오류가 발생했습니다."

# Streamlit 웹 UI에서 상호작용 분석 제공
def run_app():
    st.title("영양제 상호작용 분석기")

    user_input = st.text_input("영양제 이름을 쉼표로 구분하여 입력하세요 (예: 칼슘, 마그네슘)")
    supplements = user_input.split(',')
    supplements = [supp.strip() for supp in supplements if supp.strip()]

    if st.button("분석하기") and supplements:
        with st.spinner('분석 중입니다... 잠시만 기다려주세요.'):
            result = analyze_interactions(supplements)
            #st.write("디버깅: 함수 결과 =", result)  # 디버깅용 출력

            if result and isinstance(result, tuple) and len(result) == 2:
                risk_description, explanation = map(str, result)
            else:
                risk_description, explanation = "결과를 판단할 수 없습니다.", "예기치 않은 오류가 발생했습니다."

        st.write("**영양성분:**", ", ".join(supplements))
        st.write("**결과:**", risk_description)
        st.write("**설명:**", explanation)

if __name__ == "__main__":
    run_app()
