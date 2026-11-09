import argparse
import csv
import json
import os
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAIError
from pydantic import ValidationError

from courtbee_voice_eval.assistant import DEFAULT_MODEL, OPENROUTER_URL, complete, parse
from courtbee_voice_eval.reservation import Reservation

FIELDS = ("date", "start", "duration_min", "court")
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
LOCAL_PREFIX = "local:"
COLUMNS = [
    "run_id",
    "spec",
    "model",
    "provider",
    "served_by",
    "effort",
    "cases_file",
    "repeat",
    "case_id",
    "message",
    "outcome",
    "latency_s",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
    "expected",
    "got",
    "question",
    "error",
]


@dataclass(frozen=True)
class ModelSpec:
    spec: str
    model: str
    provider: str | None
    effort: str | None
    base_url: str


@dataclass(frozen=True)
class Turn:
    case_id: str
    message: str
    state: Reservation
    expected: dict


def parse_spec(spec: str) -> ModelSpec:
    rest, _, effort = spec.partition("#")
    model, _, provider = rest.partition("@")
    base_url = OPENROUTER_URL
    if model.startswith(LOCAL_PREFIX):
        model = model.removeprefix(LOCAL_PREFIX)
        base_url = os.getenv("LOCAL_LLM_SERVER", "http://127.0.0.1:8080/v1")
    return ModelSpec(spec, model, provider or None, effort or None, base_url)


def default_spec() -> str:
    spec = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    if provider := os.getenv("LLM_PROVIDER"):
        spec += f"@{provider}"
    if effort := os.getenv("LLM_REASONING_EFFORT"):
        spec += f"#{effort}"
    return spec


def load_turns(cases: list[dict]) -> list[Turn]:
    turns = []
    for case in cases:
        turns.append(Turn(str(case["id"]), case["text"], Reservation(), case["expected"]))
        for number, followup in enumerate(case.get("followups", []), 1):
            state = Reservation(**case["expected"], question=followup["question"])
            turns.append(Turn(f"{case['id']}.{number}", followup["answer"], state, followup["expected"]))
    return turns


def classify(got: Reservation, expected: dict) -> str:
    fields_ok = all(getattr(got, name) == expected[name] for name in FIELDS)
    asks = bool(got.question) or not got.is_complete()
    should_ask = any(expected[name] is None for name in FIELDS)
    if fields_ok and asks == should_ask:
        return "correct"
    if not asks:
        return "silent_wrong"
    wrong = [name for name in FIELDS if getattr(got, name) is not None and getattr(got, name) != expected[name]]
    return "wrong_value" if wrong else "unnecessary_question"


def run_turn(spec: ModelSpec, turn: Turn, now: datetime, facility: dict) -> dict:
    row = {"case_id": turn.case_id, "message": turn.message, "expected": json.dumps(turn.expected, ensure_ascii=False)}
    started = time.perf_counter()
    try:
        response = complete(
            turn.message,
            turn.state,
            now,
            facility,
            model=spec.model,
            provider=spec.provider,
            effort=spec.effort,
            base_url=spec.base_url,
        )
    except OpenAIError as error:
        return row | {"outcome": "invalid", "latency_s": round(time.perf_counter() - started, 3), "error": repr(error)[:300]}
    row["latency_s"] = round(time.perf_counter() - started, 3)
    row["served_by"] = getattr(response, "provider", None)
    if response.usage:
        row["prompt_tokens"] = response.usage.prompt_tokens
        row["completion_tokens"] = response.usage.completion_tokens
        row["cost_usd"] = getattr(response.usage, "cost", None)
    try:
        got = parse(response)
    except ValidationError as error:
        content = response.choices[0].message.content if response.choices else None
        return row | {"outcome": "invalid", "got": content, "error": str(error).splitlines()[0]}
    got_fields = {name: getattr(got, name) for name in FIELDS}
    return row | {
        "outcome": classify(got, turn.expected),
        "got": json.dumps(got_fields, ensure_ascii=False),
        "question": got.question,
    }


def summarize(spec: str, rows: list[dict]) -> str:
    counts = Counter(row["outcome"] for row in rows)
    latencies = sorted(row["latency_s"] for row in rows if row.get("latency_s") is not None)
    p90 = statistics.quantiles(latencies, n=10)[-1] if len(latencies) > 1 else latencies[0]
    cost = sum(row.get("cost_usd") or 0 for row in rows)
    return (
        f"{spec}\n"
        f"  correct {counts['correct']}/{len(rows)}"
        f"  silent_wrong {counts['silent_wrong']}"
        f"  wrong_value {counts['wrong_value']}"
        f"  unnecessary_question {counts['unnecessary_question']}"
        f"  invalid {counts['invalid']}\n"
        f"  latency median {statistics.median(latencies):.2f}s  p90 {p90:.2f}s"
        f"  cost ${cost:.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Courtbee booking cases against one or more models.")
    parser.add_argument("cases", type=Path, help="data/dev_cases.json or data/cases.json")
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="model[@provider][#effort], or local:model[#effort]; repeat to compare models",
    )
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()

    data = json.loads(args.cases.read_text(encoding="utf-8"))
    context = data["context"]
    facility = {key: context[key] for key in ("timezone", "opening_hours", "courts")}
    now = datetime.fromisoformat(context["now"]).replace(tzinfo=ZoneInfo(context["timezone"]))
    turns = load_turns(data["cases"])
    specs = [parse_spec(spec) for spec in args.models or [default_spec()]]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / f"{run_id}_{args.cases.stem}.csv"
    summaries = []
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        for spec in specs:
            rows = []
            for repeat in range(1, args.repeats + 1):
                for turn in turns:
                    row = run_turn(spec, turn, now, facility) | {
                        "run_id": run_id,
                        "spec": spec.spec,
                        "model": spec.model,
                        "provider": spec.provider,
                        "effort": spec.effort,
                        "cases_file": args.cases.name,
                        "repeat": repeat,
                    }
                    writer.writerow(row)
                    file.flush()
                    rows.append(row)
                    if row["outcome"] != "correct":
                        print(f"{spec.spec} r{repeat} {turn.case_id:5} {row['outcome']:20} {turn.message}")
            summaries.append(summarize(spec.spec, rows))
    print()
    print("\n".join(summaries))
    print(f"\nWrote {output}")


if __name__ == "__main__":
    main()
