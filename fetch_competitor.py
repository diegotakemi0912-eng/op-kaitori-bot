import os
import time
import requests
from playwright.sync_api import sync_playwright

# 監視対象のアカウントID
TARGET_USERNAME = os.environ.get("TARGET_X_USERNAME", "card_raftel")

def fetch_latest_image():
    print(f"[@{TARGET_USERNAME}] の最新買取ポストを監視中...")
    
    image_url = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # スマホ表示をシミュレート
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        )
        page = context.new_page()
        
        # タイムラインを開く
        url = f"https://x.com/{TARGET_USERNAME}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)  # 投稿がレンダリングされるまで待機

        # 各ツイート要素を探索
        articles = page.locator('article').all()
        print(f"取得したツイート数: {len(articles)}")

        for article in articles:
            text = article.inner_text()
            # 「ワンピース」または「ワンピ」、かつ「買取」が含まれるポストを優先判定
            if ("ワンピース" in text or "ワンピ" in text) and "買取" in text:
                img = article.locator('img[src*="pbs.twimg.com/media/"]').first
                if img.count() > 0:
                    src = img.get_attribute("src")
                    if src:
                        # 最高解像度（origまたはlarge）を取得
                        base_url = src.split("&name=")[0]
                        image_url = f"{base_url}&name=large"
                        print("ワンピースカードの買取表ポストを発見しました。")
                        break

        # もしキーワード一致が見つからない場合、メディア一覧の先頭画像を取得（フォールバック）
        if not image_url:
            print("本文判定で見つからなかったため、メディアタブの最新画像を探索します...")
            page.goto(f"https://x.com/{TARGET_USERNAME}/media", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            img = page.locator('img[src*="pbs.twimg.com/media/"]').first
            if img.count() > 0:
                src = img.get_attribute("src")
                if src:
                    image_url = src.split("&name=")[0] + "&name=large"

        browser.close()

    if not image_url:
        print("最新画像を取得できませんでした。")
        return False

    print(f"取得した画像URL: {image_url}")
    
    # 画像をダウンロードして sample.jpg として保存（main.pyで読み込み）
    res = requests.get(image_url)
    if res.status_code == 200:
        with open("sample.jpg", "wb") as f:
            f.write(res.content)
        print("最新の買取表を sample.jpg に保存しました。")
        return True
    else:
        print("画像のダウンロードに失敗しました。")
        return False

if __name__ == "__main__":
    fetch_latest_image()
