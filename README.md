# Rhythm Isomers

**Generate distinct rhythmic sequences with comparable structural complexity.**

Rhythm Isomers is a Python command-line tool that generates multiple rhythmic patterns using a fixed set of permitted note durations. Each sequence has the **same total duration, number of onsets, and multiset of note values**, but a different temporal ordering. The results are exported as **MIDI**, **WAV** (synthetic claves / wooden sticks), and a **CSV** summary.

The generator uses exact rational arithmetic for musical time and a heuristic selection strategy to keep simple rhythmic-complexity indicators as close as possible across the generated examples.

## Requirements

- Python 3.9 or newer
- NumPy
- Mido

Install:

~~~bash
git clone https://github.com/fv-c/rhythm-isomers.git
cd rhythm-isomers
python -m pip install -r requirements.txt
~~~

## Quick start

Generate 10 sequences lasting two bars of 4/4, at 100 quarter-note BPM, using quarter notes, eighth notes, and sixteenth notes:

~~~bash
python genera_ritmi_legnetti.py --n 10 --durata 2 --bpm 100 --durate 1/4 1/8 1/16 --out ritmi --seed 42
~~~

Generate 5 sequences lasting one and a half bars:

~~~bash
python genera_ritmi_legnetti.py --n 5 --durata 3/2 --bpm 120 --durate 1/4 1/8 1/16 --out ritmi_3_2 --seed 42
~~~

### Musical duration convention

All durations are **fractions of a whole note (semibreve)**, with a fixed 4/4 reference meter.

| Value | Meaning |
| --- | --- |
| 1 | One 4/4 bar |
| 2 | Two 4/4 bars |
| 3/2 | One and a half 4/4 bars |
| 1/4 | Quarter note |
| 1/8 | Eighth note |
| 1/16 | Sixteenth note |

BPM refers to the **quarter-note pulse**.

## Command-line arguments

| Argument | Required | Description |
| --- | --- | --- |
| --n | Yes | Number of distinct sequences to generate (positive integer) |
| --durata | Yes | Total musical duration as a positive rational number |
| --bpm | Yes | Quarter-note BPM, greater than zero and at most 1000 |
| --durate | Yes | Space-separated list of allowed positive rational durations |
| --out | No | Output directory (default: ritmi) |
| --seed | No | Random seed for reproducibility (default: 42) |

Examples of accepted rational inputs: 2, 3/2, 1/4, 3/16.

## Output

For each generated sequence, the tool writes:

~~~text
ritmi/
├── sequenza_001.mid
├── sequenza_001.wav
├── sequenza_002.mid
├── sequenza_002.wav
├── ...
└── sequenze.csv
~~~

- **MIDI:** 4/4 meter, explicit tempo, percussion channel 10 (zero-based channel 9), General MIDI note 75 (Claves).
- **WAV:** mono, 44.1 kHz, 16-bit PCM. Each onset triggers a short, procedurally synthesized wooden-stick sound (inharmonic damped resonances and a noise transient). No external samples or SoundFonts are needed.
- **CSV:** one row per sequence containing the ordered rational durations and two complexity indicators.

The WAV renderer and MIDI exporter are independent: the MIDI timbre is determined by the receiving synthesizer, whereas the WAV uses the built-in procedural sound.

## How complexity is controlled

1. **Exact fit:** a multiset of allowed note values is chosen so that its sum equals the requested musical duration exactly, using Python's Fraction arithmetic.
2. **Equal inventory:** every generated sequence is a unique permutation of that same multiset. Consequently, all sequences have the same number of events and the same distribution of durations.
3. **Comparable rhythmic profiles:** candidates are assessed by two indicators:
   - **Off-beat onsets:** number of attacks that do not coincide with a quarter-note grid position.
   - **Duration changes:** number of adjacent event pairs having different durations.
4. **Diversity:** among comparably complex candidates, the algorithm favors different event orderings.

When a sufficiently large candidate group is available, the two indicators may match exactly. Otherwise, the generator selects the closest available profiles. This is a **structural heuristic**, not a claim of identical perceptual or cognitive difficulty.

The patterns contain only note attacks: no rests, pitches, dynamics, or expressive timing are generated in this version. Requests for more unique patterns than the allowed durations can support are rejected.

## Reproducibility and limitations

- Use the same seed and parameters to reproduce a run in the same Python environment.
- With larger search spaces, candidate selection uses bounded enumeration and randomized sampling; it does not guarantee a global optimum.
- Very fine rational divisions may exceed the allowed internal search or MIDI tick resolution and produce an explanatory error.
- The synthetic claves sound is a procedural approximation, not a sampled acoustic recording.

## License

Distributed under the **GNU General Public License v3.0**, as specified in the existing [LICENSE](LICENSE) file.
