import gradio as gr

from courtbee_voice_eval.assistant import reply
from courtbee_voice_eval.reservation import FIELD_LABELS, Reservation, format_court, format_date

TITLE = "Courtbee Voice Manager"


def render_reservation(reservation: Reservation) -> str:
    date = format_date(reservation.date) if reservation.date else "—"
    start = reservation.start or "—"
    duration = f"{reservation.duration_min} min" if reservation.duration_min else "—"
    court = format_court(reservation.court) if reservation.court is not None else "—"
    if reservation.is_complete():
        status = "Pripravená na rezerváciu"
    else:
        status = "Chýba: " + ", ".join(FIELD_LABELS[name] for name in reservation.missing())
    return (
        "### Rezervácia\n\n"
        "| Pole | Hodnota |\n|---|---|\n"
        f"| Dátum | {date} |\n"
        f"| Začiatok | {start} |\n"
        f"| Dĺžka | {duration} |\n"
        f"| Kurt | {court} |\n\n"
        f"**Stav:** {status}"
    )


def respond(message: str, history: list[dict], reservation: Reservation):
    if not message.strip():
        return "", history, reservation, render_reservation(reservation)
    answer, updated = reply(message, reservation)
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    return "", history, updated, render_reservation(updated)


def reset():
    empty = Reservation()
    return [], empty, render_reservation(empty)


def build_app() -> gr.Blocks:
    with gr.Blocks(title=TITLE) as app:
        gr.Markdown(f"# {TITLE}")
        reservation = gr.State(Reservation())
        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(label="Rozhovor", height=480)
                message = gr.Textbox(
                    placeholder="Napríklad: Zajtra o pol piatej dvojku na hodinu.",
                    show_label=False,
                    submit_btn="Odoslať",
                )
            with gr.Column(scale=2):
                reservation_view = gr.Markdown(render_reservation(Reservation()))
                new_reservation = gr.Button("Nová rezervácia")

        message.submit(
            respond,
            inputs=[message, chatbot, reservation],
            outputs=[message, chatbot, reservation, reservation_view],
        )
        new_reservation.click(reset, outputs=[chatbot, reservation, reservation_view])
    return app


def main() -> None:
    build_app().launch()


if __name__ == "__main__":
    main()
