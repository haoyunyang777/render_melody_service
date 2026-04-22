import math
import os
import uuid
from copy import deepcopy
from datetime import datetime
from itertools import product
from typing import Dict, List, Optional, Tuple

from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)


def default_database_uri() -> str:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+psycopg://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return db_url
    base_dir = os.path.abspath(os.path.dirname(__file__))
    return "sqlite:///" + os.path.join(base_dir, "app.db")


app.config["SQLALCHEMY_DATABASE_URI"] = default_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
}

db = SQLAlchemy(app)

DEFAULT_BPM = 92
BEATS_PER_MEASURE = 4

NOTE_TO_TONE = {
    "C": "C4", "D": "D4", "E": "E4", "F": "F4", "G": "G4", "A": "A4", "B": "B4",
    "C_HIGH": "C5", "D_HIGH": "D5", "E_HIGH": "E5", "F_HIGH": "F5",
}
VALID_NOTES = set(NOTE_TO_TONE.keys())
ALIASES = {"C'": "C_HIGH", "D'": "D_HIGH", "E'": "E_HIGH", "F'": "F_HIGH"}

PC_TO_SEMITONE = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4,
    "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}
SEMITONE_TO_PC = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
    6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B",
}
DIATONIC_KEY_PCS = {"C", "D", "E", "F", "G", "A", "B"}

MELODY_MIDI = {
    "C": 60, "D": 62, "E": 64, "F": 65, "G": 67, "A": 69, "B": 71,
    "C_HIGH": 72, "D_HIGH": 74, "E_HIGH": 76, "F_HIGH": 77,
}

CHORD_LIBRARY = [
    {"key": "C", "label": "C", "root": "C", "quality": "maj", "intervals": [0, 4, 7], "family": "tonic", "roman": "I", "color": 0.15},
    {"key": "Cmaj7", "label": "Cmaj7", "root": "C", "quality": "maj7", "intervals": [0, 4, 7, 11], "family": "tonic", "roman": "Imaj7", "color": 0.35},
    {"key": "Dm", "label": "Dm", "root": "D", "quality": "min", "intervals": [0, 3, 7], "family": "predominant", "roman": "ii", "color": 0.15},
    {"key": "Dm7", "label": "Dm7", "root": "D", "quality": "min7", "intervals": [0, 3, 7, 10], "family": "predominant", "roman": "ii7", "color": 0.35},
    {"key": "Em", "label": "Em", "root": "E", "quality": "min", "intervals": [0, 3, 7], "family": "mediant", "roman": "iii", "color": 0.10},
    {"key": "F", "label": "F", "root": "F", "quality": "maj", "intervals": [0, 4, 7], "family": "predominant", "roman": "IV", "color": 0.15},
    {"key": "Fmaj7", "label": "Fmaj7", "root": "F", "quality": "maj7", "intervals": [0, 4, 7, 11], "family": "predominant", "roman": "IVmaj7", "color": 0.30},
    {"key": "G", "label": "G", "root": "G", "quality": "maj", "intervals": [0, 4, 7], "family": "dominant", "roman": "V", "color": 0.10},
    {"key": "G7", "label": "G7", "root": "G", "quality": "dom7", "intervals": [0, 4, 7, 10], "family": "dominant", "roman": "V7", "color": 0.40},
    {"key": "Am", "label": "Am", "root": "A", "quality": "min", "intervals": [0, 3, 7], "family": "tonic", "roman": "vi", "color": 0.15},
    {"key": "Am7", "label": "Am7", "root": "A", "quality": "min7", "intervals": [0, 3, 7, 10], "family": "tonic", "roman": "vi7", "color": 0.35},
    {"key": "Bdim", "label": "Bdim", "root": "B", "quality": "dim", "intervals": [0, 3, 6], "family": "dominant", "roman": "vii°", "color": 0.05},
]
CHORD_BY_KEY = {c["key"]: c for c in CHORD_LIBRARY}
STATE_KEYS = [c["key"] for c in CHORD_LIBRARY]
PACHELBEL_TARGET = ["C", "G", "Am", "Em", "F", "C", "F", "G"]

