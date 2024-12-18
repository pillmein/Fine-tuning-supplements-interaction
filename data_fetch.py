import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# PubMed API 함수
def search_pubmed(supplements, pubmed_api_key):
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
     # 상호작용 관련 키워드
    keywords = ["negative interaction", "adverse effects", "interaction risk", "adverse effects", "contraindications"]
    articles = []
    collected_article_ids = set()

    # 최근 5년 이내 논문만 검색
    start_date = (datetime.now() - timedelta(days=5*365)).strftime('%Y/%m/%d')

    # 모든 supplements를 조합하여 검색 쿼리 생성
    if len(supplements) > 1:
        supplement_combination = " AND ".join(supplements)
    else:
        supplement_combination = supplements[0]

    for keyword in keywords:
        # 조합된 영양제 성분과 키워드를 하나의 검색어로 사용
        search_term = f"{supplement_combination} AND {keyword}"
        search_url = f"{base_url}/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": search_term,
            "retmax": 10,  
            "api_key": pubmed_api_key,
            "retmode": "json",
            "mindate": start_date,
            "datetype": "pdat"
        }

        response = requests.get(search_url, params=params)
        time.sleep(0.5)

        if response.status_code != 200:
            continue

        data = response.json()
        article_ids = data["esearchresult"]["idlist"]

        # 중복 논문 ID 제거
        unique_article_ids = [aid for aid in article_ids if aid not in collected_article_ids]
        collected_article_ids.update(unique_article_ids)

        if unique_article_ids:
            fetch_url = f"{base_url}/efetch.fcgi"
            params = {
                "db": "pubmed",
                "id": ",".join(unique_article_ids),
                "retmode": "xml"
            }

            response = requests.get(fetch_url, params=params)
            time.sleep(0.5)

            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for article in root.findall(".//PubmedArticle"):
                    title_elem = article.find(".//ArticleTitle")
                    abstract_elem = article.find(".//AbstractText")

                    # 제목 및 초록 추출
                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    abstract = abstract_elem.text.strip() if abstract_elem is not None and abstract_elem.text else ""

                    # 제목 또는 초록에 모든 보충제 이름이 포함된 경우만 추가
                    if all(supp.lower() in (title + abstract).lower() for supp in supplements):
                        articles.append({
                            "title": title,
                            "abstract": abstract
                        })
    
    return articles

# NIH ODS API 함수
def get_nih_interaction_info(supplement_name):
    base_url = "https://ods.od.nih.gov/api/"
    params = {
        "resourcename": supplement_name,
        "readinglevel": "Health Professional",
        "outputformat": "XML"
    }

    # API 요청
    response = requests.get(base_url, params=params)

    if response.status_code != 200:
        return "NIH 데이터에 접근할 수 없습니다."

    # XML 응답 파싱
    root = ET.fromstring(response.content)

    # 네임스페이스 처리
    namespace = {'ns': 'http://tempuri.org/factsheet.xsd'}
    content = root.find(".//ns:Content", namespaces=namespace)

    if content is not None:
        content_text = ET.tostring(content, encoding='unicode', method='text')
    else:
        return "상호작용 정보가 포함된 Content 태그를 찾을 수 없습니다."

    # 상호작용 관련 정보 추출
    interaction_keyword = "Interactions with Medications"
    interaction_info = []

    if interaction_keyword in content_text:
        lines = content_text.split('\n')
        record = False
        for line in lines:
            if interaction_keyword in line:
                record = True
            if record:
                interaction_info.append(line)

    return "\n".join(interaction_info) if interaction_info else "상호작용 정보가 없습니다."
