# Courtbee voice booking eval

Week 4 exercise of the LLM Engineering course.

A player says a booking request in Slovak, for example "zajtra o pol piatej dvojku na hodinu". A model turns the sentence into a reservation: date, start time, duration and court. When the sentence leaves something open, the model has to ask instead of guessing.

This project measures which model does that best for Courtbee, on 40 hand-written Slovak sentences with expected answers. Every call records two things: whether the reservation is correct, and how long the answer took.

## Layout

| Path | What it holds |
|---|---|
| `data/cases.json` | the test set: 40 sentences and their expected reservations; nothing from it goes into the prompt |
| `data/dev_cases.json` | the dev set: 17 other sentences with another date and other opening hours, for tuning the prompt |
| `courtbee_voice_eval/` | the extraction call and the evaluation runner |
| `results/` | one CSV per run |
| `tests/` | unit tests |

## Setup

```bash
uv sync
cp .env.example .env
```

All hosted models go through OpenRouter with the `openai` client library. The local model runs behind any OpenAI-compatible server, such as `mlx_lm.server`.

## Courtbee Voice Manager

A Gradio UI with a chat on the left and the current reservation on the right.

```bash
uv run python -m courtbee_voice_eval.app
```

The chat calls `reply()` in `courtbee_voice_eval/assistant.py`, which takes the player's message and the current `Reservation` and returns the answer and the updated `Reservation`.

## Evaluation

```bash
uv run python -m courtbee_voice_eval.evaluate data/dev_cases.json \
  --model "deepseek/deepseek-v4.1-flash-20260910@together#none" \
  --model "google/gemini-3.8-flash#low" \
  --repeats 3
```

Each `--model` is `model[@provider][#effort]`:

- `@provider` pins one OpenRouter provider with no fallback. Without it, OpenRouter picks a provider per call, and the answers can differ between providers.
- `#effort` sets the reasoning effort (`none`, `low`, `medium`, …). Without it, the model's API default applies.
- `local:<model>[#effort]` calls the server in `LOCAL_LLM_SERVER` instead of OpenRouter.

With no `--model`, the run uses `LLM_MODEL`, `LLM_PROVIDER` and `LLM_REASONING_EFFORT` from `.env`.

Every case and every follow-up is one turn. Each turn gets one outcome:

| Outcome | Meaning | What it costs Courtbee |
|---|---|---|
| `correct` | all four fields match, and the model asks exactly when a field is missing | nothing |
| `silent_wrong` | the model asks nothing, and the reservation is wrong | a wrong booking nobody notices |
| `wrong_value` | the model asks, but a field it filled is wrong | a wrong booking after the answer, unless the player notices |
| `unnecessary_question` | the model asks about something the player already said | one extra round of conversation |
| `invalid` | API error or JSON that does not fit the schema | the player has to repeat |

The run prints the failed turns and a summary per model, and writes every turn to `results/<run>_<cases>.csv` with latency, tokens, cost and the provider that served it. Latency is the time of the whole call, not the time to the first token.

Tune the prompt on `data/dev_cases.json`. Run `data/cases.json` only to compare finished prompts and models.
