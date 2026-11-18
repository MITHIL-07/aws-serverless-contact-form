"""
Serverless Contact Form handler
-------------------------------
Triggered by Amazon API Gateway (HTTP API, payload format 2.0) on  POST /contact

Flow:
    1. Parse and validate the JSON body (name, email, subject, message)
    2. Save the submission to Amazon DynamoDB
    3. Send an email notification to the admin through Amazon SES

Environment variables (set in the Lambda console):
    TABLE_NAME    DynamoDB table name           e.g. ContactMessages
    SENDER_EMAIL  Verified SES sender address   e.g. you@example.com
    ADMIN_EMAIL   Verified SES admin address    e.g. you@example.com

CORS is configured on the API Gateway itself, so this function does not need
to return CORS headers.
"""

import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("TABLE_NAME", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("ses")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SUCCESS_MESSAGE = "Thank you! Your message has been received."


def _response(status_code, body):
    """Build an API Gateway (payload v2.0) response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _clean(value, max_len):
    """Return a trimmed string limited to max_len characters."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_len]


def _single_line(value):
    """Remove line breaks so the value is safe to use in an email subject."""
    return re.sub(r"[\r\n]+", " ", value)


def _parse_body(event):
    """Read the JSON body sent by the website."""
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("Body must be a JSON object")
    return data


def _validate(data):
    """Return (cleaned_fields, error_message). error_message is None if valid."""
    name = _clean(data.get("name"), 100)
    email = _clean(data.get("email"), 254).lower()
    subject = _single_line(_clean(data.get("subject"), 150)) or "New message"
    message = _clean(data.get("message"), 2000)

    if len(name) < 2:
        return None, "Please enter your name (at least 2 characters)."
    if not EMAIL_PATTERN.match(email):
        return None, "Please enter a valid email address."
    if len(message) < 10:
        return None, "Please enter a message (at least 10 characters)."

    return {"name": name, "email": email, "subject": subject, "message": message}, None


def _save_to_dynamodb(item):
    table = dynamodb.Table(TABLE_NAME)
    table.put_item(Item=item)


def _send_email(item):
    """Notify the admin by email. Reply-To is set to the visitor's address."""
    body_text = (
        "New contact form submission\n"
        "===========================\n\n"
        f"Name:       {item['name']}\n"
        f"Email:      {item['email']}\n"
        f"Subject:    {item['subject']}\n"
        f"Received:   {item['createdAt']} (UTC)\n"
        f"Message ID: {item['id']}\n\n"
        "Message:\n"
        "--------\n"
        f"{item['message']}\n"
    )
    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={"ToAddresses": [ADMIN_EMAIL]},
        ReplyToAddresses=[item["email"]],
        Message={
            "Subject": {"Data": f"[Contact Form] {item['subject']}", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body_text, "Charset": "UTF-8"}},
        },
    )


def lambda_handler(event, context):
    if not (TABLE_NAME and SENDER_EMAIL and ADMIN_EMAIL):
        logger.error("Missing environment variables: TABLE_NAME, SENDER_EMAIL, ADMIN_EMAIL")
        return _response(500, {"message": "Server configuration error."})

    # 1. Parse the request body
    try:
        data = _parse_body(event)
    except (ValueError, TypeError):
        return _response(400, {"message": "Invalid request. Please send valid JSON."})

    # Honeypot field: real visitors never see or fill it, simple bots do.
    if data.get("website"):
        logger.info("Honeypot field filled, submission ignored.")
        return _response(200, {"message": SUCCESS_MESSAGE})

    # 2. Validate
    fields, error = _validate(data)
    if error:
        logger.info("Validation failed: %s", error)
        return _response(400, {"message": error})

    item = {
        "id": str(uuid.uuid4()),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "new",
        **fields,
    }

    # 3. Save to DynamoDB (must succeed)
    try:
        _save_to_dynamodb(item)
        logger.info("Saved submission %s", item["id"])
    except ClientError:
        logger.exception("DynamoDB write failed")
        return _response(500, {"message": "Could not save your message. Please try again later."})

    # 4. Email the admin (the message is already saved, so a failure here is only logged)
    try:
        _send_email(item)
        logger.info("Email sent for submission %s", item["id"])
    except ClientError:
        logger.exception("SES send failed for submission %s", item["id"])

    return _response(200, {"message": SUCCESS_MESSAGE, "id": item["id"]})
