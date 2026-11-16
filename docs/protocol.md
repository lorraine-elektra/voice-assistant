# WebSocket message format

The browser and the backend talk over one WebSocket at `/ws`. Every message is a JSON
object with a `type` field. This file is the agreement between frontend and backend.

A **turn** is one user message and the reply to it. The backend numbers turns 1, 2, 3
and stamps every reply message with its turn, so the browser can ignore anything stale.

## Browser to backend

| type | fields | meaning |
| --- | --- | --- |
| `user_text` | `text` | What the user said or typed. Starts a new turn. If a reply is still in progress it is cancelled first (barge in). |
| `stop` | | Cancel the reply in progress. |

## Backend to browser

| type | fields | meaning |
| --- | --- | --- |
| `ready` | `brain` | Sent once after connecting. `brain` is `mock` or `claude`. |
| `status` | `turn`, `state` | What the backend is doing. `state` is `thinking` or `searching` (a web search is running). |
| `sentence` | `turn`, `index`, `text` | One finished sentence of the reply. `index` counts from 0 inside the turn. Speak them in order. |
| `search_failed` | `turn` | The web search did not work. The reply carries on from what the assistant already knows. |
| `sources` | `turn`, `sources` | Web pages the answer used, as a list of `{"title", "url"}`. Show them as links. Never speak them. |
| `done` | `turn` | The reply is complete. |
| `cancelled` | `turn` | The reply was cancelled. Nothing more arrives for this turn. |
| `error` | `message`, maybe `turn` | Something went wrong. `message` is safe to show to the user. |

## Barge in rule

When `user_text` or `stop` arrives, the backend stops the reply in progress before it
does anything else. After `cancelled`, no `sentence` for that turn is ever sent.

## Example

```
browser  {"type": "user_text", "text": "Hello there"}
backend  {"type": "status", "turn": 1, "state": "thinking"}
backend  {"type": "sentence", "turn": 1, "index": 0, "text": "Hi!"}
backend  {"type": "sentence", "turn": 1, "index": 1, "text": "How can I help?"}
backend  {"type": "done", "turn": 1}
```

## Example with a web search

When a search starts the backend sends the `searching` status and then a short filler
sentence ("Let me look that up.") to speak, so there is no long silence.

```
browser  {"type": "user_text", "text": "What is the weather in Paris today?"}
backend  {"type": "status", "turn": 2, "state": "thinking"}
backend  {"type": "status", "turn": 2, "state": "searching"}
backend  {"type": "sentence", "turn": 2, "index": 0, "text": "Let me look that up."}
backend  {"type": "status", "turn": 2, "state": "thinking"}
backend  {"type": "sentence", "turn": 2, "index": 1, "text": "According to ..."}
backend  {"type": "sources", "turn": 2, "sources": [{"title": "...", "url": "https://..."}]}
backend  {"type": "done", "turn": 2}
```
