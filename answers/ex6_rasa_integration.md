# Ex6 - Rasa structured half

## Your answer

The RasaStructuredHalf subclass overrides run() to POST a booking
intent to Rasa's REST webhook and interpret the response. Input
payload flows: loop half produces raw booking data → StructuredHalf
calls normalise_booking_payload (via validator.py) to produce a
Rasa-shaped message with canonical types → urllib POST to Rasa →
parse response for {action: committed} or {action: rejected} custom
slots.

For offline mode we spawn a stdlib http.server thread that mimics
Rasa's REST webhook. The mock mirrors `ActionValidateBooking`:
`party_size > 8` returns `{action: rejected, reason: party_too_large}`,
`deposit_gbp > 300` returns `{action: rejected, reason: deposit_too_high}`,
and everything else returns a deterministic `BK-<sha1>` reference
identical in shape to the one the real Rasa action emits. That parity
is exactly what lets Ex7's bridge exercise the reverse-handoff path
in offline mode without needing a Rasa license.

A second design note: the response parser accepts both the mock's
structured `custom` payload AND real Rasa's plain text utterances
(`Booking confirmed. Reference: BK-7D401E9E.`) - Rasa returns text
only from `utter_booking_confirmed` / `utter_booking_rejected`, so
the parser falls back to string matching when no `custom` field is
present.

Three design choices worth noting: (1) we raise ValidationFailed in
normalise_booking_payload and catch it in run() rather than letting
it propagate; the StructuredHalf contract demands a HalfResult. (2)
Network errors return success=False with SA_EXT_SERVICE_UNAVAILABLE
 - the caller decides whether to retry. (3) The stable sender_id is a
hash of (venue+date+time) so the Rasa tracker is consistent across
retries within one session.

## Citations

- `starter/rasa_half/validator.py::normalise_booking_payload` + helpers
- `starter/rasa_half/structured_half.py::RasaStructuredHalf.run` + `_MockRasaHandler`
- `rasa_project/actions/actions.py::ActionValidateBooking.run` - enforces `MAX_PARTY_SIZE_FOR_AUTO_BOOKING=8` and `MAX_DEPOSIT_FOR_AUTO_BOOKING_GBP=300`
- `sessions/examples/ex6-rasa-half/sess_967bc6920b07/logs/trace.jsonl` - real Rasa Pro 3.16 confirming `BK-7D401E9E` for `party_size=6, deposit_gbp=200`
