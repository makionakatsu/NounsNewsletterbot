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

mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL, PASSWORD)
mail.select("inbox")

_, data = mail.search(None, "UNSEEN")

mail_ids = data[0].split()

def get_sections(soup):
    sections = []
    for element in soup.find_all(["h1", "h2", "h3", "p", "a"]):
        if element.name == "a":
            url = element.get("href")
            if url:
                sections.append(f"URL: {url}\n")
        else:
            sections.append(element.get_text(strip=True))
    return sections

if len(mail_ids) == 0:
    print("No unread mails found. Skipping Discord message sending.")
else:
    for mail_id in mail_ids:
        _, msg_data = mail.fetch(mail_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

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
                if part.get_content_type() == "text/plain":
                    text = part.get_payload(decode=True).decode()
                elif part.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True).decode()
                    soup = BeautifulSoup(html_content, "html.parser")

                    sections = get_sections(soup)

                    print("BeautifulSoupで取得したセクション:")
                    print(sections)
        else:
            text = msg.get_payload(decode=True).decode()

        print(text)
        print(f"mail_ids: {mail_ids}")

        summarized_sections = []

        for section in sections:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "あなたは、ニュースを受け取り、わかりやすく伝える役割です。"},
                    {"role": "user", "content": f"""以下のセクションを、題名、内容、URLの順に出力してください。
                    URLは1つの題名に複数紐づくことがあります。
                    出力フォーマットは、題名を太字かつ下線として、題名の冒頭に内容に即した絵文字をつけてください。
                    箇条書きで出力してください
                    内容は、文字数が1000字以上の場合は500字程度に要約してください。
                    URLの末尾は改行し、破線を引いて次の見出しに移ることをわかるようにしてください。セクション：{section}"""}
                ],
            )
            summarized_sections.append(response["choices"][0]["message"]["content"])

        summarized_text = "\n".join(summarized_sections)

        data = {
            "content": f"**Subject:** {decoded_subject_string}\n**Summarized content:**\n{summarized_text}"
        }

        response = requests.post(WEBHOOK_URL, json=data)
        if response.status_code != 204:
            print(f"Failed to send message: {response.text}")


 