# Melody Chord Preference Trainer

A small Flask app for Render deployment:
- browser piano keyboard GUI for melody input
- generates **two HMM chord variations**
- browser playback for both versions
- user votes A/B
- vote updates the HMM transition weights online

## Local run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: http://127.0.0.1:10000

## Render deploy

This repo includes `render.yaml` for Blueprint deployment.

1. Push the project to GitHub.
2. In Render, choose **New Blueprint Instance**.
3. Select the repo.
4. Render will create:
   - one Python web service
   - one Postgres database

## API

### POST `/api/generate`

Request:
```json
{
  "notes": ["C", "D", "E", "F", "G", "A", "B", "C_HIGH"]
}
```

### POST `/api/vote`

Request:
```json
{
  "comparison_id": "uuid",
  "winner": "A"
}
```

## Important note

The online update is a lightweight preference-learning rule over HMM transition logits. It is reinforcement-like and useful for collecting human preference data, but it is not a full large-scale RLHF pipeline.
