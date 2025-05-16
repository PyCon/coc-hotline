import datetime

from flask import Flask, Response, request, url_for
from twilio.twiml.voice_response import VoiceResponse, Dial
from twilio.twiml.messaging_response import MessagingResponse

import requests

import os

app = Flask(__name__)
_HOTLINE_NUMBERS = None
_AFTER_HOURS_NUMBERS = None
_HTTP_SCHEME = None
_SLACK_URL = None


def after_hours():
    timezone = datetime.timezone(datetime.timedelta(hours=-4))
    return not (9 <= datetime.datetime.now(tz=timezone).hour < 23)


class ConfigurationError(ValueError):
    pass


def get_hotline_numbers():
    global _HOTLINE_NUMBERS
    global _AFTER_HOURS_NUMBERS

    if _HOTLINE_NUMBERS is None:
        numbers_str = os.environ.get("COC_NUMBERS", None)

        if numbers_str is None:
            msg = (
                "Environment variable COC_NUMBERS must be present "
                "and must be a comma delimited string of numbers "
                "with country codes"
            )
            raise ConfigurationError(msg)

        _HOTLINE_NUMBERS = {}
        for num in numbers_str.split(","):
            try:
                name = num.split(";")[1].strip()
            except:
                name = None
            _HOTLINE_NUMBERS[num.split(";")[0].strip()] = name

    if _AFTER_HOURS_NUMBERS is None:
        numbers_str = os.environ.get("COC_AFTER_HOURS_NUMBERS", None)

        if numbers_str is None:
            msg = (
                "Environment variable COC_AFTER_HOURS_NUMBERS must be present "
                "and must be a comma delimited string of numbers "
                "with country codes"
            )
            raise ConfigurationError(msg)

        _AFTER_HOURS_NUMBERS = {}
        for num in numbers_str.split(","):
            try:
                name = num.split(";")[1].strip()
            except:
                name = None
            _AFTER_HOURS_NUMBERS[num.split(";")[0].strip()] = name

    if after_hours():
        return _AFTER_HOURS_NUMBERS
    return _HOTLINE_NUMBERS


def get_http_scheme():
    global _HTTP_SCHEME

    if _HTTP_SCHEME is None:
        http_scheme_str = os.environ.get("COC_HTTP_SCHEME", "http").strip().lower()

        if http_scheme_str not in {"http", "https"}:
            raise ConfigurationError("COC_HTTP_SCHEME must be http or https")

        _HTTP_SCHEME = http_scheme_str

    return _HTTP_SCHEME


def get_slack_url():
    global _SLACK_URL

    if _SLACK_URL is None:
        _SLACK_URL = os.environ.get("COC_SLACK_URL", "")

    return _SLACK_URL


def send_slack_message(msg, attachments=None):
    if _SLACK_URL != "":
        payload = {
            "text": msg,
            "username": "CoC Hotline Bot",
            "icon_emoji": ":rotating_light:",
        }

        if attachments is not None:
            payload["attachments"] = attachments

        requests.post(get_slack_url(), json=payload)


def handle_answered(data):
    incoming_number = data.get("From")
    outgoing_number = data.get("To")
    hotline_numbers = get_hotline_numbers()
    if hotline_numbers.get(outgoing_number, None):
        outgoing_number = hotline_numbers[outgoing_number]
    msg = f"Call from {incoming_number} answered by {outgoing_number}"
    print(msg)
    msg_attachments = [
        {
            "color": "good",
            "title": "Call Answered",
            "fallback": msg,
            "text": (
                f"Call from *{incoming_number}* " f"answered by *{outgoing_number}*"
            ),
            "mrkdwn_in": ["text", "pretext"],
        }
    ]
    send_slack_message("", msg_attachments)


def handle_completed(data):
    incoming_number = data.get("From")
    outgoing_number = data.get("To")
    call_duration = data.get("CallDuration")
    hotline_numbers = get_hotline_numbers()
    if hotline_numbers.get(outgoing_number, None):
        outgoing_number = hotline_numbers[outgoing_number]
    msg = f"Call from {incoming_number} to {outgoing_number} has completed"
    print(msg)
    msg_attachments = [
        {
            "color": "good",
            "title": "Call Completed",
            "fallback": msg,
            "text": (
                f"Call from *{incoming_number}* "
                f"to *{outgoing_number}* has completed\n"
                f"Call lasted for {call_duration} seconds"
            ),
            "mrkdwn_in": ["text", "pretext"],
        }
    ]
    send_slack_message("", msg_attachments)


@app.route("/call_status", methods=["POST"])
def call_status():
    values = request.values
    status = values.get("CallStatus")

    if status == "in-progress":
        handle_answered(values)
    elif status == "completed":
        handle_completed(values)

    return Response(str(VoiceResponse()), 200, mimetype="application/xml")


@app.route("/incoming_call", methods=["POST"])
def incoming_call():
    response = VoiceResponse()
    dial = Dial()
    incoming_number = request.values.get("From")
    msg = f"Incoming call from {incoming_number}"
    print(msg)
    msg_attachments = [
        {
            "color": "danger",
            "title": "Incoming Call",
            "fallback": msg,
            "text": f"From *{incoming_number}*",
            "mrkdwn_in": ["text", "pretext"],
        }
    ]
    send_slack_message(f"<!channel>", msg_attachments)
    status_url = url_for("call_status", _external=True, _scheme=get_http_scheme())

    for number in get_hotline_numbers():
        dial.number(
            number,
            status_callback_event="initiated ringing answered completed",
            status_callback_method="POST",
            status_callback=status_url,
        )

    response.append(dial)

    return Response(str(response), 200, mimetype="application/xml")


@app.route("/incoming_sms", methods=["POST"])
def incoming_sms():
    incoming_number = request.values.get("From")
    body = request.values.get("Body")
    msg = f"Incoming SMS from {incoming_number}"
    print(msg)
    text = f"From *{incoming_number}*"
    text += f"\n{body}"
    num_media = int(request.values.get("NumMedia", "0"))
    if num_media > 0:
        text += "\n\nMedia Attachments:"
        for i in range(num_media):
            media_url = request.values.get(f"MediaUrl{i}")
            text += f"\n  - {media_url}"
    msg_attachments = [
        {
            "color": "danger",
            "title": "Incoming SMS",
            "fallback": msg,
            "text": text,
            "mrkdwn_in": ["text", "pretext"],
        }
    ]
    send_slack_message(f"<!channel>", msg_attachments)
    response = MessagingResponse()
    response.message(
        "Thank you for contacting the PyCon US incident hotline, "
        f"a responder will contact you at {incoming_number}."
    )
    return str(response)

@app.route("/_health")
@app.route("/_health/")
def health()
    return "OK"


if __name__ == "__main__":
    from waitress import serve
    get_hotline_numbers()
    get_http_scheme()
    get_slack_url()

    print('starting server...')
    uds = os.environ.get("UDS", None)
    if uds is not None:
        serve(app, unix_socket=uds)
    else:
        port = os.environ.get("PORT", 8080)
        serve(app, host="0.0.0.0", port=port, threads=8)
