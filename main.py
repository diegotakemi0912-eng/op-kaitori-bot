import os
import json
import requests
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
# 2. 画像読み込み & Gemini 抽出処理
# ----------------------------------------------------
image_path = "sample.jpg"
if not os.path.exists(image_path):
    raise FileNotFoundError(f"'{image_path}' がリポジトリ内に見つかりません。画像をアップロードしてください。")

image = Image.open(image_path)

prompt = """
あなたはワンピースカード専門店の査定スタッフです。
添付された買取表画像から、すべてのカードデータを漏れなく読み取ってください。

必ず以下のJSON配列フォーマットのみを出力してください。
マークダウン記法（```json など）や前後の挨拶文は一切含めないでください。

[
  {
    "card_id": "型番（例: OP05-119。画像内に記載がない場合はnull）",
    "card_name": "カード名（例: モンキー・D・ルフィ）",
    "rarity": "仕様やレアリティ（例: コミパラ、金文字、SECなど。不明なら空文字）",
    "buy_price": 買取価格の数字（例: 120000 ※「円」や「,」は含めず整数で出力）
  }
]
"""

print("Gemini APIへ画像を送信中...")
# 推奨されている最新モデル gemini-3.6-flash を指定
response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=[image, prompt],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1
    ),
)

raw_text = response.text.strip()
print("--- Gemini 生レスポンス ---")
print(raw_text)
print("--------------------------")

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
# 3. 自社買取価格の計算
# ----------------------------------------------------
inventory_data = {"OP05-119": 1, "OP01-120": 6}
calculated_results = []

for item in extracted_data:
    # 型番がNoneやnullの場合はハイフンに置き換え
    raw_card_id = item.get("card_id")
    if not raw_card_id or str(raw_card_id).strip().lower() == "none":
        card_id = "-"
    else:
        card_id = str(raw_card_id).strip()

    card_name = item.get("card_name") or item.get("name") or "名称不明"
    
    # 金額の数値化
    raw_price = item.get("buy_price") or item.get("price") or 0
    try:
        comp_price = int(str(raw_price).replace(",", "").replace("¥", "").replace("円", "").strip())
    except:
        comp_price = 0

    stock = inventory_data.get(card_id, 3)

    # 在庫に応じた掛け率（在庫薄:100%、過多:80%、通常:90%）
    rate = 1.0 if stock <= 1 else (0.8 if stock >= 5 else 0.9)
    final_price = int((comp_price * rate) // 10 * 10)

    calculated_results.append({
        "card_id": card_id,
        "card_name": str(card_name),
        "rarity": item.get("rarity") or "",
        "my_price": final_price
    })

# ----------------------------------------------------
# 4. 買取表画像の生成（Pillow）
# ----------------------------------------------------
img_w, img_h = 1200, 900
base_img = Image.new("RGB", (img_w, img_h), color="#0F172A")
draw = ImageDraw.Draw(base_img)

font_path = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"
title_font = ImageFont.truetype(font_path, 46)
header_font = ImageFont.truetype(font_path, 26)
text_font = ImageFont.truetype(font_path, 24)
price_font = ImageFont.truetype(font_path, 28)

# ヘッダー描画
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
if not calculated_results:
    draw.text((60, current_y + 20), "※読み取り可能なカードデータが見つかりませんでした", font=text_font, fill="#EF4444")
else:
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
output_path = "kaitori_output.png"
base_img.save(output_path)

# プレビュー用画像
preview_path = "kaitori_preview.jpg"
with Image.open(output_path) as img:
    img_preview = img.copy()
    img_preview.thumbnail((800, 800))
    img_preview.convert("RGB").save(preview_path, "JPEG", quality=75)

# ----------------------------------------------------
# 5. LINE対応画像アップロード（Freeimage API）
# ----------------------------------------------------
def upload_image(path):
    url = "[https://freeimage.host/api/1/upload](https://freeimage.host/api/1/upload)"
    data = {
        "key": "6d207e02198a847aa98d0a2a901485a5",
        "action": "upload",
        "format": "json"
    }
    with open(path, "rb") as f:
        res = requests.post(url, data=data, files={"source": f})
    
    res_data = res.json()
    if res.status_code == 200 and "image" in res_data:
        return res_data["image"]["url"]
    else:
        raise Exception(f"画像アップロード失敗: {res.text}")

print("画像をCDNへアップロード中...")
orig_url = upload_image(output_path)
prev_url = upload_image(preview_path)
print(f"画像URL取得成功:\n  元画像: {orig_url}\n  プレビュー: {prev_url}")

# ----------------------------------------------------
# 6. LINE Messaging API プッシュ送信
# ----------------------------------------------------
line_headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_TOKEN}"
}
payload = {
    "to": LINE_USER,
    "messages": [
        {
            "type": "text", 
            "text": f"【自動買取表生成】\nカード抽出: {len(calculated_results)}件\n画像をタップして確認してください。"
        },
        {
            "type": "image", 
            "originalContentUrl": orig_url, 
            "previewImageUrl": prev_url
        },
        {
            "type": "text", 
            "text": "画像を長押し保存してXへポストしてください。"
        }
    ]
}

res_line = requests.post("[https://api.line.me/v2/bot/message/push](https://api.line.me/v2/bot/message/push)", headers=line_headers, json=payload)

if res_line.status_code == 200:
    print("✅ LINEへの画像プッシュ送信が完了しました！")
else:
    print(f"❌ LINE送信エラー（ステータスコード: {res_line.status_code}）")
    print(res_line.text)