INITIAL_TRANSITION_PROBS = {
    "C": {"C": 0.08, "Cmaj7": 0.08, "Dm": 0.15, "Dm7": 0.15, "Em": 0.06, "F": 0.10, "Fmaj7": 0.08, "G": 0.12, "G7": 0.10, "Am": 0.04, "Am7": 0.03, "Bdim": 0.01},
    "Cmaj7": {"C": 0.10, "Cmaj7": 0.08, "Dm": 0.14, "Dm7": 0.14, "Em": 0.04, "F": 0.11, "Fmaj7": 0.10, "G": 0.11, "G7": 0.10, "Am": 0.04, "Am7": 0.03, "Bdim": 0.01},
    "Dm": {"C": 0.08, "Cmaj7": 0.05, "Dm": 0.05, "Dm7": 0.08, "Em": 0.02, "F": 0.10, "Fmaj7": 0.07, "G": 0.22, "G7": 0.22, "Am": 0.04, "Am7": 0.05, "Bdim": 0.02},
    "Dm7": {"C": 0.07, "Cmaj7": 0.05, "Dm": 0.05, "Dm7": 0.08, "Em": 0.02, "F": 0.08, "Fmaj7": 0.07, "G": 0.23, "G7": 0.24, "Am": 0.04, "Am7": 0.05, "Bdim": 0.02},
    "Em": {"C": 0.12, "Cmaj7": 0.08, "Dm": 0.05, "Dm7": 0.05, "Em": 0.05, "F": 0.08, "Fmaj7": 0.06, "G": 0.10, "G7": 0.10, "Am": 0.15, "Am7": 0.12, "Bdim": 0.04},
    "F": {"C": 0.14, "Cmaj7": 0.10, "Dm": 0.07, "Dm7": 0.08, "Em": 0.02, "F": 0.06, "Fmaj7": 0.09, "G": 0.17, "G7": 0.17, "Am": 0.05, "Am7": 0.04, "Bdim": 0.01},
    "Fmaj7": {"C": 0.13, "Cmaj7": 0.11, "Dm": 0.07, "Dm7": 0.08, "Em": 0.02, "F": 0.07, "Fmaj7": 0.08, "G": 0.16, "G7": 0.18, "Am": 0.05, "Am7": 0.04, "Bdim": 0.01},
    "G": {"C": 0.22, "Cmaj7": 0.17, "Dm": 0.03, "Dm7": 0.03, "Em": 0.02, "F": 0.03, "Fmaj7": 0.02, "G": 0.06, "G7": 0.15, "Am": 0.12, "Am7": 0.10, "Bdim": 0.05},
    "G7": {"C": 0.26, "Cmaj7": 0.22, "Dm": 0.02, "Dm7": 0.03, "Em": 0.02, "F": 0.02, "Fmaj7": 0.02, "G": 0.06, "G7": 0.11, "Am": 0.11, "Am7": 0.08, "Bdim": 0.05},
    "Am": {"C": 0.13, "Cmaj7": 0.08, "Dm": 0.12, "Dm7": 0.12, "Em": 0.08, "F": 0.09, "Fmaj7": 0.08, "G": 0.09, "G7": 0.08, "Am": 0.05, "Am7": 0.06, "Bdim": 0.02},
    "Am7": {"C": 0.12, "Cmaj7": 0.08, "Dm": 0.12, "Dm7": 0.13, "Em": 0.07, "F": 0.09, "Fmaj7": 0.08, "G": 0.09, "G7": 0.08, "Am": 0.05, "Am7": 0.06, "Bdim": 0.03},
    "Bdim": {"C": 0.30, "Cmaj7": 0.15, "Dm": 0.02, "Dm7": 0.03, "Em": 0.02, "F": 0.02, "Fmaj7": 0.02, "G": 0.09, "G7": 0.14, "Am": 0.11, "Am7": 0.08, "Bdim": 0.02},
}


class ModelState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    transition_logits = db.Column(db.JSON, nullable=False)
    learning_rate = db.Column(db.Float, nullable=False, default=0.06)
    exploration_margin = db.Column(db.Float, nullable=False, default=0.30)
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


def safe_log(x: float, eps: float = 1e-12) -> float:
    return math.log(max(x, eps))


def softmax_dict(logits: Dict[str, float]) -> Dict[str, float]:
    keys = list(logits.keys())
    values = [logits[k] for k in keys]
    mx = max(values)
    exps = [math.exp(v - mx) for v in values]
    total = sum(exps)
    return {k: exps[i] / total for i, k in enumerate(keys)}


