"""Run with .venv/Scripts/python.exe test_ui.py. Never writes the shop database."""
import base64
import io
import json
import os
import sqlite3
import tempfile
import wave
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from streamlit.testing.v1 import AppTest
from app import today, rupees, preview_values, Sales, Credit, Repayment, Proposal, save_batch

# Mock only live network calls. UI, validation, transactions, and SQLite reads are real.
wav = io.BytesIO()
with wave.open(wav, "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(16000)
    audio.writeframes(b"\x00\x00" * 1600)
AUDIO = base64.b64encode(wav.getvalue()).decode()
MOCKS = """
_real_interpret = interpret
def interpret(text):
    st.session_state["understanding_calls"] = st.session_state.get("understanding_calls", 0) + 1
    if text == "network error":
        import httpx
        raise httpx.ConnectError("[WinError 10013] socket access forbidden")
    return _real_interpret(text)
def synthesize_confirmation(text):
    st.session_state["speech_calls"] = st.session_state.get("speech_calls", 0) + 1
    if st.session_state.get("speech_should_succeed"):
        import base64
        return [base64.b64decode("AUDIO_PLACEHOLDER")]
    import httpx
    raise httpx.ConnectError("[WinError 10013] socket access forbidden")
""".replace("AUDIO_PLACEHOLDER", AUDIO)


def html(at):
    return "\n".join(element.proto.body for element in at.get("html"))


def button(at, name):
    return next(b for b in at.button if b.label == name)


def set_text(at, text):
    at.text_area(key="instruction").set_value(text).run()
    assert not at.exception


def propose(at, payload):
    set_text(at, payload)
    button(at, "Understand instruction").click().run()
    assert not at.exception


def count_batches(db):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0]


