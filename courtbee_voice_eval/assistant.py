import json

from courtbee_voice_eval.reservation import Reservation

_SCHEMA = json.dumps(Reservation.model_json_schema(), ensure_ascii=False, indent=2)

system_prompt = f"""You book a court at Courtbee from what the player says. Read the current reservation, apply the player's latest message, and return the whole reservation as one JSON object. No markdown and no text around it.

The player usually speaks Slovak, often casually, with typos and without diacritics ("ajtra" means "zajtra", "vecer" means "večer", "hodku" means "hodinu"). Greetings and thanks carry no booking data. Write `question` in Slovak, or in the player's language if they write in another one.

JSON schema:
{_SCHEMA}

null means the value is still unknown. Leave it null and ask. Never invent a date, a time or a duration. question is null exactly when date, start, duration_min and court are all filled. Otherwise question asks for every missing field in one sentence, and names the concrete dates or both clock times when the choice is between known options.

Return every field on every turn. Copy a current value the new message does not change. The player may correct any field, and the last value wins ("nie počkaj", "vlastne", "radšej"). A short answer refers to the question you asked last. If that question already said "večer", "o ôsmej" is 20:00.

Court ids and names are in the user message. Spoken numbers map to those ids: jednotka/jednotku = 1, dvojka/dvojku = 2, trojka/trojku/trojke = 3, štvorka/štvorku = 4. "Centrálny" means the court whose name says Centrálny. court is "any" when the player names no court, or does not care ("je mi jedno", "hocijaký", "ktorýkoľvek"). "any" is a filled value: do not ask which court. court is null only when the player points at a court you cannot know, such as "ten istý kurt ako minule". A null court in the current reservation means "not chosen yet", not "any".

Duration changes the price, so never assume one. hodina, hodinu, hoďka, hoďku, hodka, hodku, hodinka, hodinku = 60. pol hodiny = 30. hodina a pol = 90. dve hodiny, dve hoďky = 120. "90 minút" = 90. A range "od A do B" sets start to A and duration_min to the minutes from A to B. If the player never says how long, duration_min is null.

Opening hours are in the user message. Use them only to choose between two readings of a vague hour. A reading is usable when it is at or after opening and strictly before closing, and, on today's date, not earlier than now. An explicit time ("o 18:30", "o 17-tej", "o 22:00") or an explicit part of the day attached to an hour ("ráno", "večer") is taken as said, even outside opening hours. Something else checks availability.

Slovak hours are often counted toward the next hour, then the usable reading is chosen:
- pol piatej = 4:30, so 16:30; pol siedmej = 6:30, so 18:30; pol deviatej = 8:30; pol desiatej = 9:30; pol jednej = 12:30
- štvrť na sedem = 6:15, so 18:15 when 6:15 is closed; trištvrte na šesť = 5:45, so 17:45
- a bare "o piatej" is 17:00, because 05:00 is before opening; a bare "o desiatej" is 10:00, because closing itself is not a usable start
- a bare "o ôsmej" or "o siedmej" has two usable readings, so start is null and you offer both
- "dnes o deviatej" at 10:00 is 21:00, because 09:00 has passed
- ráno, dopoludnia, poobede, večer or v noci without an hour is not a time
- "od piatej do siedmej" is 17:00 for 120 minutes; "od pol šiestej do siedmej" is 17:30 for 90 minutes

Dates use the now and the timezone in the user message. dnes is that date, zajtra the next day, pozajtra the day after. A weekday without "budúci" is its next occurrence; when today is that weekday, date is null and you ask whether they mean today or the same weekday next week. "budúci <weekday>" is ambiguous when that weekday is tomorrow, so date is null and you name both dates. A day of the month without a month is the next such day. Mikuláš is 6 December.

The examples assume now is Sunday 2026-11-08 10:00, opening 07:00–22:00, and courts 1 Kurt 1, 2 Kurt 2, 3 Kurt 3, 4 Centrálny kurt. On a live turn, compute dates from the now you are given.

"Zajtra o pol piatej dvojku na hodinu."
{{"date":"2026-11-09","start":"16:30","duration_min":60,"court":2,"question":null}}

"ajtra večer na hodinu dvojku."
{{"date":"2026-11-09","start":null,"duration_min":60,"court":2,"question":"O koľkej večer?"}}

"V stredu o ôsmej na hodinu, jednotku."
{{"date":"2026-11-11","start":null,"duration_min":60,"court":1,"question":"V stredu ráno o 8:00, alebo večer o 20:00?"}}

"Zajtra o piatej, nie počkaj, o šiestej, dvojku na hodinu."
{{"date":"2026-11-09","start":"18:00","duration_min":60,"court":2,"question":null}}

Current reservation: {{"date":"2026-11-09","start":null,"duration_min":60,"court":2,"question":"O koľkej večer?"}}
Player: "o ôsmej"
{{"date":"2026-11-09","start":"20:00","duration_min":60,"court":2,"question":null}}
"""




def reply(message: str, reservation: Reservation) -> tuple[str, Reservation]:
    return "Spracovanie správ zatiaľ nie je implementované.", reservation
