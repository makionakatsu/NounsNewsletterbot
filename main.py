import email
from email.header import decode_header
import imaplib
from bs4 import BeautifulSoup
import requests
import openai
import os
import time

# メールサーバーに接続する
def connect_mail_server(email, password):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email, password)
    mail.select("inbox")
    return mail

# 未読メールのIDを取得する
def get_unread_mail_ids(mail):
    _, data = mail.search(None, "UNSEEN")
    mail_ids = data[0].split()
    return mail_ids

# BeautifulSoupオブジェクトからテキストを抽出する
def get_text(soup):
    text = ""
    for element in soup.find_all(["h1", "h3", "p", "a"]):
        if element.name == "a":
            url = element.get("href")
            if url:
                text += f"URL: {url}\n"
        else:
            text += element.get_text(strip=True)
    return text

# メールを処理し、テキストとデコードされた件名を返す
def process_mail(mail_id, mail):
    _, msg_data = mail.fetch(mail_id, "(RFC822)")
    raw_email = msg_data[0][1]
    msg = email.message_from_bytes(raw_email)

    decoded_subject_string = decode_subject(msg["subject"])

    if msg.is_multipart():
        text = ""
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                text = part.get_payload(decode=True).decode()
            elif part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode()
                soup = BeautifulSoup(html_content, "html.parser")
                text = get_text(soup)
    else:
        text = msg.get_payload(decode=True).decode()

    return text, decoded_subject_string

# 件名をデコードする
def decode_subject(subject):
    decoded_subject = decode_header(subject)
    decoded_subject_string = ""
    for item in decoded_subject:
        if item[1]:
            decoded_subject_string += item[0].decode(item[1])
        else:
            decoded_subject_string += item[0]
    return decoded_subject_string

# テキストを要約する
def summarize_text(text):
    chunks = [text[i:i + 8000] for i in range(0, len(text), 8000)]
    summarized_chunks = []

    for chunk in chunks:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "あなたは、ニュースを受け取り、日本語で感情を込めてわかりやすく伝える役割です。受け取ったテキストを、題名、内容、URLの順に出力してください。URLは1つの題名に複数紐づくことがあります。"},
                    {"role": "user", "content": f"""フォーマットは以下のとおりです。：
                     題名内容に即した絵文字　題名（太字）
                     ・（内容）
                     🔗URL：
                     話題ごとに、⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨ ⌐◨-◨を挿入して区切る。URLの末尾は改行し、次の見出しに移ることをわかるようにしてください。
                     受け取りチャンク：{chunk}"""}
                ],
                timeout=20  # Increase the timeout value
            )
            summarized_chunks.append(response["choices"][0]["message"]["content"])
        except Exception as e:
            print(f"Error occurred during API call: {e}")
            continue

    summarized_text = "\n".join(summarized_chunks)
    return summarized_text

# Discordへメッセージを送信する
def send_discord_message(webhook_url, content, max_retries=3, retry_delay=5):
    chunks = [content[i:i + 2000] for i in range(0, len(content), 2000)]

    for chunk in chunks:
        if isinstance(chunk, bytes):
            chunk = chunk.decode('utf-8')

        data = {"content": chunk}
        retries = 0

        while retries <= max_retries:
            response = requests.post(webhook_url, json=data)
            if response.status_code == 204:
                break
            else:
                print(f"Failed to send message (attempt {retries + 1}): {response.text}")
                if retries < max_retries:
                    time.sleep(retry_delay)
                    retries += 1
                else:
                    print(f"Giving up after {max_retries} attempts")
                    return

        time.sleep(1)  # Add a delay between message sending

# メイン処理
def main():
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    webhook_url = os.environ.get("WEBHOOK_URL")
    openai.api_key = os.environ.get("OPENAI_KEY")

    mail = connect_mail_server(email, password)
    mail_ids = get_unread_mail_ids(mail)

    if len(mail_ids) == 0:
        print("No unread mails found. Skipping Discord message sending.")
    else:
        for mail_id in mail_ids:
            text, decoded_subject_string = process_mail(mail_id, mail)
            summarized_text = summarize_text(text)
            content = f"**Subject:** {decoded_subject_string}\n**Summarized content:**\n{summarized_text}"
            send_discord_message(webhook_url, content)

if __name__ == "__main__":
    main()

