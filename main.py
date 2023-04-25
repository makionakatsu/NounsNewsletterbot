import email
from email.header import decode_header
import imaplib
from bs4 import BeautifulSoup
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

    # メールの本文の取得
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                text = part.get_payload(decode=True).decode()
            elif part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode()
                soup = BeautifulSoup(html_content, "html.parser")
                text = soup.get_text()
    else:
        text = msg.get_payload(decode=True).decode()
        
        print(text)

    # GPT-4によるテキストの要約
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "あなたは、MECEや5W1Hの思考法を用いることが得意です。"},
            {"role": "user", "content": f"以下のテキストを、見出し、小見出し、URLは省略せずに、内容を日本語で要約してください。\nフォーマットは、以下としてください。\n1.見出し\n・要約内容\n2.見出し\n・要約内容\n{text}"}
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
