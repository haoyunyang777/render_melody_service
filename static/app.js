const noteButtons = [
  { label: 'C', note: 'C', key: 'A' },
  { label: 'D', note: 'D', key: 'S' },
  { label: 'E', note: 'E', key: 'D' },
  { label: 'F', note: 'F', key: 'F' },
  { label: 'G', note: 'G', key: 'G' },
  { label: 'A', note: 'A', key: 'H' },
  { label: 'B', note: 'B', key: 'J' },
  { label: "C'", note: 'C_HIGH', key: 'K' },
  { label: "D'", note: 'D_HIGH', key: 'L' },
  { label: "E'", note: 'E_HIGH', key: ';' },
  { label: "F'", note: 'F_HIGH', key: "'" }
];

const NOTE_TO_TONE = {
  C: 'C4', D: 'D4', E: 'E4', F: 'F4', G: 'G4', A: 'A4', B: 'B4',
  C_HIGH: 'C5', D_HIGH: 'D5', E_HIGH: 'E5', F_HIGH: 'F5'
};

let measures = [];
let currentMeasure = [];
let latestComparison = null;
let transportBusy = false;

let pianoSampler = null;
let previewSynth = null;
let reverb = null;
let compressor = null;

const pianoEl = document.getElementById('piano');
const noteCountEl = document.getElementById('noteCount');
const measureCountEl = document.getElementById('measureCount');
const melodyMeasuresEl = document.getElementById('melodyMeasures');
const resultSectionEl = document.getElementById('resultSection');
const modelVersionEl = document.getElementById('modelVersion');
const matrixEl = document.getElementById('matrix');

function formatNote(note) {
  return note.replace('_HIGH', "'");
}

function allMeasuresForDisplay() {
  return currentMeasure.length ? [...measures, [...currentMeasure]] : [...measures];
}

function flattenMelody() {
  return allMeasuresForDisplay().flat();
}

function renderMelody() {
  const all = allMeasuresForDisplay();
  noteCountEl.textContent = String(flattenMelody().length);
  measureCountEl.textContent = String(all.length);
  melodyMeasuresEl.textContent = all.length ? all.map(m => m.map(formatNote).join(' ')).join(' | ') : '(empty)';
}

function flashButton(note) {
  const btn = pianoEl.querySelector(`[data-note="${note}"]`);
  if (!btn) return;
  btn.classList.add('active');
  window.setTimeout(() => btn.classList.remove('active'), 120);
}

async function ensureAudio() {
  if (!window.Tone) return;
  if (pianoSampler && previewSynth) return;

  await Tone.start();
  compressor = new Tone.Compressor(-18, 4).toDestination();
  reverb = new Tone.Reverb({ decay: 2.8, wet: 0.18 });
  reverb.connect(compressor);

  try {
    pianoSampler = new Tone.Sampler({
      urls: {
        A1: 'A1.mp3', C2: 'C2.mp3', 'D#2': 'Ds2.mp3', 'F#2': 'Fs2.mp3',
        A2: 'A2.mp3', C3: 'C3.mp3', 'D#3': 'Ds3.mp3', 'F#3': 'Fs3.mp3',
        A3: 'A3.mp3', C4: 'C4.mp3', 'D#4': 'Ds4.mp3', 'F#4': 'Fs4.mp3', A4: 'A4.mp3', C5: 'C5.mp3'
      },
      baseUrl: 'https://tonejs.github.io/audio/salamander/',
      release: 1.4
    }).connect(reverb);
    await Tone.loaded();
  } catch (err) {
    console.warn('Sampler failed to load, falling back to synth.', err);
    pianoSampler = new Tone.PolySynth(Tone.AMSynth, {
      harmonicity: 1.2,
      oscillator: { type: 'sine' },
      envelope: { attack: 0.01, decay: 0.35, sustain: 0.25, release: 1.3 }
    }).connect(reverb);
  }

  previewSynth = new Tone.Synth({
    oscillator: { type: 'triangle' },
    envelope: { attack: 0.005, decay: 0.08, sustain: 0.12, release: 0.25 }
  }).connect(compressor);
}

async function playPreview(note) {
  await ensureAudio();
  const toneNote = NOTE_TO_TONE[note];
  if (toneNote) previewSynth.triggerAttackRelease(toneNote, '8n', Tone.now(), 0.8);
}

async function addNote(note) {
  if (currentMeasure.length >= 4) endMeasure();
  currentMeasure.push(note);
  renderMelody();
  flashButton(note);
  await playPreview(note);
}

