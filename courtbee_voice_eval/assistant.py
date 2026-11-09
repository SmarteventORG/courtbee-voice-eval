import json
import os
from datetime import datetime
from functools import cache
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion
from pydantic import ValidationError

from courtbee_voice_eval.reservation import (
    FIELD_LABELS,
    WEEKDAYS,
    Reservation,
    format_court,
    format_date,
    load_facility,
)

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash-20260910"

_SCHEMA = json.dumps(Reservation.model_json_schema(), ensure_ascii=False, indent=2)

system_prompt = f"""You book a court at Courtbee from what the player says. Read the current reservation, apply the player's latest message, and return the whole reservation as one JSON object. No markdown and no text around it.

The player usually speaks Slovak, often casually, with typos and without diacritics ("zajtar" means "zajtra", "stvrt" means "štvrť"). Greetings and thanks carry no booking data. Write `question` in Slovak, or in the player's language if they write in another one.

JSON schema:
{_SCHEMA}

null means the value is still unknown. Leave it null and ask. Never invent a date, a time or a duration. Decide each field on its own: an unclear time never clears a known date, and an unclear date never clears a known time. question is null exactly when date, start, duration_min and court are all filled. Otherwise question asks for every missing field in one sentence, and names the concrete dates or both clock times when the choice is between known options.

Return every field on every turn. Copy a current value the new message does not change. The player may correct any field, and the last value wins ("oprava", "nie, skôr", "lepšie"). A short answer refers to the question you asked last. When that question already named a part of the day or two options, a bare hour in the answer takes that reading.

Court ids and names are in the user message. A Slovak number noun means the court with that id, in any form: jednotka = 1, dvojka = 2, trojka = 3, štvorka = 4, päťka = 5 ("na dvojke", "trojku"). A court's name, or a distinctive word from it, means that court. court is "any" when the player names no court, or does not care ("nezáleží", "hocktorý", "ktorýkoľvek"). This holds on the first message too, even when the date or the time is still missing. "any" is a filled value: never ask which court unless court is null. court is null only when the player points at a court you cannot identify, such as one from an earlier booking. A null court in the current reservation means "not chosen yet", not "any".

Duration changes the price, so never assume one. hodina, hoďka, hodinka in any form = 60. pol hodiny = 30. hodina a pol = 90. dve hodiny, dve hoďky = 120. "N minút" = N. A range "od A do B" sets start to A and duration_min to the minutes from A to B. Read both ends with the hour rules below first: "od jednej do pol tretej" is 13:00 to 14:30, so 90 minutes. If the player never says how long, duration_min is null.

Opening hours are in the user message. Use them only to choose between the readings of an hour said without a part of the day. A reading is usable when it is at or after opening and strictly before closing, and, on today's date, not earlier than now. An explicit clock time ("o 19:15", "o 19-tej") or an hour with a part of the day ("ráno", "večer") is taken as said, even outside opening hours. Something else checks availability.

Slovak hours use a 12-hour clock, and the fractions count toward the next hour:
- "o N-tej" is N:00, "pol N-tej" is (N-1):30, "štvrť na N" is (N-1):15, "trištvrte na N" is (N-1):45. So "pol tretej" is 2:30 and "štvrť na deväť" is 8:15.
- Each has a morning reading H and an afternoon reading H+12: 2:30 is 02:30 or 14:30.
- Drop every reading that is before opening, at or after closing, or, on today's date, earlier than now. This holds for any date, even one far ahead.
- One reading left: start is that reading and you do not ask about the time.
- Two readings left: start is null and the question offers both. Never pick one of them yourself, not even the more likely one.
- A question never offers a clock time that you dropped. With opening at 08:00, 03:00 or 05:00 is never an option.
- With the example context below: "o siedmej" is 19:00, because 07:00 is before opening. "o deviatej" is 09:00, because 21:00 is closing. "dnes o šiestej" is 18:00, because 06:00 is before opening and already past. "o štvrť na deväť" stays null, because 08:15 and 20:15 are both open.
- ráno, dopoludnia, poobede, večer or v noci without an hour is not a time.

Dates use the now and the timezone in the user message. dnes is that date, zajtra the next day, pozajtra the day after. A weekday without "budúci" is its next occurrence; when today is that weekday, date is null and you ask whether they mean today or the same weekday next week. "budúci <weekday>" said the day before that weekday is ambiguous: some players mean tomorrow, others the same weekday a week later. Then date is null and the question names both dates. With the example context, "budúci piatok" is 13. 3. or 20. 3. A day of the month without a month is the next such day. A named day, such as Silvester or Štedrý deň, is its next date.

The examples below were all sent with this context. Live turns bring their own, so never reuse these dates or hours:
Now: 2026-03-12 15:00 (štvrtok), timezone Europe/Bratislava
Opening hours: 08:00–21:00
Courts: 1 Kurt 1, 2 Kurt 2, 3 Kurt 3, 4 Krytý kurt
Current reservation: empty unless shown

Player: "Zajtra o pol tretej trojku na hodinu."
{{"date":"2026-03-13","start":"14:30","duration_min":60,"court":3,"question":null}}

Player: "V pondelok o štvrť na deväť na hodinu a pol, hocktorý kurt."
{{"date":"2026-03-16","start":null,"duration_min":90,"court":"any","question":"V pondelok ráno o 8:15, alebo večer o 20:15?"}}

Player: "Pozajtra o tretej, vlastne radšej o pol štvrtej, na dve hoďky."
{{"date":"2026-03-14","start":"15:30","duration_min":120,"court":"any","question":null}}

Player: "Na ten kurt čo naposledy, v sobotu o jedenástej na hodinu."
{{"date":"2026-03-14","start":"11:00","duration_min":60,"court":null,"question":"Ktorý kurt chcete?"}}

Current reservation: {{"date":"2026-03-13","start":null,"duration_min":90,"court":1,"question":"O koľkej poobede?"}}
Player: "o štvrtej"
{{"date":"2026-03-13","start":"16:00","duration_min":90,"court":1,"question":null}}
"""


