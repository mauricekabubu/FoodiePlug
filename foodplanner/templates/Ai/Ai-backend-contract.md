# FoodiePlug AI — backend contract for `ai.js`

The page never invents an answer. `data-chat-url="#"` (in `assistant.html`) means "not connected":
the UI says so honestly. Replace the `#` values in `<div id="ai-config">` when these routes exist:

| attribute | value |
|---|---|
| `data-chat-url` | `POST` chat endpoint, e.g. `{% url 'ai:chat' %}` |
| `data-conversation-url` | must end in `/0/` (swapped for the id): `GET` load · `PATCH` rename · `DELETE` delete |

All requests are same-origin with `X-CSRFToken`. The **backend** decides the user (`request.user`);
the client never sends a user id.

## POST chat

Request
```json
{ "message": "What can I cook tonight?", "conversation_id": null, "context": { "sources": ["pantry", "meal_plan"] } }
```
`context.sources` lists only the switches the user left ON. Retrieve nothing else.

Success (200)
```json
{
  "conversation_id": 12,
  "conversation_title": "What can I cook tonight?",
  "response": "You already have beans, rice and sukuma wiki.\n\nNothing extra to buy.",
  "intent": "meal_suggestion",
  "cards": [
    {
      "type": "meal_recommendation",
      "title": "Beans + Rice + Sukuma wiki",
      "basis": "calculated",
      "highlight": { "label": "Estimated additional cost", "value": "KES 0" },
      "items": [ { "name": "Beans", "status": "have" }, { "name": "Onions", "status": "missing", "note": "1 piece" } ],
      "actions": [ { "kind": "api", "label": "Add onions to Shopping", "endpoint": "/api/ai/actions/add-shopping/",
                     "payload": { "food_id": 7, "quantity": "1", "unit": "piece" },
                     "confirm": { "title": "Add to shopping?", "text": "Add 1 piece of onions to your shopping list?", "label": "Add" } } ]
    }
  ],
  "actions": [ { "kind": "link", "label": "Open Pantry", "url": "/pantry/" } ],
  "requires_confirmation": false
}
```
* `basis` ∈ `data | calculated | estimate | general | ai` → shown as a badge so facts and estimates are never mixed.
* Card fields are all optional: `title`, `basis`, `tone: "warn"`, `highlight{label,value}`, `items[{name,status:have|missing,note}]`, `rows[{label,value}]`, `points[]`, `actions[]`.
  `type` containing `shopping` / `budget` / `pantry` only changes the accent colour.
* Action `kind`: `link` (`url` must start with `/` or `#`) or `api` (`endpoint` + `payload`, optional `confirm`).
  Anything that changes user data should carry `confirm`; the server must still re-validate and re-authorise.

Errors → non-2xx with
```json
{ "error": { "code": "data | llm | rate_limit" } }
```
`429` is treated as `rate_limit`. Never put provider/stack-trace text in the response.

## POST action endpoint
Request body = the action's `payload`. Respond `200 {"ok": true, "message": "Onions added to Shopping."}`
(optionally with `cards` / `actions` reflecting the new state) or a non-2xx / `{"ok": false}` — the UI then says
"I couldn't … Nothing was changed." so only report success when the database really changed.

## Conversations
* `GET …/<id>/` → `{ "id": 12, "title": "…", "messages": [ { "role": "user|assistant", "content": "…", "cards": [], "actions": [] } ] }`
* `PATCH …/<id>/` body `{ "title": "…" }` · `DELETE …/<id>/`
* Every query must be scoped to `request.user`.

## Rules the UI assumes (enforce them server-side)
1. Retrieve only the context the question needs, and only from enabled `context.sources`.
2. Tools take the authenticated user from the request — never an id supplied by the model.
3. Validate structured LLM output before acting; the LLM proposes, the backend authorises and executes.
4. Label estimates (`basis: "estimate"`) and say when price data is missing instead of guessing.
5. Rate-limit chat and expensive analyses; return `429` with `rate_limit`.