function endMeasure() {
  if (!currentMeasure.length) return;
  measures.push([...currentMeasure]);
  currentMeasure = [];
  renderMelody();
}

function undoLast() {
  if (currentMeasure.length) {
    currentMeasure.pop();
  } else if (measures.length) {
    currentMeasure = measures.pop();
    currentMeasure.pop();
  }
  renderMelody();
}

function buildPiano() {
  noteButtons.forEach(({ label, note, key }) => {
    const btn = document.createElement('button');
    btn.className = 'piano-key';
    btn.dataset.note = note;
    btn.innerHTML = `<span>${label}</span><small>${key}</small>`;
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
      <div class="tiny">${chord.roman} · ${chord.family}</div>
      <div class="tiny">upper: ${chord.upper_notes.join(' ')}</div>
      <div class="tiny">bass: ${chord.bass_note}</div>
      <div class="tiny">${chord.reason}</div>
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
  const payloadMeasures = allMeasuresForDisplay();
  if (payloadMeasures.flat().length < 4) {
    alert('Please enter at least 4 notes.');
    return;
  }
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ measures: payloadMeasures })
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || 'Generation failed');
    return;
  }
  renderComparison(data);
  await refreshModel();
}

function scheduleMeasurePlayback(baseTime, measureNotes, chord, bpm) {
  const beatSeconds = 60 / bpm;
  const melodyStep = 4 / measureNotes.length;
  const sampler = pianoSampler;

  sampler.triggerAttackRelease(chord.bass_note, '2n', baseTime, 0.50);
  sampler.triggerAttackRelease(chord.upper_notes, '2n', baseTime + 0.02, 0.23);
  sampler.triggerAttackRelease(chord.bass_fifth_note, '2n', baseTime + 2 * beatSeconds, 0.34);
  sampler.triggerAttackRelease([chord.upper_notes[1], chord.upper_notes[2]].filter(Boolean), '2n', baseTime + 2 * beatSeconds + 0.02, 0.18);

  const arp = chord.arpeggio_notes || chord.upper_notes;
  if (arp.length >= 3) {
    sampler.triggerAttackRelease(arp[0], '8n', baseTime + 0.5 * beatSeconds, 0.14);
    sampler.triggerAttackRelease(arp[1], '8n', baseTime + 1.5 * beatSeconds, 0.12);
    sampler.triggerAttackRelease(arp[2], '8n', baseTime + 3.5 * beatSeconds, 0.12);
  }

  for (let i = 0; i < measureNotes.length; i++) {
    const toneNote = NOTE_TO_TONE[measureNotes[i]];
    if (!toneNote) continue;
    const startBeat = i * melodyStep;
    sampler.triggerAttackRelease(toneNote, melodyStep * beatSeconds, baseTime + startBeat * beatSeconds, 0.78);
  }
}

async function playVariation(which) {
  if (!latestComparison || transportBusy) return;
  await ensureAudio();
  transportBusy = true;

  const variation = which === 'A' ? latestComparison.variation_a : latestComparison.variation_b;
  const measureList = latestComparison.measures;
  const bpm = latestComparison.bpm || 92;
  const beatSeconds = 60 / bpm;
  const startAt = Tone.now() + 0.08;

  let t = startAt;
  for (let m = 0; m < measureList.length; m++) {
    scheduleMeasurePlayback(t, measureList[m], variation.chords[m], bpm);
    t += beatSeconds * 4;
  }
  window.setTimeout(() => { transportBusy = false; }, Math.ceil((t - startAt) * 1000) + 500);
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
  measures = [['C','C','G','G'], ['A','A','G','G'], ['F','F','E','E'], ['D','D','C','C']];
  currentMeasure = [];
  latestComparison = null;
  resultSectionEl.classList.add('hidden');
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
  document.getElementById('endMeasureBtn').addEventListener('click', endMeasure);
  document.getElementById('undoBtn').addEventListener('click', undoLast);
  document.getElementById('clearBtn').addEventListener('click', () => {
    measures = [];
    currentMeasure = [];
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
  const keyMap = { a: 'C', s: 'D', d: 'E', f: 'F', g: 'G', h: 'A', j: 'B', k: 'C_HIGH', l: 'D_HIGH', ';': 'E_HIGH', "'": 'F_HIGH' };
  window.addEventListener('keydown', async event => {
    if (event.target && ['INPUT', 'TEXTAREA'].includes(event.target.tagName)) return;
    if (event.key === ' ') {
      event.preventDefault();
      endMeasure();
      return;
    }
    if (event.key === 'Backspace') {
      event.preventDefault();
      undoLast();
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