const noteButtons = [
  { label: 'C', note: 'C', key: 'A', solfege: 'Do' },
  { label: 'D', note: 'D', key: 'S', solfege: 'Re' },
  { label: 'E', note: 'E', key: 'D', solfege: 'Mi' },
  { label: 'F', note: 'F', key: 'F', solfege: 'Fa' },
  { label: 'G', note: 'G', key: 'G', solfege: 'Sol' },
  { label: 'A', note: 'A', key: 'H', solfege: 'La' },
  { label: 'B', note: 'B', key: 'J', solfege: 'Ti' },
  { label: "C'", note: 'C_HIGH', key: 'K', solfege: 'Do' },
  { label: "D'", note: 'D_HIGH', key: 'L', solfege: 'Re' },
  { label: "E'", note: 'E_HIGH', key: ';', solfege: 'Mi' },
  { label: "F'", note: 'F_HIGH', key: "'", solfege: 'Fa' }
];

const NOTE_TO_TONE = {
  C: 'C4', D: 'D4', E: 'E4', F: 'F4', G: 'G4', A: 'A4', B: 'B4',
  C_HIGH: 'C5', D_HIGH: 'D5', E_HIGH: 'E5', F_HIGH: 'F5'
};

const DEMO_MELODIES = [
  {
    title: 'Twinkle Twinkle Little Star',
    measures: [['C','C','G','G'], ['A','A','G','G'], ['F','F','E','E'], ['D','D','C','C']]
  },
  {
    title: 'Mary Had a Little Lamb',
    measures: [['E','D','C','D'], ['E','E','E','E'], ['D','D','D','D'], ['E','G','G','G']]
  },
  {
    title: 'Ode to Joy',
    measures: [['E','E','F','G'], ['G','F','E','D'], ['C','C','D','E'], ['E','D','D','D']]
  },
  {
    title: 'Frere Jacques',
    measures: [['C','D','E','C'], ['C','D','E','C'], ['E','F','G','G'], ['E','F','G','G']]
  },
  {
    title: 'Old MacDonald Had a Farm',
    measures: [['G','G','G','D'], ['E','E','D','D'], ['B','B','A','A'], ['G','G','G','G']]
  },
  {
    title: 'Jingle Bells',
    measures: [['E','E','E','E'], ['E','E','E','G'], ['C','D','E','F'], ['G','G','G','G']]
  },
  {
    title: 'Amazing Grace',
    measures: [['C','F','A','F'], ['A','G','E','C'], ['F','A','C','A'], ['G','F','F','F']]
  },
  {
    title: 'Auld Lang Syne',
    measures: [['C','F','F','F'], ['A','G','F','G'], ['A','F','F','A'], ['C','C','D','C']]
  },
  {
    title: 'When the Saints Go Marching In',
    measures: [['C','E','F','G'], ['C','E','F','G'], ['C','E','F','G'], ['F','E','D','C']]
  },
  {
    title: 'Greensleeves',
    measures: [['E','G','A','B'], ['C_HIGH','B','A','G'], ['E','F','G','A'], ['B','A','G','E']]
  }
];

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
const feedbackEl = document.getElementById('actionFeedback');

const endMeasureBtn = document.getElementById('endMeasureBtn');
const undoBtn = document.getElementById('undoBtn');
const clearBtn = document.getElementById('clearBtn');
const demoBtn = document.getElementById('demoBtn');
const generateBtn = document.getElementById('generateBtn');
const playABtn = document.getElementById('playA');
const playBBtn = document.getElementById('playB');
const voteABtn = document.getElementById('voteA');
const voteBBtn = document.getElementById('voteB');

function formatNote(note) {
  return note.replace('_HIGH', "'");
}

function showFeedback(message, type = 'info') {
  if (!feedbackEl) {
    console.log(message);
    return;
  }
  feedbackEl.textContent = message;
  feedbackEl.className = `action-feedback ${type}`;
}

