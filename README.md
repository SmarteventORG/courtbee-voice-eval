# Courtbee voice booking eval

Week 4 exercise of the LLM Engineering course.

A player says a booking request in Slovak, for example "zajtra o pol piatej dvojku na hodinu". A model turns the sentence into a reservation: date, start time, duration and court. When the sentence leaves something open, the model has to ask instead of guessing.

This project measures which model does that best for Courtbee, on 40 hand-written Slovak sentences with expected answers. Every call records two things: whether the reservation is correct, and how long the answer took.

## Layout

| Path | What it holds |
|---|---|
| `data/` | the test sentences and their expected reservations |
| `courtbee_voice_eval/` | the extraction call and the evaluation runner |
| `results/` | one CSV per run |
| `tests/` | unit tests |

## Setup

```bash
uv sync
cp .env.example .env
```

All hosted models go through OpenRouter with the `openai` client library. The local model runs behind any OpenAI-compatible server, such as `mlx_lm.server`.
