import math
import os
import uuid
from copy import deepcopy
from datetime import datetime
from itertools import product
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
from xml.dom import minidom

from flask import Flask, jsonify, render_template, request, Response
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
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)

DEFAULT_BPM = 92
SINGLE_NOTE_BPM = 120
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

FREQ_MAP = {
    "C": 261.63, "C#": 277.18, "DB": 277.18,
    "D": 293.66, "D#": 311.13, "EB": 311.13,
    "E": 329.63,
    "F": 349.23, "F#": 369.99, "GB": 369.99,
    "G": 392.00, "G#": 415.30, "AB": 415.30,
    "A": 440.00, "A#": 466.16, "BB": 466.16,
    "B": 493.88,
}
FREQ_MAP_EXT = FREQ_MAP.copy()
FREQ_MAP_EXT.update({"C_HIGH": 523.25, "D_HIGH": 587.33, "E_HIGH": 659.25, "F_HIGH": 698.46})
CONSONANCE_RATIOS = {1.00: 5.0, 1.50: 4.0, 1.33: 3.5, 1.25: 3.0, 1.20: 2.5}
CHORD_STRUCTURES_SIMPLE = {"Major": [0, 4, 7], "Minor": [0, 3, 7]}
SINGLE_NOTE_STATES = [("C", "Major"), ("E", "Minor"), ("F", "Major"), ("G", "Major"), ("A", "Minor")]
SINGLE_NOTE_STATE_KEYS = ["C", "Em", "F", "G", "Am"]
SINGLE_NOTE_STATE_MAP = dict(zip(SINGLE_NOTE_STATE_KEYS, SINGLE_NOTE_STATES))
SINGLE_NOTE_TRANSITION_PROBS = {
    "C": {"C": 0.1, "F": 0.3, "G": 0.4, "Em": 0.1, "Am": 0.1},
    "F": {"C": 0.4, "G": 0.4, "Em": 0.1, "Am": 0.1},
    "G": {"C": 0.2, "F": 0.05, "Am": 0.7, "Em": 0.05},
    "Em": {"Am": 0.2, "F": 0.6, "G": 0.1, "C": 0.1},
    "Am": {"F": 0.1, "G": 0.2, "Em": 0.6, "C": 0.1},
}
STYLE_TARGETS_KPOP = {
    "C": [("C", "Major"), ("A", "Minor")],
    "D": [("G", "Major")],
    "E": [("C", "Major"), ("A", "Minor")],
    "F": [("F", "Major")],
    "G": [("C", "Major"), ("G", "Major")],
    "A": [("A", "Minor"), ("F", "Major")],
    "B": [("G", "Major"), ("E", "Minor")],
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


def tone_name_to_musicxml_parts(name: str) -> Tuple[str, Optional[int], int]:
    step = name[0]
    alter = None
    rest = name[1:]
    if rest.startswith('#'):
        alter = 1
        octave = int(rest[1:])
    elif rest.startswith('b'):
        alter = -1
        octave = int(rest[1:])
    else:
        octave = int(rest)
    return step, alter, octave


def normalize_note(note: str) -> str:
    note = str(note).strip().upper()
    return ALIASES.get(note, note)


def melody_pc(note: str) -> str:
    return normalize_note(note).replace("_HIGH", "")


def note_to_midi(note: str) -> int:
    return MELODY_MIDI[normalize_note(note)]


def note_to_musicxml_pitch(note: str) -> Tuple[str, Optional[int], int]:
    n = normalize_note(note)
    if n.endswith('_HIGH'):
        pc = n.replace('_HIGH', '')
        octave = 5
    else:
        pc = n
        octave = 4
    if len(pc) == 2 and pc[1] == '#':
        return pc[0], 1, octave
    if len(pc) == 2 and pc[1] == 'B':
        return pc[0], -1, octave
    return pc[0], None, octave


def chord_pitch_classes(chord_key: str) -> List[str]:
    chord = CHORD_BY_KEY[chord_key]
    root = PC_TO_SEMITONE[chord['root']]
    return [SEMITONE_TO_PC[(root + interval) % 12] for interval in chord['intervals']]


def build_default_transition_logits() -> Dict[str, Dict[str, float]]:
    logits = {}
    for src in STATE_KEYS:
        row = {}
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
    migrated = {}
    for src in STATE_KEYS:
        raw_row = logits.get(src, {})
        if not isinstance(raw_row, dict):
            raw_row = {}
            changed = True
        new_row = {}
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
        if set(raw_row.keys()) - set(STATE_KEYS):
            changed = True
        migrated[src] = new_row
    if set(logits.keys()) - set(STATE_KEYS):
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
            raise ValueError('Each measure must be a list of notes.')
        row = validate_flat_notes(measure)
        if len(row) > 4:
            raise ValueError('Each measure can contain at most 4 notes.')
        if row:
            cleaned.append(row)
    return cleaned


def flat_to_measures(notes: List[str]) -> List[List[str]]:
    return [notes[i:i+BEATS_PER_MEASURE] for i in range(0, len(notes), BEATS_PER_MEASURE)]


def chord_tone_role(chord_key: str, note_pc: str) -> Optional[str]:
    root = PC_TO_SEMITONE[CHORD_BY_KEY[chord_key]['root']]
    diff = (PC_TO_SEMITONE[note_pc] - root) % 12
    return {0:'root',3:'third',4:'third',6:'flat_five',7:'fifth',10:'seventh',11:'seventh'}.get(diff)


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
        if role == 'root':
            score += 3.2 * beat_weight; reasons.append('root fit')
        elif role == 'third':
            score += 3.0 * beat_weight; reasons.append('third fit')
        elif role == 'fifth':
            score += 2.1 * beat_weight; reasons.append('fifth fit')
        elif role == 'seventh':
            score += 1.8 * beat_weight; reasons.append('seventh color')
        else:
            score += -0.8 if note_pc in DIATONIC_KEY_PCS else -1.8
            reasons.append('non-chord passing tone' if note_pc in DIATONIC_KEY_PCS else 'out of key')
    if note_pcs[0] in pcs:
        score += 1.6; reasons.append('strong-beat anchor')
    if note_pcs[-1] in pcs:
        score += 1.2; reasons.append('cadential anchor')
    last_index = total_measures - 1
    if index == 0 and chord['family'] == 'tonic':
        score += 2.6; reasons.append('opening tonic')
    if index == last_index:
        if chord['key'] in {'C','Cmaj7','Am','Am7'}:
            score += 3.1; reasons.append('final stability')
        elif chord['family'] == 'dominant':
            score -= 2.2; reasons.append('weak final dominant')
    elif index == last_index - 1 and chord['family'] == 'dominant':
        score += 2.0; reasons.append('pre-cadence dominant')
    avg_midi = sum(midi_notes)/len(midi_notes)
    root_mid = 48 + PC_TO_SEMITONE[chord['root']]
    gap = avg_midi - root_mid
    if 12 <= gap <= 28:
        score += 0.9; reasons.append('good register gap')
    elif gap < 7:
        score -= 1.5; reasons.append('too close to bass')
    if chord['quality'] in {'maj7','min7','dom7'}:
        uses_seventh = any(chord_tone_role(chord_key, pc) == 'seventh' for pc in note_pcs)
        score += (1.0 + chord['color']) if uses_seventh else (0.3 * chord['color'])
        reasons.append('7th supported by melody' if uses_seventh else 'light color')
    if len(set(note_pcs)) == 1 and chord['family'] in {'tonic','dominant'}:
        score += 0.8; reasons.append('stable under repeated melody')
    return score, ', '.join(dict.fromkeys(reasons))


def transition_bonus(prev_key: Optional[str], curr_key: str, index: int, total_measures: int) -> Tuple[float, List[str]]:
    if prev_key is None:
        return 0.0, []
    prev = CHORD_BY_KEY[prev_key]
    curr = CHORD_BY_KEY[curr_key]
    bonus = 0.0
    reasons: List[str] = []
    if prev_key == curr_key:
        bonus -= 0.25; reasons.append('repeat penalty')
    good_moves = {
        ('Dm','G'), ('Dm','G7'), ('Dm7','G'), ('Dm7','G7'),
        ('G','C'), ('G','Cmaj7'), ('G7','C'), ('G7','Cmaj7'),
        ('F','G'), ('Fmaj7','G7'), ('C','Am'), ('Cmaj7','Am7'),
        ('Am','Dm'), ('Am7','Dm7'), ('Em','Am'), ('Bdim','C'), ('Bdim','Cmaj7'),
    }
    if (prev_key, curr_key) in good_moves:
        bonus += 0.9; reasons.append('functional move')
    if prev['family'] == 'predominant' and curr['family'] == 'dominant':
        bonus += 0.7; reasons.append('PD→D')
    if prev['family'] == 'dominant' and curr['family'] == 'tonic':
        bonus += 1.0; reasons.append('D→T')
    if prev['family'] == 'tonic' and curr['family'] == 'predominant':
        bonus += 0.4; reasons.append('T→PD')
    if index == total_measures - 1 and curr['family'] == 'dominant':
        bonus -= 1.1; reasons.append('avoid ending on dominant')
    if index == total_measures - 2 and curr['family'] == 'dominant':
        bonus += 0.8; reasons.append('penultimate dominant')
    if index == 0 and curr['family'] != 'tonic':
        bonus -= 0.8; reasons.append('non-tonic opening')
    return bonus, reasons


def candidate_upper_voicings(chord_key: str) -> List[List[int]]:
    pcs = chord_pitch_classes(chord_key)
    if CHORD_BY_KEY[chord_key]['quality'] in {'maj7','min7','dom7'} and len(pcs) >= 4:
        essential_sets = [[pcs[1], pcs[3], pcs[0]], [pcs[1], pcs[3], pcs[2]], [pcs[3], pcs[0], pcs[1]]]
    else:
        essential_sets = [[pcs[0], pcs[1], pcs[2]], [pcs[1], pcs[2], pcs[0]], [pcs[2], pcs[0], pcs[1]]]
    candidates = []
    for pcs_set in essential_sets:
        for octaves in product(range(3,5), range(3,6), range(3,6)):
            mids = sorted([(octave + 1) * 12 + PC_TO_SEMITONE[pc] for pc, octave in zip(pcs_set, octaves)])
            if len(set(mids)) < 3 or mids[0] < 50 or mids[-1] > 72 or mids[-1] - mids[0] > 16:
                continue
            candidates.append(mids)
    uniq = []
    seen = set()
    for cand in sorted(candidates):
        sig = tuple(cand)
        if sig not in seen:
            uniq.append(cand); seen.add(sig)
    return uniq or [[55,60,64]]


def chord_measure_pattern(chord_key: str) -> List[str]:
    # Root-position 4-note pattern like C E G C' / G B D G
    chord = CHORD_BY_KEY[chord_key]
    root_pc = chord['root']
    if chord_key in {'C', 'Cmaj7'}:
        base_octave = 3
    elif root_pc in {'F', 'G', 'A'}:
        base_octave = 2
    elif root_pc in {'D', 'E', 'B'}:
        base_octave = 2
    else:
        base_octave = 2
    intervals = chord['intervals'][:3] + [12]
    base = PC_TO_SEMITONE[root_pc] + (base_octave + 1) * 12
    names = []
    for interval in intervals:
        midi = base + interval
        names.append(midi_to_tone_name(midi))
    return names


def choose_voicings_for_path(state_keys: List[str], measures: List[List[str]]) -> List[Dict[str, object]]:
    chosen = []
    prev_upper = None
    for chord_key, measure_notes in zip(state_keys, measures):
        melody_floor = min(note_to_midi(n) for n in measure_notes)
        best_upper = None
        best_penalty = float('inf')
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
        root_pc = CHORD_BY_KEY[chord_key]['root']
        bass_midi = 36 + PC_TO_SEMITONE[root_pc]
        fifth_pc = pcs[2 if len(pcs) >= 3 else 0]
        bass_fifth_midi = 36 + PC_TO_SEMITONE[fifth_pc]
        chosen.append({
            'bass_note': midi_to_tone_name(bass_midi),
            'bass_fifth_note': midi_to_tone_name(bass_fifth_midi),
            'upper_notes': [midi_to_tone_name(m) for m in best_upper],
            'arpeggio_notes': [midi_to_tone_name(m) for m in best_upper],
            'measure_pattern_notes': chord_measure_pattern(chord_key),
        })
        prev_upper = best_upper
    return chosen


def k_best_paths(measures: List[List[str]], transition_probs: Dict[str, Dict[str, float]], k: int = 2):
    total = len(measures)
    beam = []
    for chord_key in STATE_KEYS:
        emit, reason = emission_detail(measures[0], chord_key, 0, total)
        beam.append({'score': emit, 'state_keys': [chord_key], 'details': [{'state_key': chord_key, 'emission_score': round(emit,4), 'reason': reason, 'transition_prob': None, 'transition_bonus': None, 'total_score': round(emit,4)}]})
    beam = sorted(beam, key=lambda x: x['score'], reverse=True)[:max(k * 5, 18)]
    for idx in range(1, total):
        expanded = []
        for cand in beam:
            prev_key = cand['state_keys'][-1]
            for chord_key in STATE_KEYS:
                emit, emit_reason = emission_detail(measures[idx], chord_key, idx, total)
                trans = transition_probs.get(prev_key, {}).get(chord_key, 1e-4)
                extra_bonus, extra_reasons = transition_bonus(prev_key, chord_key, idx, total)
                total_score = cand['score'] + safe_log(trans) + emit + extra_bonus
                reason = emit_reason if not extra_reasons else f"{emit_reason} | {'; '.join(extra_reasons)}"
                expanded.append({'score': total_score, 'state_keys': cand['state_keys'] + [chord_key], 'details': cand['details'] + [{'state_key': chord_key, 'emission_score': round(emit,4), 'reason': reason, 'transition_prob': round(trans,4), 'transition_bonus': round(extra_bonus,4), 'total_score': round(total_score,4)}]})
        uniq = {}
        for cand in sorted(expanded, key=lambda x: x['score'], reverse=True):
            sig = tuple(cand['state_keys'])
            if sig not in uniq:
                uniq[sig] = cand
            if len(uniq) >= max(k * 10, 40):
                break
        beam = list(uniq.values())
    return sorted(beam, key=lambda x: x['score'], reverse=True)[:k]


def diversify_second_path(best_paths, transition_probs, measures):
    if len(best_paths) >= 2:
        return best_paths[:2]
    if not best_paths:
        return []
    winner = best_paths[0]
    perturbed = deepcopy(transition_probs)
    for prev_key, curr_key in zip(winner['state_keys'][:-1], winner['state_keys'][1:]):
        perturbed[prev_key][curr_key] = max(1e-6, perturbed[prev_key][curr_key] * 0.62)
        total = sum(perturbed[prev_key].values())
        perturbed[prev_key] = {k: v / total for k, v in perturbed[prev_key].items()}
    retry = k_best_paths(measures, perturbed, k=3)
    merged = best_paths + retry
    uniq = []
    seen = set()
    for cand in merged:
        sig = tuple(cand['state_keys'])
        if sig not in seen:
            uniq.append(cand); seen.add(sig)
        if len(uniq) >= 2:
            break
    return uniq


def single_note_consonance_score(note: str, state: Tuple[str, str]) -> float:
    chord_root_name, chord_type = state
    base_divisor = 2.0 if chord_root_name == 'C' and chord_type == 'Major' else 4.0
    root_freq = FREQ_MAP[chord_root_name] / base_divisor
    chord_freqs = [root_freq * (2 ** (st / 12.0)) for st in CHORD_STRUCTURES_SIMPLE[chord_type]]
    mel_freq = FREQ_MAP_EXT[note]
    score = 0.0
    for cf in chord_freqs:
        if cf >= mel_freq:
            score -= 20.0
            continue
        if mel_freq / cf < 1.05:
            score -= 2.0
        ratio = max(mel_freq, cf) / min(mel_freq, cf)
        while ratio > 2.01:
            ratio /= 2.0
        for ideal, weight in CONSONANCE_RATIOS.items():
            if abs(ratio - ideal) < 0.03:
                score += weight
                break
    note_pc = melody_pc(note)
    targets = STYLE_TARGETS_KPOP.get(note_pc, [])
    if (chord_root_name, chord_type) in targets:
        score += 4.0
    elif note_pc in STYLE_TARGETS_KPOP:
        score -= 0.3
    return max(0.01, score)



def melody_intervals_for_single_note_mode(measures: List[List[str]]) -> List[int]:
    notes = [m[0] for m in measures if m]
    return [note_to_midi(notes[i + 1]) - note_to_midi(notes[i]) for i in range(len(notes) - 1)]


def analyze_single_note_motion(measures: List[List[str]]) -> Dict[str, float]:
    intervals = melody_intervals_for_single_note_mode(measures)
    if not intervals:
        return {
            'stepwise_ratio': 0.0,
            'same_direction_ratio': 0.0,
            'sequence_ratio': 0.0,
            'leap_ratio': 0.0,
            'canonical_strength': 0.0,
        }

    stepwise_count = sum(1 for iv in intervals if 0 < abs(iv) <= 2)
    leap_count = sum(1 for iv in intervals if abs(iv) >= 5)

    same_direction_pairs = 0
    valid_direction_pairs = 0
    repeated_interval_pairs = 0
    for a, b in zip(intervals, intervals[1:]):
        if a != 0 and b != 0:
            valid_direction_pairs += 1
            if (a > 0) == (b > 0):
                same_direction_pairs += 1
        if abs(a - b) <= 1:
            repeated_interval_pairs += 1

    stepwise_ratio = stepwise_count / len(intervals)
    leap_ratio = leap_count / len(intervals)
    same_direction_ratio = (same_direction_pairs / valid_direction_pairs) if valid_direction_pairs else 0.0
    sequence_ratio = (repeated_interval_pairs / max(1, len(intervals) - 1)) if len(intervals) > 1 else 0.0

    canonical_strength = (
        0.55 * stepwise_ratio +
        0.25 * sequence_ratio +
        0.15 * same_direction_ratio +
        0.05 * (1.0 - leap_ratio)
    )

    return {
        'stepwise_ratio': stepwise_ratio,
        'same_direction_ratio': same_direction_ratio,
        'sequence_ratio': sequence_ratio,
        'leap_ratio': leap_ratio,
        'canonical_strength': canonical_strength,
    }


def single_note_measure_chord_score(note: str, chord_key: str) -> float:
    chord = CHORD_BY_KEY[chord_key]
    note_pc = melody_pc(note)
    role = chord_tone_role(chord_key, note_pc)
    if role == 'root':
        score = 5.2
    elif role == 'third':
        score = 4.8
    elif role == 'fifth':
        score = 3.9
    elif role == 'seventh':
        score = 3.0 + chord.get('color', 0.0)
    elif note_pc in DIATONIC_KEY_PCS:
        score = 1.1
    else:
        score = -1.0

    midi = note_to_midi(note)
    bass_midi = 36 + PC_TO_SEMITONE[chord['root']]
    gap = midi - bass_midi
    if 19 <= gap <= 31:
        score += 0.7
    elif gap < 12:
        score -= 0.6
    return score


def single_note_path_score(state_keys: List[str], measures: List[List[str]], variant_letter: str = 'A') -> float:
    if not measures or len(state_keys) != len(measures):
        return 0.0

    total = 10.0
    motion = analyze_single_note_motion(measures)

    for idx, (measure, chord_key) in enumerate(zip(measures, state_keys)):
        note = measure[0]
        total += single_note_measure_chord_score(note, chord_key)

        chord = CHORD_BY_KEY[chord_key]
        if idx == 0 and chord['family'] == 'tonic':
            total += 1.3
        if idx == len(measures) - 1 and chord['family'] == 'tonic':
            total += 1.6

    total_measures = len(measures)
    for idx, (prev_key, curr_key) in enumerate(zip(state_keys[:-1], state_keys[1:]), start=1):
        total += 0.9
        total += transition_bonus(prev_key, curr_key, idx, total_measures)[0]
        simple_row = SINGLE_NOTE_TRANSITION_PROBS.get(prev_key)
        if simple_row is not None:
            total += 2.0 * simple_row.get(curr_key, 1e-4)
        elif prev_key != curr_key:
            total += 0.15

    total += 4.0 * motion['stepwise_ratio']
    total += 2.2 * motion['sequence_ratio']
    total += 1.0 * motion['same_direction_ratio']
    total -= 1.8 * motion['leap_ratio']

    if variant_letter.upper() == 'A':
        total += 1.15 * motion['canonical_strength']
    elif motion['canonical_strength'] >= 0.6:
        total -= 0.2

    return round(max(total, 0.1), 4)


def single_note_reason(measures: List[List[str]], variant_letter: str = 'A') -> str:
    motion = analyze_single_note_motion(measures)
    parts = ['single-note canon mode']
    if motion['stepwise_ratio'] >= 0.65:
        parts.append('stepwise melody bonus')
    if motion['sequence_ratio'] >= 0.45:
        parts.append('sequence / sequential contour bonus')
    if variant_letter.upper() == 'A' and motion['canonical_strength'] >= 0.55:
        parts.append('canon-style A preference')
    return ', '.join(parts)


def single_note_hmm_path(measures: List[List[str]]) -> List[str]:
    notes = [m[0] for m in measures]
    start_p = math.log(1.0 / len(SINGLE_NOTE_STATE_KEYS))
    V = [{}]
    path = {}
    for sk in SINGLE_NOTE_STATE_KEYS:
        emit = math.log(single_note_consonance_score(notes[0], SINGLE_NOTE_STATE_MAP[sk]))
        V[0][sk] = start_p + emit
        path[sk] = [sk]
    for t in range(1, len(notes)):
        V.append({})
        new_path = {}
        for curr_key in SINGLE_NOTE_STATE_KEYS:
            emit = math.log(single_note_consonance_score(notes[t], SINGLE_NOTE_STATE_MAP[curr_key]))
            best_prev = None
            best_prob = -float('inf')
            for prev_key in SINGLE_NOTE_STATE_KEYS:
                tr = SINGLE_NOTE_TRANSITION_PROBS.get(prev_key, {}).get(curr_key, 1e-4)
                prob = V[t-1][prev_key] + math.log(tr) + emit
                if prob > best_prob:
                    best_prob = prob
                    best_prev = prev_key
            V[t][curr_key] = best_prob
            new_path[curr_key] = path[best_prev] + [curr_key]
        path = new_path
    best_final = max(V[-1], key=V[-1].get)
    return path[best_final]


def build_single_note_variation_payload(state_keys: List[str], name: str, letter: str, measures: List[List[str]]):
    score = single_note_path_score(state_keys, measures, variant_letter=letter)
    reason_text = single_note_reason(measures, variant_letter=letter)
    chords = []
    for idx, chord_key in enumerate(state_keys):
        chord = CHORD_BY_KEY[chord_key]
        chords.append({
            'key': chord['key'],
            'label': chord['label'],
            'roman': chord['roman'],
            'family': chord['family'],
            'root': chord['root'],
            'quality': chord['quality'],
            'emission_score': None,
            'transition_prob': None,
            'transition_bonus': None,
            'reason': reason_text,
            'total_score': None,
            'bass_note': chord_measure_pattern(chord_key)[0],
            'bass_fifth_note': chord_measure_pattern(chord_key)[2],
            'upper_notes': chord_measure_pattern(chord_key)[1:],
            'arpeggio_notes': chord_measure_pattern(chord_key),
            'measure_pattern_notes': chord_measure_pattern(chord_key),
        })
    return {'id': letter, 'name': name, 'score': score, 'state_keys': state_keys, 'chords': chords}


def build_variation_payload(path_item, name: str, letter: str, measures: List[List[str]]):
    voicings = choose_voicings_for_path(path_item['state_keys'], measures)
    chords = []
    for detail, voicing in zip(path_item['details'], voicings):
        chord = CHORD_BY_KEY[detail['state_key']]
        chords.append({
            'key': chord['key'],
            'label': chord['label'],
            'roman': chord['roman'],
            'family': chord['family'],
            'root': chord['root'],
            'quality': chord['quality'],
            'emission_score': detail['emission_score'],
            'transition_prob': detail['transition_prob'],
            'transition_bonus': detail['transition_bonus'],
            'reason': detail['reason'],
            'total_score': detail['total_score'],
            **voicing,
        })
    return {'id': letter, 'name': name, 'score': round(path_item['score'], 4), 'state_keys': path_item['state_keys'], 'chords': chords}


def apply_variation_score_override(variation: Dict[str, object], score: float) -> Dict[str, object]:
    updated = deepcopy(variation)
    updated['score'] = round(max(score, 0.1), 4)
    return updated


def all_single_note_measures(measures: List[List[str]]) -> bool:
    return bool(measures) and all(len(m) == 1 for m in measures)


def generate_two_variations_from_measures(measures: List[List[str]]):
    model = ensure_model_state()
    if all_single_note_measures(measures):
        single_path = single_note_hmm_path(measures)
        variation_a = build_single_note_variation_payload(single_path, 'Variation A', 'A', measures)

        transition_probs = get_transition_probs(model)
        general_paths = diversify_second_path(k_best_paths(measures, transition_probs, k=2), transition_probs, measures)
        if not general_paths:
            variation_b = build_single_note_variation_payload(single_path, 'Variation B', 'B', measures)
        else:
            variation_b = build_variation_payload(general_paths[0], 'Variation B', 'B', measures)
            variation_b = apply_variation_score_override(
                variation_b,
                single_note_path_score(variation_b['state_keys'], measures, variant_letter='B')
            )

        if variation_a['score'] <= variation_b['score']:
            motion = analyze_single_note_motion(measures)
            edge = 0.6 if motion['canonical_strength'] >= 0.55 else 0.25
            variation_a = apply_variation_score_override(variation_a, variation_b['score'] + edge)

        return {
            'model_version': model.version,
            'bpm': SINGLE_NOTE_BPM,
            'measures': measures,
            'variation_a': variation_a,
            'variation_b': variation_b,
        }

    transition_probs = get_transition_probs(model)
    paths = diversify_second_path(k_best_paths(measures, transition_probs, k=2), transition_probs, measures)
    if len(paths) == 1:
        paths = [paths[0], paths[0]]
    return {
        'model_version': model.version,
        'bpm': DEFAULT_BPM,
        'measures': measures,
        'variation_a': build_variation_payload(paths[0], 'Variation A', 'A', measures),
        'variation_b': build_variation_payload(paths[1], 'Variation B', 'B', measures),
    }


def build_musicxml_bytes(measures: List[List[str]], variation: Dict[str, object], bpm: int) -> bytes:
    score = ET.Element('score-partwise', version='3.1')
    part_list = ET.SubElement(score, 'part-list')
    for pid, name in [('P1', 'Melody (R.H.)'), ('P2', 'Accompaniment (L.H.)')]:
        sp = ET.SubElement(part_list, 'score-part', id=pid)
        ET.SubElement(sp, 'part-name').text = name

    p1 = ET.SubElement(score, 'part', id='P1')
    for idx, measure_notes in enumerate(measures, start=1):
        m = ET.SubElement(p1, 'measure', number=str(idx))
        if idx == 1:
            attr = ET.SubElement(m, 'attributes')
            ET.SubElement(attr, 'divisions').text = '4'
            key = ET.SubElement(attr, 'key')
            ET.SubElement(key, 'fifths').text = '0'
            time = ET.SubElement(attr, 'time')
            ET.SubElement(time, 'beats').text = '4'
            ET.SubElement(time, 'beat-type').text = '4'
            clef = ET.SubElement(attr, 'clef')
            ET.SubElement(clef, 'sign').text = 'G'
            ET.SubElement(clef, 'line').text = '2'
            direction = ET.SubElement(m, 'direction', placement='above')
            direction_type = ET.SubElement(direction, 'direction-type')
            metro = ET.SubElement(direction_type, 'metronome')
            ET.SubElement(metro, 'beat-unit').text = 'quarter'
            ET.SubElement(metro, 'per-minute').text = str(bpm)
            ET.SubElement(direction, 'sound', tempo=str(bpm))
        if len(measure_notes) == 1:
            note = ET.SubElement(m, 'note')
            pitch = ET.SubElement(note, 'pitch')
            step, alter, octave = note_to_musicxml_pitch(measure_notes[0])
            ET.SubElement(pitch, 'step').text = step
            if alter is not None:
                ET.SubElement(pitch, 'alter').text = str(alter)
            ET.SubElement(pitch, 'octave').text = str(octave)
            ET.SubElement(note, 'duration').text = '16'
            ET.SubElement(note, 'type').text = 'whole'
        else:
            duration_map = {1: ('whole', 16), 2: ('half', 8), 4: ('quarter', 4)}
            typ, dur = duration_map.get(len(measure_notes), ('quarter', max(1, 16 // len(measure_notes))))
            for melody_note in measure_notes:
                note = ET.SubElement(m, 'note')
                pitch = ET.SubElement(note, 'pitch')
                step, alter, octave = note_to_musicxml_pitch(melody_note)
                ET.SubElement(pitch, 'step').text = step
                if alter is not None:
                    ET.SubElement(pitch, 'alter').text = str(alter)
                ET.SubElement(pitch, 'octave').text = str(octave)
                ET.SubElement(note, 'duration').text = str(dur)
                ET.SubElement(note, 'type').text = typ

    p2 = ET.SubElement(score, 'part', id='P2')
    for idx, chord in enumerate(variation['chords'], start=1):
        m = ET.SubElement(p2, 'measure', number=str(idx))
        if idx == 1:
            attr = ET.SubElement(m, 'attributes')
            ET.SubElement(attr, 'divisions').text = '4'
            key = ET.SubElement(attr, 'key')
            ET.SubElement(key, 'fifths').text = '0'
            time = ET.SubElement(attr, 'time')
            ET.SubElement(time, 'beats').text = '4'
            ET.SubElement(time, 'beat-type').text = '4'
            clef = ET.SubElement(attr, 'clef')
            ET.SubElement(clef, 'sign').text = 'F'
            ET.SubElement(clef, 'line').text = '4'
        pattern = chord.get('measure_pattern_notes') or [chord['bass_note'], *chord['upper_notes'][:3]]
        for name in pattern[:4]:
            note = ET.SubElement(m, 'note')
            pitch = ET.SubElement(note, 'pitch')
            step, alter, octave = tone_name_to_musicxml_parts(name)
            ET.SubElement(pitch, 'step').text = step
            if alter is not None:
                ET.SubElement(pitch, 'alter').text = str(alter)
            ET.SubElement(pitch, 'octave').text = str(octave)
            ET.SubElement(note, 'duration').text = '4'
            ET.SubElement(note, 'type').text = 'quarter'

    raw = ET.tostring(score)
    pretty = minidom.parseString(raw).toprettyxml(indent='  ')
    return pretty.encode('utf-8')


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


@app.route('/')
def index():
    return render_template('index.html')


@app.get('/api/health')
def health():
    model = ensure_model_state()
    db.session.execute(text('SELECT 1'))
    return jsonify({'ok': True, 'model_version': model.version, 'database': app.config['SQLALCHEMY_DATABASE_URI'].split(':', 1)[0]})


@app.post('/api/generate')
def api_generate():
    payload = request.get_json(force=True)
    raw_measures = payload.get('measures')
    raw_notes = payload.get('notes', [])
    try:
        if raw_measures:
            measures = validate_measures(raw_measures)
            cleaned = [n for m in measures for n in m]
        else:
            cleaned = validate_flat_notes(raw_notes)
            measures = flat_to_measures(cleaned)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if len(cleaned) < 4:
        return jsonify({'error': 'Need at least 4 notes.'}), 400
    data = generate_two_variations_from_measures(measures)
    comparison_id = str(uuid.uuid4())
    comparison = Comparison(id=comparison_id, melody={'notes': cleaned, 'measures': measures, 'bpm': data['bpm']}, variation_a=data['variation_a'], variation_b=data['variation_b'], model_version=data['model_version'])
    db.session.add(comparison)
    db.session.commit()
    data['musicxml_a_url'] = f"/api/comparison/{comparison_id}/musicxml/A"
    data['musicxml_b_url'] = f"/api/comparison/{comparison_id}/musicxml/B"
    return jsonify({'comparison_id': comparison_id, **data})


@app.post('/api/vote')
def api_vote():
    payload = request.get_json(force=True)
    comparison_id = payload.get('comparison_id')
    winner = str(payload.get('winner', '')).upper()
    if winner not in {'A', 'B'}:
        return jsonify({'error': 'winner must be A or B'}), 400
    comparison = db.session.get(Comparison, comparison_id)
    if comparison is None:
        return jsonify({'error': 'comparison not found'}), 404
    if comparison.voted:
        return jsonify({'error': 'vote already recorded for this comparison'}), 409
    model = ensure_model_state()
    before_version = model.version
    winner_keys = comparison.variation_a['state_keys'] if winner == 'A' else comparison.variation_b['state_keys']
    loser_keys = comparison.variation_b['state_keys'] if winner == 'A' else comparison.variation_a['state_keys']
    update_transition_logits_from_preference(model, winner_keys, loser_keys)
    comparison.voted = True
    vote = Vote(comparison_id=comparison.id, winner=winner, model_version_before=before_version, model_version_after=model.version)
    db.session.add(vote)
    db.session.commit()
    return jsonify({'ok': True, 'message': f'Vote {winner} saved.', 'model_version_before': before_version, 'model_version_after': model.version})


@app.get('/api/model')
def api_model():
    model = ensure_model_state()
    return jsonify({'model_version': model.version, 'learning_rate': model.learning_rate, 'transition_probs': get_transition_probs(model)})


@app.get('/api/comparison/<comparison_id>/musicxml/<letter>')
def api_musicxml_download(comparison_id: str, letter: str):
    comparison = db.session.get(Comparison, comparison_id)
    if comparison is None:
        return jsonify({'error': 'comparison not found'}), 404
    letter = letter.upper()
    if letter not in {'A', 'B'}:
        return jsonify({'error': 'letter must be A or B'}), 400
    variation = comparison.variation_a if letter == 'A' else comparison.variation_b
    melody_data = comparison.melody or {}
    measures = melody_data.get('measures', [])
    bpm = melody_data.get('bpm') or (SINGLE_NOTE_BPM if all_single_note_measures(measures) else DEFAULT_BPM)
    xml_bytes = build_musicxml_bytes(measures, variation, bpm)
    filename = f"{comparison_id}_{letter}.musicxml"
    return Response(
        xml_bytes,
        mimetype='application/vnd.recordare.musicxml+xml',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


with app.app_context():
    db.create_all()
    ensure_model_state()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '10000'))
    app.run(host='0.0.0.0', port=port, debug=True)
