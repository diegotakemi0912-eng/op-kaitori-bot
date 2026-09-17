import os
import time
import requests
from playwright.sync_api import sync_playwright

# 監視したい競合店のXアカウントID（@を除いた英数字）
TARGET_USERNAME = os.environ.get("TARGET_X_USERNAME", "kintaro_ikebukuro") # 任意の対象アカウント名に変更可能

def fetch_latest_image():
    print(f"競合アカウント [@{TARGET_USERNAME}] の最新画像を探索中...")
    
    with sync_playwright() as p:
        # ヘッドレスブラウザ起動
        browser = p.chromium.launch(headless=True)
        # スマホ用User-Agentを模倣して軽量表示
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        )
        page = context.new_page()
        
        # 競合店のメディア一覧ページを開く
        url = f"https://x.com/{TARGET_USERNAME}/media"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)  # 読み込み待機
        
        # ツイート内の画像要素（pbs.twimg.com/media/xxx）を検索
        images = page.locator('img[src*="pbs.twimg.com/media/"]').all()
        
        image_url = None
        for img in images:
            src = img.get_attribute("src")
            if src and "name=" in src:
                # 高解像度（large / orig）パラメータへ置換
                image_url = src.split("&name=")[0] + "&name=large"
                break
            elif src and "format=" in src:
                image_url = src
                break

        browser.close()

    if not image_url:
        print("最新画像が見つかりませんでした。既存の sample.jpg があればそれを継続使用します。")
        return False

    print(f"最新の買取画像URLを発見: {image_url}")
    
    # 画像をダウンロードして sample.jpg として保存（main.pyがそのまま読み込める）
    img_data = requests.get(image_url).content
    with open("sample.jpg", "wb") as f:
        f.write(img_data)
    
    print("最新画像を sample.jpg として保存完了")
    return True

if __name__ == "__main__":
    fetch_latest_image()
