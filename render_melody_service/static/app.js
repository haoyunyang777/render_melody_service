const noteButtons = [
  { label: 'C', note: 'C', key: 'a' },
  { label: 'D', note: 'D', key: 's' },
  { label: 'E', note: 'E', key: 'd' },
  { label: 'F', note: 'F', key: 'f' },
  { label: 'G', note: 'G', key: 'g' },
  { label: 'A', note: 'A', key: 'h' },
  { label: 'B', note: 'B', key: 'j' },
  { label: "C'", note: 'C_HIGH', key: 'k' },
  { label: "D'", note: 'D_HIGH', key: 'l' },
  { label: "E'", note: 'E_HIGH', key: ';' },
  { label: "F'", note: 'F_HIGH', key: "'" }
];

const NOTE_TO_TONE = {
  C: 'C4', D: 'D4', E: 'E4', F: 'F4', G: 'G4', A: 'A4', B: 'B4',
  C_HIGH: 'C5', D_HIGH: 'D5', E_HIGH: 'E5', F_HIGH: 'F5'
};

const CHORD_NOTES = {
  C: ['C3', 'E3', 'G3', 'C4'],
  Em: ['E2', 'G2', 'B2', 'E3'],
  F: ['F2', 'A2', 'C3', 'F3'],
  G: ['G2', 'B2', 'D3', 'G3'],
  Am: ['A2', 'C3', 'E3', 'A3']
};

let melody = [];
let latestComparison = null;
let synth = null;
let polySynth = null;
let transportBusy = false;

const pianoEl = document.getElementById('piano');
const melodyMeasuresEl = document.getElementById('melodyMeasures');
const noteCountEl = document.getElementById('noteCount');
const modelVersionEl = document.getElementById('modelVersion');
const resultSectionEl = document.getElementById('resultSection');
const matrixEl = document.getElementById('matrix');

function groupMeasures(notes) {
  const result = [];
  for (let i = 0; i < notes.length; i += 4) result.push(notes.slice(i, i + 4));
  return result;
}

function formatNote(note) {
  return note.replace('_HIGH', "'");
}

function renderMelody() {
  noteCountEl.textContent = String(melody.length);
  if (!melody.length) {
    melodyMeasuresEl.textContent = '(empty)';
    return;
  }
  melodyMeasuresEl.textContent = groupMeasures(melody)
    .map(measure => measure.map(formatNote).join(' '))
    .join(' | ');
}

function flashButton(note) {
  const btn = document.querySelector(`[data-note="${note}"]`);
  if (!btn) return;
  btn.classList.add('active');
  window.setTimeout(() => btn.classList.remove('active'), 120);
}

async function ensureAudio() {
  if (!window.Tone) return;
  if (!synth) {
    await Tone.start();
    synth = new Tone.Synth({
      oscillator: { type: 'triangle' },
      envelope: { attack: 0.01, decay: 0.1, sustain: 0.15, release: 0.2 }
    }).toDestination();
    polySynth = new Tone.PolySynth(Tone.Synth).toDestination();
  }
}

async function playPreview(note) {
  await ensureAudio();
  const toneNote = NOTE_TO_TONE[note];
  if (synth && toneNote) synth.triggerAttackRelease(toneNote, '8n');
}

async function addNote(note) {
  melody.push(note);
  renderMelody();
  flashButton(note);
  await playPreview(note);
}

function buildPiano() {
  noteButtons.forEach(({ label, note, key }) => {
    const btn = document.createElement('button');
    btn.className = 'piano-key';
    btn.dataset.note = note;
    btn.innerHTML = `<span>${label}</span><small>${key.toUpperCase()}</small>`;
    btn.addEventListener('click', () => addNote(note));
    pianoEl.appendChild(btn);
  });
}

function renderVariation(targetId, variation) {
  const root = document.getElementById(targetId);
  root.innerHTML = '';
  variation.chords.forEach((chord, idx) => {
    const card = document.createElement('div');
    card.className = 'chord-cell';
    card.innerHTML = `
      <div class="measure-index">Bar ${idx + 1}</div>
      <div class="chord-label">${chord.label}</div>
      <div class="tiny">emit ${chord.emission_score}</div>
      <div class="tiny">${chord.transition_prob == null ? 'start' : 'trans ' + chord.transition_prob}</div>
    `;
    root.appendChild(card);
  });
}