function flashElement(el, className = 'btn-flash', duration = 180) {
  if (!el) return;
  el.classList.add(className);
  window.setTimeout(() => el.classList.remove(className), duration);
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
  melodyMeasuresEl.textContent = all.length
    ? all.map(m => m.map(formatNote).join(' ')).join(' | ')
    : '(empty)';
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
        A1: 'A1.mp3',
        C2: 'C2.mp3',
        'D#2': 'Ds2.mp3',
        'F#2': 'Fs2.mp3',
        A2: 'A2.mp3',
        C3: 'C3.mp3',
        'D#3': 'Ds3.mp3',
        'F#3': 'Fs3.mp3',
        A3: 'A3.mp3',
        C4: 'C4.mp3',
        'D#4': 'Ds4.mp3',
        'F#4': 'Fs4.mp3',
        A4: 'A4.mp3',
        C5: 'C5.mp3'
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
  if (toneNote) {
    previewSynth.triggerAttackRelease(toneNote, '8n', Tone.now(), 0.8);
  }
}

async function addNote(note) {
  if (currentMeasure.length >= 4) {
    endMeasure();
  }
  currentMeasure.push(note);
  renderMelody();
  flashButton(note);
  await playPreview(note);
  showFeedback(`Added note ${formatNote(note)} to current measure.`, 'info');
}

function endMeasure() {
  if (!currentMeasure.length) {
    showFeedback('Current measure is empty.', 'warn');
    flashElement(endMeasureBtn);
    return;
  }

  measures.push([...currentMeasure]);
  currentMeasure = [];
  renderMelody();

  melodyMeasuresEl.classList.add('measure-flash');
  window.setTimeout(() => melodyMeasuresEl.classList.remove('measure-flash'), 220);
  flashElement(endMeasureBtn);

  showFeedback(`Measure ${measures.length} saved.`, 'success');
}

function undoLast() {
  if (currentMeasure.length) {
    currentMeasure.pop();
    renderMelody();
    showFeedback('Removed last note from current measure.', 'info');
    return;
  }

  if (measures.length) {
    currentMeasure = measures.pop();
    currentMeasure.pop();
    renderMelody();
    showFeedback('Moved back to previous measure and removed last note.', 'info');
    return;
  }

  showFeedback('Nothing to undo.', 'warn');
}

function buildPiano() {
  noteButtons.forEach(({ label, note, key, solfege }) => {
    const btn = document.createElement('button');
    btn.className = 'piano-key';
    btn.dataset.note = note;
    btn.innerHTML = `
      <small>${solfege}</small>
      <span>${label}</span>
      <small>${key}</small>
    `;
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
  showFeedback('Generated 2 chord variations. Play A/B and vote.', 'success');
}

async function generateVariations() {
  const payloadMeasures = allMeasuresForDisplay();

  if (payloadMeasures.flat().length < 4) {
    showFeedback('Please enter at least 4 notes.', 'warn');
    return;
  }

  generateBtn.disabled = true;
  showFeedback('Generating chord variations...', 'info');

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ measures: payloadMeasures })
    });

    const data = await res.json();

    if (!res.ok) {
      showFeedback(data.error || 'Generation failed.', 'error');
      return;
    }

    renderComparison(data);
    await refreshModel();
  } catch (err) {
    console.error(err);
    showFeedback('Generation failed due to network/server error.', 'error');
  } finally {
    generateBtn.disabled = false;
  }
}

function scheduleMeasurePlayback(baseTime, measureNotes, chord, bpm) {
  const beatSeconds = 60 / bpm;
  const melodyStep = 4 / measureNotes.length;
  const sampler = pianoSampler;

  sampler.triggerAttackRelease(chord.bass_note, '2n', baseTime, 0.50);
  sampler.triggerAttackRelease(chord.upper_notes, '2n', baseTime + 0.02, 0.23);
  sampler.triggerAttackRelease(chord.bass_fifth_note, '2n', baseTime + 2 * beatSeconds, 0.34);
  sampler.triggerAttackRelease(
    [chord.upper_notes[1], chord.upper_notes[2]].filter(Boolean),
    '2n',
    baseTime + 2 * beatSeconds + 0.02,
    0.18
  );

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
    sampler.triggerAttackRelease(
      toneNote,
      melodyStep * beatSeconds,
      baseTime + startBeat * beatSeconds,
      0.78
    );
  }
}

