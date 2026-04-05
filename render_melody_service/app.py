import json
import math
import os
import random
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Tuple

from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# ======================================================
# App / DB setup
# ======================================================
app = Flask(__name__)

def default_database_uri() -> str:
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            return db_url.replace("postgres://", "postgresql://", 1)
        return db_url
    base_dir = os.path.abspath(os.path.dirname(__file__))
    return "sqlite:///" + os.path.join(base_dir, "app.db")

app.config["SQLALCHEMY_DATABASE_URI"] = default_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False

db = SQLAlchemy(app)

# ======================================================
# Music model config
# ======================================================
DEFAULT_BPM = 100
BEATS_PER_MEASURE = 4
MELODY_OCTAVE_DEFAULT = 4
MELODY_OCTAVE_HIGH = 5

FREQ_MAP = {
    "C": 261.63, "C#": 277.18,
    "D": 293.66, "D#": 311.13,
    "E": 329.63,
    "F": 349.23, "F#": 369.99,
    "G": 392.00, "G#": 415.30,
    "A": 440.00, "A#": 466.16,
    "B": 493.88,
    "C_HIGH": 523.25, "D_HIGH": 587.33,
    "E_HIGH": 659.25, "F_HIGH": 698.46,
}

CHORD_STRUCTURES = {
    "Major": [0, 4, 7],
    "Minor": [0, 3, 7],
}

STATES: List[Tuple[str, str]] = [
    ("C", "Major"),
    ("E", "Minor"),
    ("F", "Major"),
    ("G", "Major"),
    ("A", "Minor"),
]
STATE_KEYS = [s[0] + ("m" if s[1] == "Minor" else "") for s in STATES]
STATE_MAP = {k: s for k, s in zip(STATE_KEYS, STATES)}

INITIAL_TRANSITION_PROBS = {
    "C":  {"C": 0.10, "F": 0.30, "G": 0.40, "Em": 0.10, "Am": 0.10},
    "F":  {"C": 0.40, "G": 0.40, "Em": 0.10, "Am": 0.10},
    "G":  {"C": 0.20, "F": 0.05, "Am": 0.70, "Em": 0.05},
    "Em": {"Am": 0.20, "F": 0.60, "G": 0.10, "C": 0.10},
    "Am": {"F": 0.10, "G": 0.20, "Em": 0.60, "C": 0.10},
}

CONSONANCE_RATIOS = {1.00: 5.0, 1.50: 4.0, 1.33: 3.5, 1.25: 3.0, 1.20: 2.5}
RATIO_NAMES = {1.00: "octave", 1.50: "fifth", 1.33: "fourth", 1.25: "major third", 1.20: "minor third"}

PARAMS = {
    "cross_penalty": 20.0,
    "close_penalty": 2.0,
    "close_ratio_threshold": 1.05,
    "ratio_tolerance": 0.03,
    "style_hit_bonus": 4.0,
    "style_miss_penalty": 0.3,
}

STYLE_TARGETS = {
    "C": [("C", "Major"), ("A", "Minor")],
    "D": [("G", "Major")],
    "E": [("C", "Major"), ("E", "Minor"), ("A", "Minor")],
    "F": [("F", "Major")],
    "G": [("C", "Major"), ("G", "Major")],
    "A": [("A", "Minor"), ("F", "Major")],
    "B": [("G", "Major"), ("E", "Minor")],
}