def midi_to_tone_name(midi: int) -> str:
    semitone = midi % 12
    octave = midi // 12 - 1
    return f"{SEMITONE_TO_PC[semitone]}{octave}"


def normalize_note(note: str) -> str:
    note = str(note).strip().upper()
    return ALIASES.get(note, note)


def melody_pc(note: str) -> str:
    n = normalize_note(note)
    return n.replace("_HIGH", "")


def note_to_midi(note: str) -> int:
    return MELODY_MIDI[normalize_note(note)]


def chord_pitch_classes(chord_key: str) -> List[str]:
    chord = CHORD_BY_KEY[chord_key]
    root = PC_TO_SEMITONE[chord["root"]]
    return [SEMITONE_TO_PC[(root + interval) % 12] for interval in chord["intervals"]]


def build_default_transition_logits() -> Dict[str, Dict[str, float]]:
    logits: Dict[str, Dict[str, float]] = {}
    for src in STATE_KEYS:
        row: Dict[str, float] = {}
        for dst in STATE_KEYS:
            p = INITIAL_TRANSITION_PROBS.get(src, {}).get(dst, 1e-4)
            row[dst] = math.log(max(p, 1e-6))
        logits[src] = row
    return logits


def migrate_transition_logits(logits: Optional[Dict[str, Dict[str, float]]]) -> Tuple[Dict[str, Dict[str, float]], bool]:
    default_logits = build_default_transition_logits()
    if not isinstance(logits, dict):
        return deepcopy(default_logits), True

    changed = False
    migrated: Dict[str, Dict[str, float]] = {}

    for src in STATE_KEYS:
        raw_row = logits.get(src, {})
        if not isinstance(raw_row, dict):
            raw_row = {}
            changed = True

        new_row: Dict[str, float] = {}
        for dst in STATE_KEYS:
            if dst in raw_row:
                try:
                    new_row[dst] = float(raw_row[dst])
                except (TypeError, ValueError):
                    new_row[dst] = float(default_logits[src][dst])
                    changed = True
            else:
                new_row[dst] = float(default_logits[src][dst])
                changed = True

        extra_keys = set(raw_row.keys()) - set(STATE_KEYS)
        if extra_keys:
            changed = True

        migrated[src] = new_row

    extra_rows = set(logits.keys()) - set(STATE_KEYS)
    if extra_rows:
        changed = True

    return migrated, changed


def ensure_model_state() -> ModelState:
    model = db.session.get(ModelState, 1)
    if model is not None:
        migrated_logits, changed = migrate_transition_logits(model.transition_logits)
        if changed:
            model.transition_logits = migrated_logits
            model.updated_at = datetime.utcnow()
            db.session.commit()
        return model

    model = ModelState(id=1, version=1, transition_logits=build_default_transition_logits())
    db.session.add(model)
    db.session.commit()
    return model


def get_transition_probs(model: ModelState) -> Dict[str, Dict[str, float]]:
    return {src: softmax_dict(row) for src, row in model.transition_logits.items()}


def validate_flat_notes(notes: List[str]) -> List[str]:
    cleaned = []
    for note in notes:
        n = normalize_note(note)
        if n not in VALID_NOTES:
            raise ValueError(f"Invalid note: {note}")
        cleaned.append(n)
    return cleaned


def validate_measures(raw_measures: List[List[str]]) -> List[List[str]]:
    cleaned = []
    for measure in raw_measures:
        if not isinstance(measure, list):
            raise ValueError("Each measure must be a list of notes.")
        row = validate_flat_notes(measure)
        if len(row) > 4:
            raise ValueError("Each measure can contain at most 4 notes.")
        if row:
            cleaned.append(row)
    return cleaned


def flat_to_measures(notes: List[str]) -> List[List[str]]:
    return [notes[i:i + BEATS_PER_MEASURE] for i in range(0, len(notes), BEATS_PER_MEASURE)]


def chord_tone_role(chord_key: str, note_pc: str) -> Optional[str]:
    root = PC_TO_SEMITONE[CHORD_BY_KEY[chord_key]["root"]]
    diff = (PC_TO_SEMITONE[note_pc] - root) % 12
    return {0: "root", 3: "third", 4: "third", 6: "flat_five", 7: "fifth", 10: "seventh", 11: "seventh"}.get(diff)


