# Coach Potato Integration

Coach Potato should treat `local-ragbot` as a standalone local knowledge service.

## Boundary

Coach Potato owns the product UX, training log collection, voice lines, and user
personality. `local-ragbot` owns retrieval over local indexed training data.

The first real dataset is:

```text
coach-potato
```

## Flow

1. Coach Potato collects training data.
2. Coach Potato writes or exports that data into a local dataset folder.
3. `local-ragbot` indexes that folder as `coach-potato`.
4. Coach Potato asks questions with `dataset=coach-potato`.
5. `local-ragbot` answers only from indexed training context.
6. If the question is outside the dataset, Coach Potato forwards/escalates it.

## API

```http
POST http://127.0.0.1:8088/ask
Content-Type: application/json

{
  "dataset": "coach-potato",
  "question": "What improved in my training recently?"
}
```

Expected refusal pattern:

```json
{
  "answer": "Dazu finde ich in den lokalen Daten nichts.",
  "sources": [],
  "mode": "refusal",
  "dataset": "coach-potato"
}
```

Coach Potato can use that `mode=refusal` result to decide whether to:

- ask the user for more local data
- forward to a stronger external model
- route to a human coach

## Voice Line Strategy

Keep two layers separate:

- Generic voice lines: motivational filler, UI confirmations, small talk
- RAG answers: grounded responses with local training sources

Coach Potato can speak in its own style, but it should not invent training facts.
The source-backed answer should remain the truth layer.

