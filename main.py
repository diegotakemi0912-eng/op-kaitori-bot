import os
import json
import requests
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

# 1. 環境変数の取得
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER = os.environ.get("LINE_USER_ID")

client = genai.Client(api_key=GEMINI_KEY)

# 2. 画像読み込み & Gemini 抽出
# ※ ここではリポジトリ内に配置した sample.jpg を参照
image_path = "sample.jpg"
image = Image.open(image_path)

prompt = """
添付されたカード買取表の画像から、掲載されているカードの情報をすべて抽出してください。
以下のJSONフォーマット（配列形式）で出力してください。余計な解説文は不要です。
[
  {
    "card_id": "型番（例: OP05-119）",
    "card_name": "カード名",
    "rarity": "レアリティや仕様（不明ならnull）",
    "buy_price": 買取価格（数値）
  }
]
"""

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=[image, prompt],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1
    ),
)
extracted_data = json.loads(response.text)

# 3. 価格計算
inventory_data = {"OP05-119": 1, "OP01-120": 6}
calculated_results = []

for item in extracted_data:
    card_id = item.get("card_id")
    comp_price = item.get("buy_price", 0)
    stock = inventory_data.get(card_id, 3)

    rate = 1.0 if stock <= 1 else (0.8 if stock >= 5 else 0.9)
    final_price = int((comp_price * rate) // 10 * 10)

    calculated_results.append({
        "card_id": card_id,
        "card_name": item.get("card_name"),
        "rarity": item.get("rarity"),
        "my_price": final_price
    })

# 4. 買取表画像生成
img_w, img_h = 1200, 900
base_img = Image.new("RGB", (img_w, img_h), color="#0F172A")
draw = ImageDraw.Draw(base_img)

font_path = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
title_font = ImageFont.truetype(font_path, 46)
header_font = ImageFont.truetype(font_path, 26)
text_font = ImageFont.truetype(font_path, 24)
price_font = ImageFont.truetype(font_path, 28)

draw.rectangle([0, 0, img_w, 120], fill="#1E293B")
draw.rectangle([0, 115, img_w, 120], fill="#E11D48")
draw.text((40, 25), "【池袋店】ワンピースカード 強化買取表", font=title_font, fill="#FFFFFF")
draw.text((40, 80), "※相場・在庫状況により変動する場合があります", font=header_font, fill="#94A3B8")

table_y = 150
draw.rectangle([40, table_y, img_w - 40, table_y + 45], fill="#334155")
draw.text((60, table_y + 8), "型番", font=header_font, fill="#F8FAFC")
draw.text((240, table_y + 8), "カード名 / 仕様", font=header_font, fill="#F8FAFC")
draw.text((820, table_y + 8), "自社買取価格", font=header_font, fill="#FDE047")
draw.text((1030, table_y + 8), "状態", font=header_font, fill="#F8FAFC")

current_y = table_y + 55
for i, card in enumerate(calculated_results[:12]):
    row_bg = "#1E293B" if i % 2 == 0 else "#0F172A"
    draw.rectangle([40, current_y, img_w - 40, current_y + 52], fill=row_bg)
    draw.text((60, current_y + 12), str(card.get("card_id", "-")), font=text_font, fill="#38BDF8")
    
    full_name = f"{card.get('card_name', '')} [{card.get('rarity') or ''}]"
    draw.text((240, current_y + 12), full_name[:26], font=text_font, fill="#FFFFFF")
    draw.text((820, current_y + 10), f"¥{card.get('my_price', 0):,}", font=price_font, fill="#FACC15")
    draw.text((1030, current_y + 12), "美品", font=text_font, fill="#94A3B8")
    current_y += 52

output_path = "kaitori_output.png"
base_img.save(output_path)

# プレビュー作成
preview_path = "kaitori_preview.jpg"
with Image.open(output_path) as img:
    img_preview = img.copy()
    img_preview.thumbnail((800, 800))
    img_preview.convert("RGB").save(preview_path, "JPEG", quality=75)

# 5. Imgur アップロード
def upload_imgur(path):
    headers = {"Authorization": "Client-ID c3ecbf76d05f77a"}
    with open(path, "rb") as f:
        res = requests.post("https://api.imgur.com/3/image", headers=headers, files={"image": f})
    return res.json()["data"]["link"]

orig_url = upload_imgur(output_path)
prev_url = upload_imgur(preview_path)

# 6. LINE プッシュ送信
line_headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_TOKEN}"
}
payload = {
    "to": LINE_USER,
    "messages": [
        {"type": "text", "text": "【自動買取表生成】\n本日の買取表が完成しました。"},
        {"type": "image", "originalContentUrl": orig_url, "previewImageUrl": prev_url},
        {"type": "text", "text": "画像を保存してXへポストしてください。"}
    ]
}
requests.post("https://api.line.me/v2/bot/message/push", headers=line_headers, json=payload)
print("LINE送信完了")