# ======================================================
# Database models
# ======================================================
class ModelState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    transition_logits = db.Column(db.JSON, nullable=False)
    learning_rate = db.Column(db.Float, nullable=False, default=0.08)
    exploration_margin = db.Column(db.Float, nullable=False, default=0.35)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class Comparison(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    melody = db.Column(db.JSON, nullable=False)
    variation_a = db.Column(db.JSON, nullable=False)
    variation_b = db.Column(db.JSON, nullable=False)
    model_version = db.Column(db.Integer, nullable=False)
    voted = db.Column(db.Boolean, nullable=False, default=False)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comparison_id = db.Column(db.String(36), nullable=False)
    winner = db.Column(db.String(1), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    model_version_before = db.Column(db.Integer, nullable=False)
    model_version_after = db.Column(db.Integer, nullable=False)

# ======================================================
# Init helpers
# ======================================================
def state_to_key(state: Tuple[str, str]) -> str:
    return state[0] + ("m" if state[1] == "Minor" else "")


def key_to_state(key: str) -> Tuple[str, str]:
    return STATE_MAP[key]


def chord_label(state: Tuple[str, str]) -> str:
    return state[0] + ("m" if state[1] == "Minor" else "")


def safe_log(x: float, eps: float = 1e-12) -> float:
    return math.log(max(x, eps))


def softmax_dict(logits: Dict[str, float]) -> Dict[str, float]:
    keys = list(logits.keys())
    values = [logits[k] for k in keys]
    mx = max(values)
    exps = [math.exp(v - mx) for v in values]
    total = sum(exps)
    return {k: exps[i] / total for i, k in enumerate(keys)}


def ensure_model_state() -> ModelState:
    model = db.session.get(ModelState, 1)
    if model is not None:
        return model

    transition_logits = {}
    for src in STATE_KEYS:
        row = {}
        for dst in STATE_KEYS:
            p = INITIAL_TRANSITION_PROBS.get(src, {}).get(dst, 1e-4)
            row[dst] = math.log(max(p, 1e-6))
        transition_logits[src] = row

    model = ModelState(id=1, version=1, transition_logits=transition_logits)
    db.session.add(model)
    db.session.commit()
    return model


def get_transition_probs(model: ModelState) -> Dict[str, Dict[str, float]]:
    return {src: softmax_dict(row) for src, row in model.transition_logits.items()}

# ======================================================
# Melody helpers
# ======================================================
VALID_NOTES = {"C", "D", "E", "F", "G", "A", "B", "C_HIGH", "D_HIGH", "E_HIGH", "F_HIGH"}
ALIASES = {"C'": "C_HIGH", "D'": "D_HIGH", "E'": "E_HIGH", "F'": "F_HIGH"}


def normalize_note(note: str) -> str:
    note = str(note).strip().upper()
    return ALIASES.get(note, note)


def validate_flat_notes(notes: List[str]) -> List[str]:
    cleaned = []
    for note in notes:
        n = normalize_note(note)
        if n not in VALID_NOTES:
            raise ValueError(f"Invalid note: {note}")
        cleaned.append(n)
    return cleaned


def flat_to_measures(notes: List[str], beats_per_measure: int = BEATS_PER_MEASURE) -> List[List[str]]:
    return [notes[i:i + beats_per_measure] for i in range(0, len(notes), beats_per_measure)]

# ======================================================
# Emission scoring
# ======================================================

def get_freq(note: str) -> float:
    return FREQ_MAP[note]


def note_name_from_freq(freq: float) -> str:
    for note, f in FREQ_MAP.items():
        if abs(freq - f) < 1.0 or abs(freq - f * 2) < 1.0:
            return note.replace("_HIGH", "")
    return ""


def calculate_consonance_detail(melody_notes: List[float], chord_root_name: str, chord_type: str):
    cross_penalty = float(PARAMS["cross_penalty"])
    close_penalty = float(PARAMS["close_penalty"])
    close_ratio_threshold = float(PARAMS["close_ratio_threshold"])
    ratio_tolerance = float(PARAMS["ratio_tolerance"])
    style_hit_bonus = float(PARAMS["style_hit_bonus"])
    style_miss_penalty = float(PARAMS["style_miss_penalty"])

    base_divisor = 2.0 if chord_root_name == "C" and chord_type == "Major" else 4.0
    root_freq = FREQ_MAP[chord_root_name] / base_divisor
    chord_freqs = [root_freq * (2 ** (st / 12.0)) for st in CHORD_STRUCTURES[chord_type]]

    cumulative_score = 0.0
    reasons = []

    for mel_freq in melody_notes:
        note_score = 0.0
        for cf in chord_freqs:
            if cf >= mel_freq:
                note_score -= cross_penalty
                reasons.append("voice crossing")
                continue

            if mel_freq / cf < close_ratio_threshold:
                note_score -= close_penalty
                reasons.append("too close")

            ratio = max(mel_freq, cf) / min(mel_freq, cf)
            while ratio > 2.01:
                ratio /= 2.0

            for ideal, weight in CONSONANCE_RATIOS.items():
                if abs(ratio - ideal) < ratio_tolerance:
                    note_score += weight
                    reasons.append(RATIO_NAMES[ideal])
                    break
        cumulative_score += note_score

    current_names = [note_name_from_freq(freq) for freq in melody_notes]
    hit = False
    for note_name in current_names:
        if not note_name:
            continue
        targets = STYLE_TARGETS.get(note_name, [])
        if (chord_root_name, chord_type) in targets:
            cumulative_score += style_hit_bonus
            reasons.insert(0, f"style hit: {note_name}")
            hit = True
            break

    if not hit and any(n in STYLE_TARGETS for n in current_names):
        cumulative_score -= style_miss_penalty
        reasons.append("style miss")

    avg_score = cumulative_score / max(1, len(melody_notes))
    final_score = max(0.01, avg_score)

    unique_reasons = []
    seen = set()
    for r in reasons:
        if r not in seen:
            unique_reasons.append(r)
            seen.add(r)
    return final_score, ", ".join(unique_reasons) if unique_reasons else "consonant"


def get_emission_data(note_list: List[str], state: Tuple[str, str]):
    chord_root, chord_type = state
    freqs = [get_freq(n) for n in note_list]
    score, reason = calculate_consonance_detail(freqs, chord_root, chord_type)
    return safe_log(score), score, reason

# ======================================================
# K-best Viterbi for two chord variations
# ======================================================

def transition_prob(transition_probs: Dict[str, Dict[str, float]], prev_state: Tuple[str, str], curr_state: Tuple[str, str]) -> float:
    return transition_probs.get(state_to_key(prev_state), {}).get(state_to_key(curr_state), 1e-4)


def k_best_paths(measures: List[List[str]], transition_probs: Dict[str, Dict[str, float]], k: int = 2):
    first_candidates = []
    start_log = safe_log(1.0 / len(STATES))
    for state in STATES:
        emit_log, emit_score, emit_reason = get_emission_data(measures[0], state)
        first_candidates.append({
            "score": start_log + emit_log,
            "states": [state],
            "details": [{
                "state": state,
                "emission_score": round(emit_score, 4),
                "reason": emit_reason,
                "transition_prob": None,
                "total_log_prob": start_log + emit_log,
            }],
        })

    beam = sorted(first_candidates, key=lambda x: x["score"], reverse=True)[:max(k * 3, 6)]

    for t in range(1, len(measures)):
        expanded = []
        for cand in beam:
            prev_state = cand["states"][-1]
            for state in STATES:
                emit_log, emit_score, emit_reason = get_emission_data(measures[t], state)
                trans = transition_prob(transition_probs, prev_state, state)
                total = cand["score"] + safe_log(trans) + emit_log
                details = cand["details"] + [{
                    "state": state,
                    "emission_score": round(emit_score, 4),
                    "reason": emit_reason,
                    "transition_prob": round(trans, 4),
                    "total_log_prob": total,
                }]
                expanded.append({
                    "score": total,
                    "states": cand["states"] + [state],
                    "details": details,
                })

        # unique by exact state sequence
        uniq = {}
        for cand in sorted(expanded, key=lambda x: x["score"], reverse=True):
            sig = tuple(state_to_key(s) for s in cand["states"])
            if sig not in uniq:
                uniq[sig] = cand
            if len(uniq) >= max(k * 8, 16):
                break
        beam = list(uniq.values())

    best = sorted(beam, key=lambda x: x["score"], reverse=True)
    return best[:k]


def diversify_second_path(best_paths, transition_probs, measures):
    if len(best_paths) >= 2:
        return best_paths[:2]

    # fallback: penalize winner path transitions lightly, rerun
    if not best_paths:
        return []
    best = best_paths[0]
    perturbed = deepcopy(transition_probs)
    states = best["states"]
    for prev, curr in zip(states[:-1], states[1:]):
        prev_k = state_to_key(prev)
        curr_k = state_to_key(curr)
        perturbed[prev_k][curr_k] = max(1e-6, perturbed[prev_k][curr_k] * 0.6)
        # renormalize row
        row_total = sum(perturbed[prev_k].values())
        perturbed[prev_k] = {k: v / row_total for k, v in perturbed[prev_k].items()}

    retry = k_best_paths(measures, perturbed, k=2)
    merged = best_paths + retry
    uniq = []
    seen = set()
    for cand in merged:
        sig = tuple(state_to_key(s) for s in cand["states"])
        if sig not in seen:
            uniq.append(cand)
            seen.add(sig)
        if len(uniq) == 2:
            break
    return uniq


def build_variation_payload(path_item, name: str, letter: str):
    chords = []
    for detail in path_item["details"]:
        s = detail["state"]
        chords.append({
            "root": s[0],
            "type": s[1],
            "label": chord_label(s),
            "emission_score": detail["emission_score"],
            "reason": detail["reason"],
            "transition_prob": detail["transition_prob"],
            "total_log_prob": round(detail["total_log_prob"], 4),
        })
    return {
        "id": letter,
        "name": name,
        "score": round(path_item["score"], 4),
        "chords": chords,
        "state_keys": [state_to_key(s) for s in path_item["states"]],
    }


def generate_two_variations(flat_notes: List[str]):
    measures = flat_to_measures(flat_notes)
    model = ensure_model_state()
    transition_probs = get_transition_probs(model)
    paths = diversify_second_path(k_best_paths(measures, transition_probs, k=2), transition_probs, measures)

    if not paths:
        raise RuntimeError("Unable to generate chord variations.")
    if len(paths) == 1:
        paths = [paths[0], paths[0]]

    variation_a = build_variation_payload(paths[0], "Variation A", "A")
    variation_b = build_variation_payload(paths[1], "Variation B", "B")

    return {
        "model_version": model.version,
        "bpm": DEFAULT_BPM,
        "measures": measures,
        "variation_a": variation_a,
        "variation_b": variation_b,
    }

# ======================================================
# Preference-learning update
# ======================================================

def update_transition_logits_from_preference(model: ModelState, winner_keys: List[str], loser_keys: List[str]):
    logits = deepcopy(model.transition_logits)
    lr = model.learning_rate

    transition_delta = defaultdict(lambda: defaultdict(float))

    for prev, curr in zip(winner_keys[:-1], winner_keys[1:]):
        transition_delta[prev][curr] += 1.0
    for prev, curr in zip(loser_keys[:-1], loser_keys[1:]):
        transition_delta[prev][curr] -= 1.0

    # Apply preference gradient-ish update and mild row centering.
    for src in STATE_KEYS:
        row = logits[src]
        touched = False
        for dst in STATE_KEYS:
            delta = transition_delta[src][dst]
            if delta != 0:
                row[dst] = float(row[dst]) + lr * delta
                touched = True
        if touched:
            avg = sum(row.values()) / len(row)
            for dst in STATE_KEYS:
                row[dst] = float(row[dst]) - 0.05 * avg

    model.transition_logits = logits
    model.version += 1

# ======================================================
# Routes
# ======================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/health")
def health():
    model = ensure_model_state()
    db.session.execute(text("SELECT 1"))
    return jsonify({
        "ok": True,
        "model_version": model.version,
        "database": app.config["SQLALCHEMY_DATABASE_URI"].split(":", 1)[0],
    })

@app.post("/api/generate")
def api_generate():
    payload = request.get_json(force=True)
    notes = payload.get("notes", [])
    if not notes:
        return jsonify({"error": "Provide at least 4 notes."}), 400

    try:
        cleaned = validate_flat_notes(notes)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if len(cleaned) < 4:
        return jsonify({"error": "Need at least 4 notes."}), 400

    data = generate_two_variations(cleaned)
    comparison_id = str(uuid.uuid4())
    comparison = Comparison(
        id=comparison_id,
        melody={"notes": cleaned, "measures": data["measures"]},
        variation_a=data["variation_a"],
        variation_b=data["variation_b"],
        model_version=data["model_version"],
    )
    db.session.add(comparison)
    db.session.commit()

    response = {
        "comparison_id": comparison_id,
        **data,
    }
    return jsonify(response)

@app.post("/api/vote")
def api_vote():
    payload = request.get_json(force=True)
    comparison_id = payload.get("comparison_id")
    winner = str(payload.get("winner", "")).upper()
    if winner not in {"A", "B"}:
        return jsonify({"error": "winner must be A or B"}), 400

    comparison = db.session.get(Comparison, comparison_id)
    if comparison is None:
        return jsonify({"error": "comparison not found"}), 404
    if comparison.voted:
        return jsonify({"error": "vote already recorded for this comparison"}), 409

    model = ensure_model_state()
    before_version = model.version

    if winner == "A":
        winner_keys = comparison.variation_a["state_keys"]
        loser_keys = comparison.variation_b["state_keys"]
    else:
        winner_keys = comparison.variation_b["state_keys"]
        loser_keys = comparison.variation_a["state_keys"]

    update_transition_logits_from_preference(model, winner_keys, loser_keys)
    comparison.voted = True

    vote = Vote(
        comparison_id=comparison.id,
        winner=winner,
        model_version_before=before_version,
        model_version_after=model.version,
    )
    db.session.add(vote)
    db.session.commit()

    return jsonify({
        "ok": True,
        "message": f"Vote {winner} saved.",
        "model_version_before": before_version,
        "model_version_after": model.version,
    })

@app.get("/api/model")
def api_model():
    model = ensure_model_state()
    transition_probs = get_transition_probs(model)
    return jsonify({
        "model_version": model.version,
        "learning_rate": model.learning_rate,
        "transition_probs": transition_probs,
    })

# ======================================================
# Bootstrap
# ======================================================
with app.app_context():
    db.create_all()
    ensure_model_state()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=True)