async function playVariation(which) {
  if (!latestComparison || transportBusy) {
    if (!latestComparison) {
      showFeedback('Generate chord variations first.', 'warn');
    }
    return;
  }

  await ensureAudio();
  transportBusy = true;

  const variation = which === 'A' ? latestComparison.variation_a : latestComparison.variation_b;
  const measureList = latestComparison.measures;
  const bpm = latestComparison.bpm || 92;
  const beatSeconds = 60 / bpm;
  const startAt = Tone.now() + 0.08;

  showFeedback(`Playing variation ${which}...`, 'info');

  let t = startAt;
  for (let m = 0; m < measureList.length; m++) {
    scheduleMeasurePlayback(t, measureList[m], variation.chords[m], bpm);
    t += beatSeconds * 4;
  }

  window.setTimeout(() => {
    transportBusy = false;
    showFeedback(`Finished variation ${which}.`, 'success');
  }, Math.ceil((t - startAt) * 1000) + 500);
}

async function vote(which) {
  if (!latestComparison) {
    showFeedback('Generate chord variations first.', 'warn');
    return;
  }

  voteABtn.disabled = true;
  voteBBtn.disabled = true;
  showFeedback(`Submitting vote for variation ${which}...`, 'info');

  try {
    const res = await fetch('/api/vote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        comparison_id: latestComparison.comparison_id,
        winner: which
      })
    });

    const data = await res.json();

    if (!res.ok) {
      showFeedback(data.error || 'Vote failed.', 'error');
      return;
    }

    modelVersionEl.textContent = String(data.model_version_after);
    await refreshModel();

    flashElement(which === 'A' ? voteABtn : voteBBtn, 'btn-flash', 300);
    showFeedback(
      `Vote recorded: variation ${which} is better. Model version is now ${data.model_version_after}.`,
      'success'
    );
  } catch (err) {
    console.error(err);
    showFeedback('Vote failed due to network/server error.', 'error');
  } finally {
    voteABtn.disabled = false;
    voteBBtn.disabled = false;
  }
}

function loadDemoMelody() {
  const randomIndex = Math.floor(Math.random() * DEMO_MELODIES.length);
  const chosen = DEMO_MELODIES[randomIndex];

  measures = chosen.measures.map(m => [...m]);
  currentMeasure = [];
  latestComparison = null;
  resultSectionEl.classList.add('hidden');
  renderMelody();

  flashElement(demoBtn);
  melodyMeasuresEl.classList.add('measure-flash');
  window.setTimeout(() => melodyMeasuresEl.classList.remove('measure-flash'), 220);

  showFeedback(`Loaded demo melody: ${chosen.title}`, 'success');
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
    tr.innerHTML =
      `<th>${src}</th>` +
      states.map(dst => `<td>${transition_probs[src][dst].toFixed(3)}</td>`).join('');
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);

  matrixEl.innerHTML = '';
  matrixEl.appendChild(table);
}

async function refreshModel() {
  try {
    const res = await fetch('/api/model');
    const data = await res.json();
    modelVersionEl.textContent = String(data.model_version);
    renderMatrixTable(data.transition_probs);
  } catch (err) {
    console.error(err);
    showFeedback('Unable to refresh model status.', 'warn');
  }
}

function setupButtons() {
  endMeasureBtn.addEventListener('click', endMeasure);
  undoBtn.addEventListener('click', undoLast);

  clearBtn.addEventListener('click', () => {
    measures = [];
    currentMeasure = [];
    latestComparison = null;
    resultSectionEl.classList.add('hidden');
    renderMelody();
    flashElement(clearBtn);
    showFeedback('Cleared melody input.', 'info');
  });

  demoBtn.addEventListener('click', loadDemoMelody);
  generateBtn.addEventListener('click', generateVariations);
  playABtn.addEventListener('click', () => playVariation('A'));
  playBBtn.addEventListener('click', () => playVariation('B'));
  voteABtn.addEventListener('click', () => vote('A'));
  voteBBtn.addEventListener('click', () => vote('B'));
}

function setupKeyboardInput() {
  const keyMap = {
    a: 'C',
    s: 'D',
    d: 'E',
    f: 'F',
    g: 'G',
    h: 'A',
    j: 'B',
    k: 'C_HIGH',
    l: 'D_HIGH',
    ';': 'E_HIGH',
    "'": 'F_HIGH'
  };

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
showFeedback('Ready. Click piano keys or load a random demo melody.', 'info');
refreshModel();