def emission_detail(measure_notes: List[str], chord_key: str, index: int, total_measures: int) -> Tuple[float, str]:
    chord = CHORD_BY_KEY[chord_key]
    pcs = set(chord_pitch_classes(chord_key))
    note_pcs = [melody_pc(n) for n in measure_notes]
    midi_notes = [note_to_midi(n) for n in measure_notes]
    score = 0.0
    reasons: List[str] = []

    for beat_idx, note_pc in enumerate(note_pcs):
        role = chord_tone_role(chord_key, note_pc)
        beat_weight = 1.2 if beat_idx == 0 else 1.0
        if role == "root":
            score += 3.2 * beat_weight
            reasons.append("root fit")
        elif role == "third":
            score += 3.0 * beat_weight
            reasons.append("third fit")
        elif role == "fifth":
            score += 2.1 * beat_weight
            reasons.append("fifth fit")
        elif role == "seventh":
            score += 1.8 * beat_weight
            reasons.append("seventh color")
        else:
            score += -0.8 if note_pc in DIATONIC_KEY_PCS else -1.8
            reasons.append("non-chord passing tone" if note_pc in DIATONIC_KEY_PCS else "out of key")

    if note_pcs[0] in pcs:
        score += 1.6
        reasons.append("strong-beat anchor")
    if note_pcs[-1] in pcs:
        score += 1.2
        reasons.append("cadential anchor")

    last_index = total_measures - 1
    if index == 0 and chord["family"] == "tonic":
        score += 2.6
        reasons.append("opening tonic")
    if index == last_index:
        if chord["key"] in {"C", "Cmaj7", "Am", "Am7"}:
            score += 3.1
            reasons.append("final stability")
        elif chord["family"] == "dominant":
            score -= 2.2
            reasons.append("weak final dominant")
    elif index == last_index - 1 and chord["family"] == "dominant":
        score += 2.0
        reasons.append("pre-cadence dominant")

    avg_midi = sum(midi_notes) / len(midi_notes)
    root_mid = 48 + PC_TO_SEMITONE[chord["root"]]
    gap = avg_midi - root_mid
    if 12 <= gap <= 28:
        score += 0.9
        reasons.append("good register gap")
    elif gap < 7:
        score -= 1.5
        reasons.append("too close to bass")

    if chord["quality"] in {"maj7", "min7", "dom7"}:
        uses_seventh = any(chord_tone_role(chord_key, pc) == "seventh" for pc in note_pcs)
        score += (1.0 + chord["color"]) if uses_seventh else (0.3 * chord["color"])
        reasons.append("7th supported by melody" if uses_seventh else "light color")

    if len(set(note_pcs)) == 1 and chord["family"] in {"tonic", "dominant"}:
        score += 0.8
        reasons.append("stable under repeated melody")

    return score, ", ".join(dict.fromkeys(reasons))


def transition_bonus(prev_key: Optional[str], curr_key: str, index: int, total_measures: int) -> Tuple[float, List[str]]:
    if prev_key is None:
        return 0.0, []

    prev = CHORD_BY_KEY[prev_key]
    curr = CHORD_BY_KEY[curr_key]
    bonus = 0.0
    reasons: List[str] = []

    if prev_key == curr_key:
        bonus -= 0.25
        reasons.append("repeat penalty")

    good_moves = {
        ("Dm", "G"), ("Dm", "G7"), ("Dm7", "G"), ("Dm7", "G7"),
        ("G", "C"), ("G", "Cmaj7"), ("G7", "C"), ("G7", "Cmaj7"),
        ("F", "G"), ("Fmaj7", "G7"), ("C", "Am"), ("Cmaj7", "Am7"),
        ("Am", "Dm"), ("Am7", "Dm7"), ("Em", "Am"), ("Bdim", "C"), ("Bdim", "Cmaj7"),
    }
    if (prev_key, curr_key) in good_moves:
        bonus += 0.9
        reasons.append("functional move")
    if prev["family"] == "predominant" and curr["family"] == "dominant":
        bonus += 0.7
        reasons.append("PD→D")
    if prev["family"] == "dominant" and curr["family"] == "tonic":
        bonus += 1.0
        reasons.append("D→T")
    if prev["family"] == "tonic" and curr["family"] == "predominant":
        bonus += 0.4
        reasons.append("T→PD")
    if index == total_measures - 1 and curr["family"] == "dominant":
        bonus -= 1.1
        reasons.append("avoid ending on dominant")
    if index == total_measures - 2 and curr["family"] == "dominant":
        bonus += 0.8
        reasons.append("penultimate dominant")
    if index == 0 and curr["family"] != "tonic":
        bonus -= 0.8
        reasons.append("non-tonic opening")
    return bonus, reasons


