import os
import json
import time
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

# ----------------------------------------------------
# 1. 環境変数の取得（GitHub Secrets）
# ----------------------------------------------------
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER = os.environ.get("LINE_USER_ID")

if not all([GEMINI_KEY, LINE_TOKEN, LINE_USER]):
    raise ValueError("必要な環境変数（シークレット）が設定されていません。")

client = genai.Client(api_key=GEMINI_KEY)

# ----------------------------------------------------
# 2. 競合Xアカウントから最新買取表画像を自動収集
# ----------------------------------------------------
# 監視対象のXアカウントID（@を除いたID）
TARGET_X_USER = "raftel_ikebukuro" 
image_path = "sample.jpg"

def fetch_latest_x_image(screen_name, save_path):
    print(f"Xアカウント (@{screen_name}) から最新の買取画像を探索中...")
    
    # 公開Syndication APIエンドポイントから最新タイムラインを取得
    syndication_url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{screen_name}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(syndication_url, headers=headers, timeout=20)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            data_script = soup.find("script", id="__NEXT_DATA__")
            if data_script:
                json_data = json.loads(data_script.string)
                entries = json_data.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
                
                for entry in entries:
                    tweet = entry.get("content", {}).get("tweet", {})
                    # 画像メディアの探索
                    media_list = tweet.get("entities", {}).get("media", [])
                    if media_list:
                        img_url = media_list[0].get("media_url_https")
                        if img_url:
                            # 最高画質でダウンロード
                            full_quality_url = f"{img_url}?format=jpg&name=large"
                            img_data = requests.get(full_quality_url, headers=headers, timeout=20).content
                            with open(save_path, "wb") as f:
                                f.write(img_data)
                            print(f"✅ 最新画像を自動ダウンロードしました: {full_quality_url}")
                            return True
    except Exception as e:
        print(f"⚠️ X画像自動取得でエラー発生: {e}")

    # 取得に失敗した、または投稿画像がない場合はリポジトリ内の既存ファイルを利用
    if os.path.exists(save_path):
        print("⚠️ 最新画像の自動取得をスキップし、既存のローカル画像を使用します。")
        return True
    return False

if not fetch_latest_x_image(TARGET_X_USER, image_path):
    raise FileNotFoundError("買取表画像を取得できませんでした。リポジトリ内に sample.jpg を配置するか設定を確認してください。")

image = Image.open(image_path)

# ----------------------------------------------------
# 3. Gemini によるカード情報抽出
# ----------------------------------------------------
prompt = """
添付された買取表画像から、掲載されているカードの情報をすべて抽出してください。
以下のJSONフォーマット（配列形式）で出力してください。余計な解説文は不要です。

[
  {
    "card_id": "型番（例: OP05-119。画像内に記載がない場合はnull）",
    "card_name": "カード名",
    "rarity": "仕様やレアリティ（例: コミパラ、金文字、SECなど。不明なら空文字）",
    "buy_price": 買取価格の数字（例: 120000 ※整数で出力）
  }
]
"""

candidate_models = [
    "gemini-3.6-flash",
    "gemini-3.1-pro-preview"
]

response = None
for model_name in candidate_models:
    print(f"Gemini API ({model_name}) へリクエスト中...")
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[image, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                ),
            )
            print(f"✅ {model_name} で解析に成功しました！")
            break
        except Exception as e:
            err_msg = str(e)
            print(f"⚠️ {model_name} 試行{attempt + 1}/3: {err_msg[:120]}...")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print("⏳ 429レート制限を検知。30秒待機します...")
                time.sleep(30)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                time.sleep(5 * (attempt + 1))
            else:
                break
    if response is not None:
        break

if response is None:
    raise RuntimeError("モデルの混雑・制限が継続しています。時間をおいて再実行してください。")

raw_text = response.text.strip()
print(f"--- Gemini 生レスポンス（先頭300文字） ---\n{raw_text[:300]}\n--------------------------")

try:
    extracted_data = json.loads(raw_text)
    if isinstance(extracted_data, dict):
        for v in extracted_data.values():
            if isinstance(v, list):
                extracted_data = v
                break
except Exception as e:
    print(f"JSONパースエラー: {e}")
    extracted_data = []

print(f"カード抽出件数: {len(extracted_data)}件")

# ----------------------------------------------------
# 4. 自社買取価格の計算（掛け率: 100% 同額マッチ）
# ----------------------------------------------------
calculated_results = []

