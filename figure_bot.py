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

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

ua_list = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

def analyze_and_save_with_ai(raw_text, candidate_image_urls, page_url, shop_name):
    print(f"🤖 AI가 [{shop_name}] 해외 피규어 스펙 및 이미지를 분석 중입니다...")
    
    prompt = f"""
    다음은 해외 피규어 쇼핑몰({shop_name}) 상세 페이지에서 긁어온 텍스트와 이미지 URL 후보들입니다.
    이 페이지의 정보를 분석해서 아래 JSON 형식으로만 응답해주세요 (다른 설명 없이):
    
    * 주의: 만약 이 상품이 피규어가 아니라 단순 잡화(열쇠고리, 아크릴스탠드, 인형, 의류, 아트북, 프라모델 부품 등)라면 "is_figure"를 false로, 완성품 피규어나 넨도로이드, 액션 피규어가 맞다면 true로 설정해주세요.

    - is_figure: true 또는 false (BOOLEAN)
    - title: 피규어 정확한 상품명 (영문 또는 풀네임)
    - manufacturer: 제조사/브랜드 (예: Good Smile Company, Max Factory 등)
    - scale_size: 크기 및 전고 (예: 약 140mm 등)
    - release_date: 발매년월 (예: 2027-06)
    - category: 작품 장르 분류 ('애니메이션', '게임', '보컬로이드', 'VTuber', '기타' 중 택1)
    - figure_type: 피규어 타입 분류 ('넨도로이드/SD', '스케일/스테츄', '누들 스토퍼', '액션 피규어', '기타' 중 택1)
    - images: 배너, 로고, 사은품 이미지를 제외한 순수 상품 대표 이미지 URL을 품질 좋은 순서대로 정확히 3개 뽑아서 배열로 제공 (예: ["url1", "url2", "url3"])
    - price: 판매가격 (숫자만, 표시된 금액 기준, 예: 15800)
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
        
        if not result.get('is_figure', True):
            print(f"🚫 AI 필터링 결과: 피규어가 아니라서 스킵합니다.")
            return

        title = result.get('title')
        manufacturer = result.get('manufacturer', '미정')
        scale = result.get('scale_size', '정보없음')
        release_date = result.get('release_date', '정보없음')
        category = result.get('category', '기타')
        figure_type = result.get('figure_type', '스케일/스테츄')
        ai_review = result.get('ai_review', '멋진 피규어입니다.')
        price_val = int(str(result.get("price", "0")).replace(",", ""))

        images = result.get('images', [])
        img1 = images[0] if len(images) > 0 else 'https://via.placeholder.com/300'
        img2 = images[1] if len(images) > 1 else ''
        img3 = images[2] if len(images) > 2 else ''

        print(f"✨ AI 분석 완료: {title} [{shop_name}]")

        figure_data, _ = supabase.table("figures").insert({
            "title": title,
            "manufacturer": manufacturer,
            "scale": scale,
            "release_date": release_date,
            "image_url1": img1,
            "image_url2": img2,
            "image_url3": img3,
            "image_url": img1,
            "description": ai_review,
            "category": category,
            "figure_type": figure_type
        }).execute()

        figure_id = figure_data[1][0]['id']

        supabase.table("figure_shops").insert({
            "figure_id": figure_id,
            "shop_name": shop_name,
            "price": price_val,
            "shop_url": page_url
        }).execute()

        print(f"✅ Supabase DB 적재 완료!\n")

    except Exception as e:
        print(f"❌ AI 분석 및 DB 저장 중 에러 발생: {e}")

def run_global_collector():
    options = Options()
    options.add_argument("--headless")
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
        # ==========================================
        # 1관문: 아미아미(AmiAmi) 수집 파트
        # ==========================================
        print("\n🚀 [1/2] 아미아미(AmiAmi) 글로벌 탐색 시작")
        driver.get("https://www.amiami.com/eng/search/list/?s_cate2_ids=459&s_sortkey=general_new")
        time.sleep(random.uniform(7, 10))

        amiami_links = driver.find_elements(By.CSS_SELECTOR, 'a.item-link, .search-result-item a, ul.item-list li a')
        amiami_urls = []
        for l in amiami_links:
            href = l.get_attribute('href')
            if href and "/eng/detail?" in href and href not in amiami_urls:
                amiami_urls.append(href)

        print(f"🎯 아미아미 발견 상품: {len(amiami_urls)}개")

        for url in amiami_urls[:10]:
            try:
                existing = supabase.table("figure_shops").select("id").eq("shop_url", url).execute()
                if existing.data:
                    continue

                driver.get(url)
                time.sleep(random.uniform(4, 6))

                full_text = driver.find_element(By.TAG_NAME, "body").text
                detail_imgs = driver.find_elements(By.CSS_SELECTOR, 'img')
                candidate_urls = [d.get_attribute('src') for d in detail_imgs if d.get_attribute('src') and "http" in d.get_attribute('src') and not any(k in d.get_attribute('src').lower() for k in ['logo', 'banner', 'icon'])]

                analyze_and_save_with_ai(full_text, candidate_urls[:20], url, "아미아미")
            except Exception as e:
                continue

        # ==========================================
        # 2관문: 굿스마일 컴퍼니 글로벌 샵 수집 파트
        # ==========================================
        print("\n🚀 [2/2] 굿스마일 컴퍼니(Good Smile Global) 탐색 시작")
        driver.get("https://goodsmileshop.com/en/category-list/en/category-list?sort=new")
        time.sleep(random.uniform(7, 10))

        gs_links = driver.find_elements(By.CSS_SELECTOR, 'a.product-list-thumbnail, .product-item a, a')
        gs_urls = []
        for l in gs_links:
            href = l.get_attribute('href')
            if href and "/p/" in href and href not in gs_urls:
                gs_urls.append(href)

        print(f"🎯 굿스마일 글로벌 발견 상품: {len(gs_urls)}개")

        for url in gs_urls[:10]:
            try:
                existing = supabase.table("figure_shops").select("id").eq("shop_url", url).execute()
                if existing.data:
                    continue

                driver.get(url)
                time.sleep(random.uniform(4, 6))

                full_text = driver.find_element(By.TAG_NAME, "body").text
                detail_imgs = driver.find_elements(By.CSS_SELECTOR, 'img')
                candidate_urls = [d.get_attribute('src') for d in detail_imgs if d.get_attribute('src') and "http" in d.get_attribute('src') and not any(k in d.get_attribute('src').lower() for k in ['logo', 'banner', 'icon'])]

                analyze_and_save_with_ai(full_text, candidate_urls[:20], url, "굿스마일글로벌")
            except Exception as e:
                continue

    finally:
        driver.quit()
        print("🎉 글로벌 피규어 멀티 수집 작업이 완료되었습니다!")

if __name__ == "__main__":
    run_global_collector()