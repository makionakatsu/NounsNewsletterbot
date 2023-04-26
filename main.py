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

IMAP_SERVER = "imap.gmail.com"

def connect_mail_server():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, PASSWORD)
    mail.select("inbox")
    return mail

def get_unread_mail_ids(mail):
    _, data = mail.search(None, "UNSEEN")
    mail_ids = data[0].split()
    return mail_ids

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

def decode_subject(subject):
    decoded_subject = decode_header(subject)
    decoded_subject_string = ""
    for item in decoded_subject:
        if item[1]:
            decoded_subject_string += item[0].decode(item[1])
        else:
            decoded_subject_string += item[0]
    return decoded_subject_string

def summarize_text(text):
    chunks = [text[i:i + 8000] for i in range(0, len(text), 8000)]
    summarized_chunks = []

    for chunk in chunks:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "あなたは、ニュースを受け取り、日本語でわかりやすく伝える役割です。"},
                {"role": "user", "content": f"""以下のチャンクを、題名、内容、URLの順に出力してください。
                URLは1つの題名に複数紐づくことがあります。
                出力フォーマットは、題名を太字かつ下線として、題名の冒頭に内容に即した絵文字をつけてください。
                箇条書きで出力してください
                内容は、文字数が1000字以上の場合は500字程度に要約してください。
                URLの末尾は改行し、破線を引いて次の見出しに移ることをわかるようにしてください。チャンク：{chunk}"""}
            ],
        )
        summarized_chunks.append(response["choices"][0]["message"]["content"])
        
        summarized_text = "\n".join(summarized_chunks)
        return summarized_text
    
def send_discord_message(content):
    chunks = [content[i:i + 2000] for i in range(0, len(content), 2000)]
    for chunk in chunks:
        if isinstance(chunk, bytes):
            chunk = chunk.decode('utf-8')

        data = {"content": chunk}
        response = requests.post(WEBHOOK_URL, json=data)
        if response.status_code != 204:
            print(f"Failed to send message: {response.text}")

def main():
    mail = connect_mail_server()
    mail_ids = get_unread_mail_ids(mail)

    if len(mail_ids) == 0:
        print("No unread mails found. Skipping Discord message sending.")
    else:
        for mail_id in mail_ids:
            text, decoded_subject_string = process_mail(mail_id, mail)
            summarized_text = summarize_text(text)
            content = f"**Subject:** {decoded_subject_string}\n**Summarized content:**\n{summarized_text}"
            send_discord_message(content)

if __name__ == "__main__":
    main()