for item in extracted_data:
    raw_card_id = item.get("card_id")
    if not raw_card_id or str(raw_card_id).strip().lower() == "none":
        card_id = "-"
    else:
        card_id = str(raw_card_id).strip()

    card_name = item.get("card_name") or item.get("name") or "名称不明"
    
    raw_price = item.get("buy_price") or item.get("price") or 0
    try:
        comp_price = int(str(raw_price).replace(",", "").replace("¥", "").replace("円", "").strip())
    except:
        comp_price = 0

    # 掛け率を1.0（100% 同額）に設定
    rate = 1.0
    final_price = int((comp_price * rate) // 10 * 10)

    calculated_results.append({
        "card_id": card_id,
        "card_name": str(card_name),
        "rarity": item.get("rarity") or "",
        "my_price": final_price
    })

# ----------------------------------------------------
# 5. 買取表画像の生成（Pillow）
# ----------------------------------------------------
img_w, img_h = 1200, 900
base_img = Image.new("RGB", (img_w, img_h), color="#0F172A")
draw = ImageDraw.Draw(base_img)

font_path = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
title_font = ImageFont.truetype(font_path, 46)
header_font = ImageFont.truetype(font_path, 26)
text_font = ImageFont.truetype(font_path, 24)
price_font = ImageFont.truetype(font_path, 28)

# ヘッダー
draw.rectangle([0, 0, img_w, 120], fill="#1E293B")
draw.rectangle([0, 115, img_w, 120], fill="#E11D48")
draw.text((40, 25), "【池袋店】ワンピースカード 強化買取表", font=title_font, fill="#FFFFFF")
draw.text((40, 80), "※相場・在庫状況により変動する場合があります", font=header_font, fill="#94A3B8")

# テーブルヘッダー
table_y = 150
draw.rectangle([40, table_y, img_w - 40, table_y + 45], fill="#334155")
draw.text((60, table_y + 8), "型番", font=header_font, fill="#F8FAFC")
draw.text((240, table_y + 8), "カード名 / 仕様", font=header_font, fill="#F8FAFC")
draw.text((820, table_y + 8), "自社買取価格", font=header_font, fill="#FDE047")
draw.text((1030, table_y + 8), "状態", font=header_font, fill="#F8FAFC")

# 各行の描画
current_y = table_y + 55
for i, card in enumerate(calculated_results[:12]):
    row_bg = "#1E293B" if i % 2 == 0 else "#0F172A"
    draw.rectangle([40, current_y, img_w - 40, current_y + 52], fill=row_bg)
    draw.text((60, current_y + 12), card["card_id"], font=text_font, fill="#38BDF8")
    
    rarity_str = f" [{card['rarity']}]" if card["rarity"] else ""
    full_name = f"{card['card_name']}{rarity_str}"
    draw.text((240, current_y + 12), full_name[:26], font=text_font, fill="#FFFFFF")
    draw.text((820, current_y + 10), f"¥{card['my_price']:,}", font=price_font, fill="#FACC15")
    draw.text((1030, current_y + 12), "美品", font=text_font, fill="#94A3B8")
    current_y += 52

# フッター
draw.rectangle([0, img_h - 60, img_w, img_h], fill="#1E293B")
draw.text((40, img_h - 45), "池袋トレカ専門店 | 営業時間 11:00-21:00", font=header_font, fill="#CBD5E1")

# メイン画像保存
output_path = "kaitori_output.jpg"
base_img.save(output_path, "JPEG", quality=85)

# ----------------------------------------------------
# 6. LINE対応画像アップロード & 送信
# ----------------------------------------------------
def upload_secure_image(path):
    url = "https://uguu.se/upload"
    with open(path, "rb") as f:
        res = requests.post(url, files={"files[]": f}, timeout=30)
    if res.status_code == 200:
        data = res.json()
        return data["files"][0]["url"]
    else:
        raise Exception(f"アップロード失敗: {res.text}")

print("画像を配信CDNへアップロード中...")
direct_url = upload_secure_image(output_path)
print(f"画像URL取得完了: {direct_url}")

line_headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_TOKEN}"
}
payload = {
    "to": LINE_USER,
    "messages": [
        {
            "type": "text", 
            "text": f"【自動買取表生成】\nカード抽出: {len(calculated_results)}件\n掛け率100%（同額マッチ）で買取表を作成しました。"
        },
        {
            "type": "image", 
            "originalContentUrl": direct_url, 
            "previewImageUrl": direct_url
        },
        {
            "type": "text", 
            "text": "画像を長押し保存してXへポストしてください。"
        }
    ]
}

res_line = requests.post(
    "https://api.line.me/v2/bot/message/push",
    headers=line_headers,
    json=payload,
    timeout=30
)

if res_line.status_code == 200:
    print("✅ LINEへの画像プッシュ送信が完了しました！")
else:
    print(f"❌ LINE送信エラー（ステータスコード: {res_line.status_code}）")
    print(res_line.text)
