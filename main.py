import email
from email.header import decode_header
import imaplib
from bs4 import BeautifulSoup, Tag
import requests
import openai
import os

EMAIL = os.environ.get("EMAIL")
PASSWORD = os.environ.get("PASSWORD")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
openai.api_key = os.environ.get("OPENAI_KEY")

# メールアカウントの設定
IMAP_SERVER = "imap.gmail.com"

# IMAP接続
mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL, PASSWORD)
mail.select("inbox")

# メールの検索（未読メール）
_, data = mail.search(None, "UNSEEN")

# メールIDの取得
mail_ids = data[0].split()

# メールの本文とURLの取得
def process_html_element(element):
    if isinstance(element, Tag):
        if element.name == "a":
            url = element.get("href")
            if url:
                return f"URL: {url}\n"
    return ""

# 各メールの処理
for mail_id in mail_ids:
    # メールの取得
    _, msg_data = mail.fetch(mail_id, "(RFC822)")
    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    # Subjectのデコード
    subject = msg["subject"]
    decoded_subject = decode_header(subject)
    decoded_subject_string = ""
    for item in decoded_subject:
        if item[1]:
            decoded_subject_string += item[0].decode(item[1])
        else:
            decoded_subject_string += item[0]

    if msg.is_multipart():
        for part in msg.walk():
            print(f"content_type: {part.get_content_type()}")
            if part.get_content_type() == "text/plain":
                text = part.get_payload(decode=True).decode()
            elif part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode()
                print(f"HTML content: {html_content}")
                soup = BeautifulSoup(html_content, "html.parser")

                # テキストとURLの取得
                result = []
                for element in soup.find_all("div"):
                    for child in element.children:
                        if child.string:
                            result.append(child.string.strip())
                        result.append(process_html_element(child))
                text = "".join(result).strip()


                # ここでBeautifulSoupで取得したテキストをログに出力
                print("BeautifulSoupで取得したテキスト:")
                print("".join(result).strip())

                text = "".join(result).strip()

    else:
        text = msg.get_payload(decode=True).decode()

    print(text)
    print(f"mail_ids: {mail_ids}")

    # GPT-4によるテキストの要約
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "あなたは、MECEや5W1Hの思考法を用いることが得意です。"},
            {"role": "user", "content": f"""
             以下のテキストを、見出し、内容、URLの順に出力してください。
             出力フォーマットは、**1.**、**2.**、**3.**として、箇条書きで出力してください。
             内容は、文字数が500字以上の場合は200字以内に要約してください。
             URLの末尾は改行し、破線を引いて次の見出しに移ることをわかるようにしてください。 
             テキスト：{text}
             """}
        ],
    )
    summarized_text = response["choices"][0]["message"]["content"]

    # Discordに送信するデータの作成
    data = {
        "content": f"**Subject:** {decoded_subject_string}\n**Summarized content:**\n{summarized_text}"
    }

    # Discord Webhookを使ってメッセージを送信
    response = requests.post(WEBHOOK_URL, json=data)
    if response.status_code != 204:
        print(f"Failed to send message: {response.text}")