@cache
def get_client(base_url: str = OPENROUTER_URL) -> OpenAI:
    api_key = os.environ["OPENROUTER_API_KEY"] if base_url == OPENROUTER_URL else "local"
    return OpenAI(base_url=base_url, api_key=api_key)


def build_user_message(message: str, reservation: Reservation, now: datetime, facility: dict) -> str:
    hours = facility["opening_hours"]
    courts = ", ".join(f"{court['id']} {court['name']}" for court in facility["courts"])
    return (
        f"Now: {now:%Y-%m-%d %H:%M} ({WEEKDAYS[now.weekday()]}), timezone {facility['timezone']}\n"
        f"Opening hours: {hours['open']}–{hours['close']}\n"
        f"Courts: {courts}\n"
        f"Current reservation: {reservation.model_dump_json()}\n"
        f'Player: "{message}"'
    )


def complete(
    message: str,
    reservation: Reservation,
    now: datetime,
    facility: dict,
    model: str,
    provider: str | None = None,
    effort: str | None = None,
    base_url: str = OPENROUTER_URL,
) -> ChatCompletion:
    extra_body: dict = {}
    if base_url == OPENROUTER_URL:
        if effort:
            extra_body["reasoning"] = {"effort": effort}
        if provider:
            extra_body["provider"] = {"order": [provider], "allow_fallbacks": False}
    elif effort:
        extra_body["chat_template_kwargs"] = {"enable_thinking": effort != "none"}
    return get_client(base_url).chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_user_message(message, reservation, now, facility)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        extra_body=extra_body,
    )


def parse(response: ChatCompletion) -> Reservation:
    return Reservation.model_validate_json(response.choices[0].message.content or "")


def extract(message: str, reservation: Reservation, now: datetime, facility: dict) -> Reservation:
    response = complete(
        message,
        reservation,
        now,
        facility,
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
        provider=os.getenv("LLM_PROVIDER") or None,
        effort=os.getenv("LLM_REASONING_EFFORT", "low"),
    )
    return parse(response)


def summarize(reservation: Reservation) -> str:
    return (
        f"Rozumiem: {format_date(reservation.date)} o {reservation.start}, "
        f"{reservation.duration_min} min, kurt: {format_court(reservation.court)}."
    )


def reply(message: str, reservation: Reservation) -> tuple[str, Reservation]:
    facility = load_facility()
    now = datetime.now(ZoneInfo(facility["timezone"]))
    try:
        updated = extract(message, reservation, now, facility)
    except ValidationError:
        return "Prepáčte, nerozumel som. Skúste to prosím povedať inak.", reservation
    if updated.question:
        return updated.question, updated
    if not updated.is_complete():
        missing = ", ".join(FIELD_LABELS[name] for name in updated.missing())
        return f"Ešte potrebujem vedieť: {missing}.", updated
    return summarize(updated), updated

