"""
An ansible-rulebook event source module for receiving events via IMAP.

Arguments:
    host: The hostname to listen to. Set to 0.0.0.0 to listen on all
          interfaces. Defaults to 127.0.0.1
    port: The TCP port to listen to.  Defaults to 1514
"""

import asyncio
import logging
from typing import Any
import imaplib
import email


def email_unpack(eml:email.message.Message, emails:list=None):
    """Unpack nested emails.
     
    Return a list of emails in terms of headers, content-type and attachments (payloads).
    """
    if not emails:
        emails = []

    if eml.is_multipart():
        headers = eml.items()
        payloads = []
        for eml_part in eml.walk():
            content_type = eml_part.get_content_type()
            if content_type.startswith("multipart/"):
                continue
            if content_type.startswith("message/"):
                for nested_email in eml_part.get_payload():
                    emails = email_unpack(nested_email, emails)

            payload = eml_part.get_payload(decode=True)
            if payload:
                payloads.append({
                    "content-type": eml_part.get_content_type(),
                    "payload": payload.decode(),
                })
        if payloads:
            emails.append({
                "headers": headers,
                "payloads": payloads,
            })
    else:
        headers = eml.items()
        payload = eml.get_payload(decode=True)
        if payload:
            emails.append({
                "headers": headers,
                "payloads": [{
                    "content-type": eml.get_content_type(),
                    "payload": payload.decode(),
                }],
            })
    return emails


async def main(queue: asyncio.Queue, args: dict[str, Any]) -> None:
    """Receive emails via IMAP."""
    # Load or set default variables
    imap_url = args.get("host") or "imap.gmail.com"
    imap_port = args.get("port") or 993
    username = args.get("username")
    password = args.get("password")
    delay = args.get("delay") or 300
    folders = args.get("folders") or ["INBOX", "[Gmail]/Spam"]

    while True:
        # Listening
        try:
            box = imaplib.IMAP4_SSL(imap_url, port=imap_port)
            box.login(username, password)
            logging.info(f"Connected to {imap_url}:{imap_port}")
        except Exception as e:
            logging.error("Connection failed: {}".format(e))
            raise

        for folder in folders:
            logging.info(f"Looking for emails in {folder} folder")
            box.select(mailbox=folder)
            typ, data = box.search(None, "ALL")
            for num in data[0].split():
                logging.info(f"Got email {num.decode()}")
                typ, msg = box.fetch(num, '(RFC822)')
                eml = email.message_from_bytes(msg[0][1])
                emails_unpacked = email_unpack(eml)
                # Analize attached emails only (drop the container)
                for email_unpacked in emails_unpacked[0:-1]:
                    print(email_unpacked)
                    await queue.put(email_unpacked)
                    
                # Delete email
                logging.info(f"Marking email {folder}:{num.decode()} as deleted")
                # TODO: uncomment the following line
                # box.store(num, "+FLAGS", "\\Deleted")

            # Clear mailbox before moving to the next one
            logging.info(f"Clearing {folder} folder")
            box.expunge()
            box.close()
        box.logout()
        logging.info(f"Disconnected from {imap_url}:{imap_port}")
        logging.info(f"Waiting for {delay} seconds")
        await asyncio.sleep(delay)


if __name__ == "__main__":
    # Only called when testing plugin directly, without ansible-rulebook
    class MockQueue:
        """Test class."""

        async def put(self, event):
            """Print the event."""
            print(event)

    mock_arguments = dict()
    asyncio.run(main(MockQueue(), mock_arguments))