def pachelbel_similarity(state_keys: List[str]) -> float:
    usable = min(len(state_keys), len(PACHELBEL_TARGET))
    score = 0.0
    for idx in range(usable):
        got = state_keys[idx]
        want = PACHELBEL_TARGET[idx]
        if got == want:
            score += 1.0
        elif CHORD_BY_KEY[got]["root"] == CHORD_BY_KEY[want]["root"]:
            score += 0.6
        elif CHORD_BY_KEY[got]["family"] == CHORD_BY_KEY[want]["family"]:
            score += 0.25

    if usable >= 4 and state_keys[:4] == PACHELBEL_TARGET[:4]:
        score += 1.2
    if usable >= 8 and state_keys[:8] == PACHELBEL_TARGET:
        score += 2.0
    return score


def assign_display_scores(variation_a: Dict[str, object], variation_b: Dict[str, object]) -> None:
    raw_a = float(variation_a["raw_score"])
    raw_b = float(variation_b["raw_score"])

    floor = min(raw_a, raw_b)
    display_a = raw_a - floor + 1.0
    display_b = raw_b - floor + 1.0

    canon_a = pachelbel_similarity(variation_a["state_keys"])
    canon_b = pachelbel_similarity(variation_b["state_keys"])

    if canon_a > canon_b:
        display_a += min(0.15 + 0.05 * (canon_a - canon_b), 0.75)
    elif canon_b > canon_a:
        display_b += min(0.15 + 0.05 * (canon_b - canon_a), 0.75)

    if abs(display_a - display_b) < 0.05:
        display_a += 0.08

    variation_a["score"] = round(display_a, 3)
    variation_b["score"] = round(display_b, 3)


def candidate_upper_voicings(chord_key: str) -> List[List[int]]:
    pcs = chord_pitch_classes(chord_key)
    if CHORD_BY_KEY[chord_key]["quality"] in {"maj7", "min7", "dom7"} and len(pcs) >= 4:
        essential_sets = [[pcs[1], pcs[3], pcs[0]], [pcs[1], pcs[3], pcs[2]], [pcs[3], pcs[0], pcs[1]]]
    else:
        essential_sets = [[pcs[0], pcs[1], pcs[2]], [pcs[1], pcs[2], pcs[0]], [pcs[2], pcs[0], pcs[1]]]

    candidates: List[List[int]] = []
    for pcs_set in essential_sets:
        for octaves in product(range(3, 5), range(3, 6), range(3, 6)):
            mids = sorted([(octave + 1) * 12 + PC_TO_SEMITONE[pc] for pc, octave in zip(pcs_set, octaves)])
            if len(set(mids)) < 3 or mids[0] < 50 or mids[-1] > 72 or mids[-1] - mids[0] > 16:
                continue
            candidates.append(mids)

    uniq = []
    seen = set()
    for cand in sorted(candidates):
        sig = tuple(cand)
        if sig not in seen:
            uniq.append(cand)
            seen.add(sig)
    return uniq or [[55, 60, 64]]