function renderComparison(data) {
  latestComparison = data;
  resultSectionEl.classList.remove('hidden');
  document.getElementById('scoreA').textContent = `score ${data.variation_a.score}`;
  document.getElementById('scoreB').textContent = `score ${data.variation_b.score}`;
  renderVariation('chordsA', data.variation_a);
  renderVariation('chordsB', data.variation_b);
  modelVersionEl.textContent = String(data.model_version);
}

async function generateVariations() {
  if (melody.length < 4) {
    alert('Please enter at least 4 notes.');
    return;
  }

  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes: melody })
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || 'Generation failed');
    return;
  }
  renderComparison(data);
  await refreshModel();
}

async function playVariation(which) {
  if (!latestComparison || transportBusy) return;
  await ensureAudio();
  transportBusy = true;

  const variation = which === 'A' ? latestComparison.variation_a : latestComparison.variation_b;
  const measures = latestComparison.measures;
  const beatSeconds = 60 / (latestComparison.bpm || 100);
  const startAt = Tone.now() + 0.05;

  let t = startAt;
  for (let m = 0; m < measures.length; m++) {
    const notes = measures[m];
    const chord = variation.chords[m];
    const chordNotes = CHORD_NOTES[chord.label] || CHORD_NOTES.C;

    polySynth.triggerAttackRelease(chordNotes, '1m', t, 0.22);

    for (let i = 0; i < notes.length; i++) {
      const toneNote = NOTE_TO_TONE[notes[i]];
      if (toneNote) synth.triggerAttackRelease(toneNote, '4n', t + i * beatSeconds, 0.8);
    }
    t += beatSeconds * 4;
  }

  const totalMs = Math.ceil((t - startAt) * 1000) + 300;
  window.setTimeout(() => { transportBusy = false; }, totalMs);
}

async function vote(which) {
  if (!latestComparison) {
    alert('Generate variations first.');
    return;
  }
  const res = await fetch('/api/vote', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comparison_id: latestComparison.comparison_id, winner: which })
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || 'Vote failed');
    return;
  }
  alert(`${data.message} Model version is now ${data.model_version_after}.`);
  modelVersionEl.textContent = String(data.model_version_after);
  await refreshModel();
}

function loadDemoMelody() {
  melody = ['C', 'C', 'G', 'G', 'A', 'A', 'G', 'G', 'F', 'F', 'E', 'E', 'D', 'D', 'C', 'C'];
  renderMelody();
}

function renderMatrixTable(transition_probs) {
  const states = Object.keys(transition_probs);
  const table = document.createElement('table');
  table.className = 'matrix-table';
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  hr.innerHTML = '<th>From \\ To</th>' + states.map(s => `<th>${s}</th>`).join('');
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  states.forEach(src => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<th>${src}</th>` + states.map(dst => `<td>${transition_probs[src][dst].toFixed(3)}</td>`).join('');
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  matrixEl.innerHTML = '';
  matrixEl.appendChild(table);
}

async function refreshModel() {
  const res = await fetch('/api/model');
  const data = await res.json();
  modelVersionEl.textContent = String(data.model_version);
  renderMatrixTable(data.transition_probs);
}

function setupButtons() {
  document.getElementById('undoBtn').addEventListener('click', () => {
    melody.pop();
    renderMelody();
  });
  document.getElementById('clearBtn').addEventListener('click', () => {
    melody = [];
    latestComparison = null;
    resultSectionEl.classList.add('hidden');
    renderMelody();
  });
  document.getElementById('demoBtn').addEventListener('click', loadDemoMelody);
  document.getElementById('generateBtn').addEventListener('click', generateVariations);
  document.getElementById('playA').addEventListener('click', () => playVariation('A'));
  document.getElementById('playB').addEventListener('click', () => playVariation('B'));
  document.getElementById('voteA').addEventListener('click', () => vote('A'));
  document.getElementById('voteB').addEventListener('click', () => vote('B'));
}

function setupKeyboardInput() {
  const keyMap = {
    a: 'C', s: 'D', d: 'E', f: 'F', g: 'G', h: 'A', j: 'B',
    k: 'C_HIGH', l: 'D_HIGH', ';': 'E_HIGH', "'": 'F_HIGH'
  };

  window.addEventListener('keydown', async (event) => {
    if (event.target && ['INPUT', 'TEXTAREA'].includes(event.target.tagName)) return;
    if (event.key === 'Backspace') {
      event.preventDefault();
      melody.pop();
      renderMelody();
      return;
    }
    const note = keyMap[event.key.toLowerCase()];
    if (note) {
      event.preventDefault();
      await addNote(note);
    }
  });
}

buildPiano();
setupButtons();
setupKeyboardInput();
renderMelody();
refreshModel();
