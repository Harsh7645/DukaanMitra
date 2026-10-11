# DukaanMitra

A small Streamlit notebook for Indian kirana shops: daily sales totals, customer udhaar, repayments, and dated purchase plans. Python, SQLite, Pydantic, and the official sarvamai SDK; no authentication, payments, or agent framework.

## Run (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Set SARVAM_API_KEY in this terminal using your secret manager or Windows environment settings.
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Open http://127.0.0.1:8501. The app reads SARVAM_API_KEY from the environment; it never writes or prints the key. Restart the server after changing its environment. Get a key from https://dashboard.sarvam.ai/admin.

## Use

1. Type a Hindi, Hinglish, or English instruction, for example: `Aaj ki bikri 2500 rupaye. Ramesh ko 200 rupaye udhaar.`
2. Select **Propose actions**. Answer any clarification by editing the full instruction and proposing again.
3. Review the exact dates, customers, amounts, and purchase quantities. **Confirm** saves the entire batch; **Cancel** discards it.
4. Read today's sales, customer debts, and dated purchase plans in the dashboard. A Hindi confirmation is generated from the committed actions, with a Bulbul audio player when synthesis succeeds.
5. Alternatively, expand **Microphone input**, record up to 30 seconds with `st.audio_input`, select **Transcribe recording**, edit the Saaras transcript, then select **Propose from edited transcript**. Microphone permission is required; typed input remains available.

The expandable typed JSON example works without an API key and is useful for an offline demo. All JSON money is integer paise: ₹10 = 1000 paise. Natural-language parsing requires Sarvam.

## Data rules

- Only `set_daily_sales`, `add_credit`, `record_repayment`, and `add_purchase_item` are accepted. Pydantic rejects unknown fields, unknown actions, missing names/quantities, invalid dates, booleans, fractional/string paise, and nonpositive credit/repayment amounts. A sales total may be zero.
- Sales totals are **set**, never blindly added. Udhaar and repayments do not change sales. Purchases are plans and do not change inventory.
- Dates and commit timestamps use Asia/Kolkata. Unspecified instruction dates default to the local shop date; explicit dates are shown for review.
- Repayments are limited to debt already saved. Multiple repayments in one proposal share that limit; new credit in the same batch cannot fund a repayment. Balances are rechecked under a SQLite write lock at confirmation.
- Customer names are matched by Unicode normalization, case folding, and whitespace normalization. No fuzzy matching or guessed customers.
- Only Confirm creates/writes `dukaanmitra.sqlite3`. Proposal generation, cancellation, reruns, and dashboard reads do not write SQLite. Schema creation, the unique batch record, sales, debt events, and purchase plans share one transaction. A failed batch rolls back entirely.
- A UUID primary key prevents repeated confirmation of the same proposal, including after a Streamlit rerun. Deliberately creating a new proposal creates a new batch; identical instructions in separate proposals can be legitimate separate transactions.
- Speech runs after the transaction commits. Failed synthesis never undoes a save. **Retry spoken confirmation** only retries speech from the committed summary, never the database write. Ordinary reruns do not repeat speech requests. Long summaries are split between action sentences to stay within Bulbul's character limit.
- Database files, the local environment, logs, and secrets are excluded by `.gitignore`.

## Checks

```powershell
.\.venv\Scripts\python.exe app.py --check
```

The built-in check uses a temporary database, not the shop database. It covers validation, dashboard read-only behavior, excessive/cumulative repayments, atomic rollback, daily total replacement, normalized customer matching, duplicate and simultaneous confirmation, and rollback after an injected database failure. It also checks JSON extraction, transcription, Hindi summary generation, and audio decoding using a mocked SDK; those checks do not call live APIs.

## Official API documentation

Implementation checked against https://docs.sarvam.ai/api-reference/metaprompt and https://docs.sarvam.ai/api-reference/text-to-speech/convert. Chat uses `client.chat.completions`, `sarvam-105b`, and JSON output.

## Verification in this workspace

- Python syntax, `app.py --check`, and `pip check` passed.
- Streamlit AppTest passed for typed JSON -> proposals -> Cancel/no writes -> Confirm -> dashboard, reruns, clarification, invalid actions, and speech failure/retry without duplicate writes. Tests used temporary databases.
- The installed Sarvam SDK was exercised with offline HTTP responses for chat JSON, Saaras multipart upload, and Bulbul audio.
- Live Bulbul v3 synthesis passed (valid 1.37-second WAV), live Saaras v4 transcribed it as a ₹100 sales instruction, and live sarvam-105b returned the expected 10000-paise sales action. An ambiguous Hindi instruction returned a clarification question. These checks did not write to the shop database.
- Browser microphone permissions/capture and audible speaker playback still require a user-device check.
- Vision was deferred to keep the hackathon focused on the requested core and voice flows.

## Connection troubleshooting

A `ConnectError` with Windows error 10013 means the launching runtime blocked outbound sockets. Restart Streamlit from a network-enabled terminal with SARVAM_API_KEY in that terminal's environment. The server must be relaunched; changing the key or retrying a request does not change its network permissions. The app displays this cause explicitly, and typed JSON remains usable.
