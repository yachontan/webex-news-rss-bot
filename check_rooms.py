import requests
import getpass

print("=== Webex Room ID 確認ツール ===")
print("Webex Developer Portalから取得したパーソナルアクセストークン、またはBotトークンを入力してください。")
print("（※セキュリティのため、入力した文字は画面に表示されません）\n")

token = getpass.getpass("Token: ").strip()

if not token:
    print("エラー: トークンが入力されませんでした。")
    exit(1)

print("\nWebex APIに接続してルーム一覧を取得しています...")
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("https://webexapis.com/v1/rooms?max=20", headers=headers)

if response.status_code == 200:
    rooms = response.json().get("items", [])
    print(f"\n✅ トークンは有効です！ {len(rooms)} 件のルームが見つかりました。\n")
    print("-" * 50)
    for room in rooms:
        print(f"■ ルーム名: {room.get('title')}")
        print(f"  Room ID : {room.get('id')}")
        print("-" * 50)
    print("\n※ 確認できた Room ID を .env の WEBEX_SPACE_ID_xxx に設定してください。")
else:
    print(f"\n❌ 取得失敗 (ステータスコード: {response.status_code})")
    print("トークンが無効、または期限切れの可能性があります。再度正しいトークンを取得してください。")
    print(f"詳細: {response.text}")