def choose_voicings_for_path(state_keys: List[str], measures: List[List[str]]) -> List[Dict[str, object]]:
    chosen: List[Dict[str, object]] = []
    prev_upper: Optional[List[int]] = None

    for chord_key, measure_notes in zip(state_keys, measures):
        melody_floor = min(note_to_midi(n) for n in measure_notes)
        best_upper = None
        best_penalty = float("inf")

        for cand in candidate_upper_voicings(chord_key):
            penalty = 0.0
            if cand[-1] >= melody_floor - 1:
                penalty += (cand[-1] - (melody_floor - 2)) * 1.8
            if prev_upper is not None:
                penalty += sum(abs(a - b) for a, b in zip(cand, prev_upper)) * 0.35
                if abs(cand[-1] - prev_upper[-1]) > 7:
                    penalty += 2.0
            penalty += abs(sum(cand) / len(cand) - 61) * 0.08
            if penalty < best_penalty:
                best_penalty = penalty
                best_upper = cand

        pcs = chord_pitch_classes(chord_key)
        root_pc = CHORD_BY_KEY[chord_key]["root"]
        bass_midi = 36 + PC_TO_SEMITONE[root_pc]
        fifth_pc = pcs[2 if len(pcs) >= 3 else 0]
        bass_fifth_midi = 36 + PC_TO_SEMITONE[fifth_pc]
        chosen.append({
            "bass_note": midi_to_tone_name(bass_midi),
            "bass_fifth_note": midi_to_tone_name(bass_fifth_midi),
            "upper_notes": [midi_to_tone_name(m) for m in best_upper],
            "arpeggio_notes": [midi_to_tone_name(m) for m in best_upper],
        })
        prev_upper = best_upper

    return chosen


def k_best_paths(measures: List[List[str]], transition_probs: Dict[str, Dict[str, float]], k: int = 2):
    total = len(measures)
    beam = []
    for chord_key in STATE_KEYS:
        emit, reason = emission_detail(measures[0], chord_key, 0, total)
        beam.append({
            "score": emit,
            "state_keys": [chord_key],
            "details": [{
                "state_key": chord_key,
                "emission_score": round(emit, 4),
                "reason": reason,
                "transition_prob": None,
                "transition_bonus": None,
                "total_score": round(emit, 4),
            }],
        })

    beam = sorted(beam, key=lambda x: x["score"], reverse=True)[:max(k * 5, 18)]

    for idx in range(1, total):
        expanded = []
        for cand in beam:
            prev_key = cand["state_keys"][-1]
            for chord_key in STATE_KEYS:
                emit, emit_reason = emission_detail(measures[idx], chord_key, idx, total)
                trans = transition_probs.get(prev_key, {}).get(chord_key, 1e-4)
                extra_bonus, extra_reasons = transition_bonus(prev_key, chord_key, idx, total)
                total_score = cand["score"] + safe_log(trans) + emit + extra_bonus
                reason = emit_reason if not extra_reasons else f"{emit_reason} | {'; '.join(extra_reasons)}"
                expanded.append({
                    "score": total_score,
                    "state_keys": cand["state_keys"] + [chord_key],
                    "details": cand["details"] + [{
                        "state_key": chord_key,
                        "emission_score": round(emit, 4),
                        "reason": reason,
                        "transition_prob": round(trans, 4),
                        "transition_bonus": round(extra_bonus, 4),
                        "total_score": round(total_score, 4),
                    }],
                })

        uniq = {}
        for cand in sorted(expanded, key=lambda x: x["score"], reverse=True):
            sig = tuple(cand["state_keys"])
            if sig not in uniq:
                uniq[sig] = cand
            if len(uniq) >= max(k * 10, 40):
                break
        beam = list(uniq.values())

    return sorted(beam, key=lambda x: x["score"], reverse=True)[:k]


def diversify_second_path(best_paths, transition_probs, measures):
    if len(best_paths) >= 2:
        return best_paths[:2]
    if not best_paths:
        return []

    winner = best_paths[0]
    perturbed = deepcopy(transition_probs)
    for prev_key, curr_key in zip(winner["state_keys"][:-1], winner["state_keys"][1:]):
        perturbed[prev_key][curr_key] = max(1e-6, perturbed[prev_key][curr_key] * 0.62)
        total = sum(perturbed[prev_key].values())
        perturbed[prev_key] = {k: v / total for k, v in perturbed[prev_key].items()}

    retry = k_best_paths(measures, perturbed, k=3)
    merged = best_paths + retry
    uniq = []
    seen = set()
    for cand in merged:
        sig = tuple(cand["state_keys"])
        if sig not in seen:
            uniq.append(cand)
            seen.add(sig)
        if len(uniq) >= 2:
            break
    return uniq


