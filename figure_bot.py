import os
import time
import random
import json
from supabase import create_client, Client
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 1. Supabase 및 OpenAI 정보 설정
SUPABASE_URL = "https://qgxvmqhotuzrwbqvvsfq.supabase.co"
SUPABASE_KEY = "sb_publishable_rmcVzlVyr2SOLaf8XeIncg_3Q2CI4n3"
import os

# ✅ 컴퓨터나 깃허브 시크릿에 설정된 환경 변수에서 안전하게 가져옵니다.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 🔍 수집 키워드 및 페이지 범위 설정
search_keyword = "넨도로이드"
start_p = 1
end_p = 1

ua_list = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

def analyze_and_save_with_ai(raw_text, candidate_image_urls, page_url):
    print("🤖 AI가 피규어 스펙, 카테고리, 한줄평 및 사진 3장을 분석 중입니다...")
    
    prompt = f"""
    다음은 쇼핑몰 피규어 상세 페이지에서 긁어온 텍스트와 이미지 URL 후보들입니다.
    이 페이지의 정보를 분석해서 아래 JSON 형식으로만 응답해주세요 (다른 설명 없이):

    - title: 피규어 정확한 상품명 (풀네임)
    - manufacturer: 제조사/브랜드 (예: 굿스마일 컴퍼니, 맥스팩토리 등)
    - scale_size: 크기 및 전고 (예: 약 140mm 등)
    - release_date: 발매년월 (예: 2027-06)
    - category: 작품 장르 분류 ('애니메이션', '게임', '보컬로이드', 'VTuber', '기타' 중 택1)
    - figure_type: 피규어 타입 분류 ('넨도로이드/SD', '스케일/스테츄', '누들 스토퍼', '액션 피규어', '기타' 중 택1)
    - images: 배너, 로고, 사은품 이미지를 제외한 순수 상품 대표 이미지 URL을 품질 좋은 순서대로 정확히 3개 뽑아서 배열로 제공 (예: ["url1", "url2", "url3"])
    - price: 판매가격 (숫자만, 예: 92900)
    - ai_review: 마니아 관점에서의 피규어 특징과 매력을 담은 친근한 AI 한줄평 (1~2문장)

    수집된 텍스트:
    {raw_text}

    이미지 URL 후보 리스트:
    {json.dumps(candidate_image_urls)}
    """

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        
        title = result.get('title')
        manufacturer = result.get('manufacturer', '미정')
        scale = result.get('scale_size', '정보없음')
        release_date = result.get('release_date', '정보없음')
        category = result.get('category', '기타')
        figure_type = result.get('figure_type', '스케일/스테츄')
        ai_review = result.get('ai_review', '멋진 피규어입니다.')
        price_val = int(str(result.get("price", "0")).replace(",", ""))

        # 이미지 3장 추출 및 매핑
        images = result.get('images', [])
        img1 = images[0] if len(images) > 0 else 'https://via.placeholder.com/300'
        img2 = images[1] if len(images) > 1 else ''
        img3 = images[2] if len(images) > 2 else ''

        print(f"✨ AI 분석 완료: {title}")
        print(f"   └ 장르: {category} / 타입: {figure_type}")
        print(f"   └ 수집된 이미지 수: {len(images)}장")

        # 1. figures 테이블에 상세 스펙 및 이미지 3장 저장
        figure_data, _ = supabase.table("figures").insert({
            "title": title,
            "manufacturer": manufacturer,
            "scale": scale,
            "release_date": release_date,
            "image_url1": img1,
            "image_url2": img2,
            "image_url3": img3,
            "image_url": img1, # 메인 카드용 대표 이미지
            "description": ai_review,
            "category": category,
            "figure_type": figure_type
        }).execute()

        figure_id = figure_data[1][0]['id']

        # 2. figure_shops 테이블에 가격 및 링크 저장
        supabase.table("figure_shops").insert({
            "figure_id": figure_id,
            "shop_name": "매니아하우스",
            "price": price_val,
            "shop_url": page_url
        }).execute()

        print(f"✅ Supabase DB 적재 완료!\n")

    except Exception as e:
        print(f"❌ AI 분석 및 DB 저장 중 에러 발생: {e}")

def run_smart_collector():
    options = Options()
    options.add_argument("--headless") # 화면 없이 백그라운드 실행 (필수!)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--incognito")
    options.add_argument(f"user-agent={random.choice(ua_list)}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.maximize_window()

    try:
        for page in range(start_p, end_p + 1):
            print(f"--- 🛒 매니아하우스 {page}페이지 수집 시작 ---")
            driver.get(f"https://maniahouse.co.kr/product/search.html?keyword={search_keyword}&page={page}")
            time.sleep(random.uniform(4, 6))
            
            link_elements = driver.find_elements(By.CSS_SELECTOR, 'ul.prdList > li .name a')
            page_urls = [link.get_attribute('href') for link in link_elements if link.get_attribute('href')]
            page_urls = list(dict.fromkeys(page_urls))

            print(f"🎯 총 {len(page_urls)}개의 상품을 대상으로 수집을 시작합니다.")

            for url in page_urls:
                try:
                    driver.get(url)
                    time.sleep(random.uniform(3, 5))

                    full_text = driver.find_element(By.TAG_NAME, "body").text
                    detail_imgs = driver.find_elements(By.CSS_SELECTOR, '#prdDetail img, .detailImage img, img')
                    candidate_urls = []
                    for d_img in detail_imgs:
                        src = d_img.get_attribute('src')
                        if src and "http" in src and not any(k in src.lower() for k in ['notice', 'guide', 'delivery', 'order', 'logo', 'banner', 'btn']):
                            if src not in candidate_urls:
                                candidate_urls.append(src)

                    analyze_and_save_with_ai(full_text, candidate_urls[:20], url)

                except Exception as e:
                    print(f"❌ 개별 상품 수집 중 에러: {e}")
                    continue

    finally:
        driver.quit()
        print("🎉 수집 작업이 완료되었습니다!")

if __name__ == "__main__":
    run_smart_collector()