def main():
    os.environ["SARVAM_API_KEY"] = "offline-test"
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "ui.sqlite3"
        source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        source = source.replace('DB_PATH = Path(__file__).with_name("dukaanmitra.sqlite3")', "DB_PATH = Path(" + repr(str(db)) + ")")
        source = source.replace('if __name__ == "__main__":', MOCKS + '\nif __name__ == "__main__":')
        at = AppTest.from_string(source, default_timeout=20).run()
        assert not at.exception and not db.exists()
        assert at.radio(key="input_mode").value == "Speak"
        assert [m.value for m in at.metric] == ["₹0.00", "₹0.00", "0"]
        assert "Key configured · unverified" in html(at)
        assert "API verified" not in html(at) and "A clean slate" in html(at)
        button(at, "Aaj ki total bikri 1200 rupaye.").click().run()
        assert at.radio(key="input_mode").value == "Type"
        assert at.text_area(key="instruction").value == "Aaj ki total bikri 1200 rupaye."
        assert "proposal" not in at.session_state and "understanding_calls" not in at.session_state
        assert not db.exists()
        day = today().isoformat()
        tomorrow = (today() + timedelta(days=1)).isoformat()
        payload = json.dumps({"actions": [
            {"action": "set_daily_sales", "day": day, "amount_paise": 120000},
            {"action": "add_credit", "day": day, "customer": "Ramesh", "amount_paise": 50000},
            {"action": "add_credit", "day": day, "customer": "Sita", "amount_paise": 25000},
            {"action": "add_purchase_item", "day": tomorrow, "item": "Bread", "quantity": "20 packets"},
            {"action": "add_purchase_item", "day": tomorrow, "item": "Milk", "quantity": "10 litres"},
        ]})
        propose(at, payload)
        assert not db.exists() and "Not saved yet" in html(at)
        assert "₹0.00" in html(at) and "₹500.00" in html(at)
        assert button(at, "Confirm & save").disabled is False
        set_text(at, payload + " ")
        assert button(at, "Confirm & save").disabled
        assert any("earlier instruction" in warning.value for warning in at.warning)
        # Reverting an edit is still a new command; a fresh proposal is required.
        set_text(at, payload)
        assert button(at, "Confirm & save").disabled and not db.exists()
        button(at, "Cancel").click().run()
        assert "proposal" not in at.session_state and not db.exists()
        assert any("Cancelled" in info.value for info in at.info)
        button(at, "Understand instruction").click().run()
        stored_proposal = at.session_state["proposal"]
        button(at, "Confirm & save").click().run()
        assert not at.exception and db.exists()
        assert [m.value for m in at.metric] == ["₹1,200.00", "₹750.00", "2"]
        assert "Saved to your shop notebook" in html(at)
        assert "Tomorrow ·" in html(at) and "20 packets" in html(at) and "10 litres" in html(at)
        assert any("changes are saved" in warning.value for warning in at.warning)
        assert count_batches(db) == 1 and at.session_state["speech_calls"] == 1
        at.run()
        assert not at.exception and at.session_state["speech_calls"] == 1 and count_batches(db) == 1
        button(at, "Retry spoken confirmation").click().run()
        assert not at.exception and at.session_state["speech_calls"] == 2 and count_batches(db) == 1
        at.session_state["speech_should_succeed"] = True
        button(at, "Retry spoken confirmation").click().run()
        assert not at.exception and at.session_state["speech_calls"] == 3 and count_batches(db) == 1
        assert at.session_state["confirmation_audio"] == [wav.getvalue()]
        assert "API verified" in html(at)
        # Replay the exact original batch through the actual persistence function.
        assert not save_batch(Proposal.model_validate(stored_proposal), db)[0]
        assert count_batches(db) == 1
        set_text(at, "network error")
        assert "saved" not in at.session_state and "Saved to your shop notebook" not in html(at)
        button(at, "Understand instruction").click().run()
        assert not at.exception and at.error and "blocked" in at.error[0].value
        assert "Last API request failed" in html(at) and count_batches(db) == 1
        assert not any(b.label == "Confirm & save" for b in at.button)
        propose(at, '{"actions":[],"clarification":"Which customer?"}')
        assert any("Which customer?" in w.value for w in at.warning)
        propose(at, '{"actions":[{"action":"delete_all"}]}')
        assert at.error and count_batches(db) == 1
        # Speak-mode transcript edits have the same stale-proposal protection.
        at.radio(key="input_mode").set_value("Speak").run()
        at.session_state["spoken_draft"] = payload
        at.session_state["transcript_ready"] = True
        at.run()
        assert at.text_area(key="transcript").value == payload
        button(at, "Understand instruction").click().run()
        assert not at.exception and not button(at, "Confirm & save").disabled
        at.text_area(key="transcript").set_value(payload + " ").run()
        assert button(at, "Confirm & save").disabled and count_batches(db) == 1
        button(at, "Cancel").click().run()
        assert not at.exception and count_batches(db) == 1
        # Complete-batch debt preview and past sales totals come from saved data.
        other_day = today() - timedelta(days=2)
        history = Proposal(actions=(Sales(action="set_daily_sales", day=other_day, amount_paise=70000),))
        save_batch(history, db)
        actions = (
            Credit(action="add_credit", day=today(), customer="ramesh", amount_paise=10000),
            Repayment(action="record_repayment", day=today(), customer="Ramesh", amount_paise=20000),
            Sales(action="set_daily_sales", day=other_day, amount_paise=80000),
        )
        before, after, sales = preview_values(actions, {"sales":120000, "debts":[("Ramesh",50000)]}, db)
        assert before["ramesh"] == 50000 and after["ramesh"] == 40000
        assert sales[other_day.isoformat()] == 70000 and count_batches(db) == 2
        assert rupees(123456789) == "₹12,34,567.89" and rupees(-101) == "-₹1.01"
        print("PASS: initial/empty, safe suggestions, proposals, stale typed/transcript edits, cancel/no writes, saved summary/receipt, date groups, audio success/failure/retry, API errors, clarification, invalid action, duplicate save, complete-batch previews, Indian currency.")


if __name__ == "__main__":
    main()