def build_variation_payload(path_item, name: str, letter: str, measures: List[List[str]]):
    voicings = choose_voicings_for_path(path_item["state_keys"], measures)
    chords = []
    for detail, voicing in zip(path_item["details"], voicings):
        chord = CHORD_BY_KEY[detail["state_key"]]
        chords.append({
            "key": chord["key"],
            "label": chord["label"],
            "roman": chord["roman"],
            "family": chord["family"],
            "root": chord["root"],
            "quality": chord["quality"],
            "emission_score": detail["emission_score"],
            "transition_prob": detail["transition_prob"],
            "transition_bonus": detail["transition_bonus"],
            "reason": detail["reason"],
            "total_score": detail["total_score"],
            **voicing,
        })
    return {
        "id": letter,
        "name": name,
        "raw_score": round(path_item["score"], 4),
        "score": round(path_item["score"], 4),
        "state_keys": path_item["state_keys"],
        "chords": chords,
    }


def generate_two_variations_from_measures(measures: List[List[str]]):
    model = ensure_model_state()
    transition_probs = get_transition_probs(model)
    paths = diversify_second_path(k_best_paths(measures, transition_probs, k=2), transition_probs, measures)
    if len(paths) == 1:
        paths = [paths[0], paths[0]]

    if len(paths) >= 2 and pachelbel_similarity(paths[1]["state_keys"]) > pachelbel_similarity(paths[0]["state_keys"]):
        paths[0], paths[1] = paths[1], paths[0]

    variation_a = build_variation_payload(paths[0], "Variation A", "A", measures)
    variation_b = build_variation_payload(paths[1], "Variation B", "B", measures)
    assign_display_scores(variation_a, variation_b)

    return {
        "model_version": model.version,
        "bpm": DEFAULT_BPM,
        "measures": measures,
        "variation_a": variation_a,
        "variation_b": variation_b,
    }


def update_transition_logits_from_preference(model: ModelState, winner_keys: List[str], loser_keys: List[str]):
    logits, _ = migrate_transition_logits(deepcopy(model.transition_logits))
    lr = model.learning_rate

    for prev_key, curr_key in zip(winner_keys[:-1], winner_keys[1:]):
        if prev_key in logits and curr_key in logits[prev_key]:
            logits[prev_key][curr_key] = float(logits[prev_key][curr_key]) + lr
    for prev_key, curr_key in zip(loser_keys[:-1], loser_keys[1:]):
        if prev_key in logits and curr_key in logits[prev_key]:
            logits[prev_key][curr_key] = float(logits[prev_key][curr_key]) - lr * 0.7

    for src in STATE_KEYS:
        row = logits[src]
        avg = sum(float(v) for v in row.values()) / len(row)
        for dst in STATE_KEYS:
            row[dst] = float(row[dst]) - avg * 0.03

    model.transition_logits = logits
    model.version += 1
    model.updated_at = datetime.utcnow()


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    model = ensure_model_state()
    db.session.execute(text("SELECT 1"))
    return jsonify({"ok": True, "model_version": model.version, "database": app.config["SQLALCHEMY_DATABASE_URI"].split(":", 1)[0]})


@app.post("/api/generate")
def api_generate():
    payload = request.get_json(force=True)
    raw_measures = payload.get("measures")
    raw_notes = payload.get("notes", [])

    try:
        if raw_measures:
            measures = validate_measures(raw_measures)
            cleaned = [n for m in measures for n in m]
        else:
            cleaned = validate_flat_notes(raw_notes)
            measures = flat_to_measures(cleaned)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if len(cleaned) < 4:
        return jsonify({"error": "Need at least 4 notes."}), 400

    data = generate_two_variations_from_measures(measures)
    comparison_id = str(uuid.uuid4())
    comparison = Comparison(
        id=comparison_id,
        melody={"notes": cleaned, "measures": measures},
        variation_a=data["variation_a"],
        variation_b=data["variation_b"],
        model_version=data["model_version"],
    )
    db.session.add(comparison)
    db.session.commit()
    return jsonify({"comparison_id": comparison_id, **data})


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
    winner_keys = comparison.variation_a["state_keys"] if winner == "A" else comparison.variation_b["state_keys"]
    loser_keys = comparison.variation_b["state_keys"] if winner == "A" else comparison.variation_a["state_keys"]
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
    return jsonify({
        "model_version": model.version,
        "learning_rate": model.learning_rate,
        "transition_probs": get_transition_probs(model),
    })


with app.app_context():
    db.create_all()
    ensure_model_state()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=True)
