# Rhythm Isomers

**Generate distinct rhythmic sequences with comparable structural complexity.**

Rhythm Isomers is a Python command-line tool that generates multiple rhythmic patterns using a fixed set of permitted note durations. Each sequence has the **same total duration, number of onsets, and multiset of note values**, but a different temporal ordering. The results are exported as **MIDI**, **WAV** (direct playback of recorded percussion samples), and a **CSV** summary.

The generator uses exact rational arithmetic for musical time and a heuristic selection strategy to keep simple rhythmic-complexity indicators as close as possible across the generated examples.

## Requirements

- Python 3.10 or newer; **Python 3.12, 64-bit is recommended on Windows**
- NumPy
- Mido
- SciPy

SamuelGremaud's CC0 wooden-claves recording is included in `samples/`. Generation works offline immediately after installing the Python requirements. No SoundFont, audio device, external player, FFmpeg, API key, or Freesound account is required to run the repository.

### Windows (PowerShell or Command Prompt)

Install Python 3.12, then run:

~~~powershell
git clone https://github.com/fv-c/rhythm-isomers.git
cd rhythm-isomers
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.venv\Scripts\python.exe genera_ritmi_legnetti.py --n 10 --durata 2 --bpm 100 --durate 1/4 1/8 1/16 --out ritmi --seed 42
~~~

Python 3.12 has prebuilt wheels for all dependencies on Windows x64. No compiler, separate DLL installation or PowerShell activation script is needed.

### macOS / Linux

~~~bash
git clone https://github.com/fv-c/rhythm-isomers.git
cd rhythm-isomers
python3 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
~~~

Use `.venv/bin/python` (macOS/Linux) or `.venv\Scripts\python.exe` (Windows) in place of `python` in the examples below. The script retains its original filename, `genera_ritmi_legnetti.py`, for command-line compatibility.

The bundled sample path is resolved relative to the script, so running from another directory works too. Use quotes around custom paths containing spaces.

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
| --sample | No | Path to a WAV recording of one percussion strike (default: SamuelGremaud's bundled `samples/claves.wav`) |
| --gain | No | Fixed linear sample gain, finite and greater than zero (default: 1.0); reduce it if overlapping hits would clip |
| --nota-midi | No | GM percussion note, 35–81, for MIDI only (default: 75, Claves); does not change the WAV sample |

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

- **MIDI:** 4/4 meter, explicit tempo, percussion channel 10 (zero-based channel 9), Standard Kit (program 0), General MIDI note **75 (Claves)** by default. `--nota-midi` selects an approximate GM instrument.
- **WAV:** mono, 44.1 kHz, 16-bit PCM. Each onset directly plays the selected recorded strike. The file retains the exact requested musical duration.
- **CSV:** one row per sequence containing the ordered rational durations and two complexity indicators.

### Sound: recorded claves

The default sample is one wooden-claves strike extracted from [SamuelGremaud's CLAVES recording](https://freesound.org/people/SamuelGremaud/sounds/517609/), made with a Zoom H4N Pro, and included as `samples/claves.wav`.

The included WAV is **decoded from the public high-quality MP3 preview**, not the original lossless download (which requires Freesound login). The microphone recording was converted to mono PCM16 at 44.1 kHz, with a fixed 0.5 preparation gain to prevent decoded MP3 peaks exceeding full scale. Source URLs, extraction boundaries, processing details and SHA-256 checksums are retained in [samples/SOURCES.json](samples/SOURCES.json).

Generate rhythms with the selected claves recording (no sample options needed):

~~~bash
python genera_ritmi_legnetti.py --n 10 --durata 2 --bpm 100 --durate 1/4 1/8 1/16 --out ritmi_claves
~~~

To use your own recording, add `--sample "path/to/hit.wav"`. Supported inputs are mono/stereo PCM WAV (8, 16, 24 or 32-bit) and floating-point WAV. Place the attack at the beginning of the file: leading silence is retained. Stereo is averaged to mono, and other sample rates are resampled without changing pitch. Missing, invalid, nonfinite or silent samples are rejected before output files are created.

Playback preserves the recorded attack, body and decay, with a 20 ms fade at each sample's end and an 8 ms fade at the file boundary. Strikes overlap naturally. The gain stays fixed across sequences: no pitch changes, random dynamics, per-sequence normalization, added reverb or synthesis. A mix that exceeds full scale raises an error instead of clipping; lower `--gain` for dense patterns.

**MIDI playback depends on the player:** MIDI stores attacks and an approximate GM instrument, not the recording. The WAV is the reference rendering.

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
- Each run uses one fixed sampled strike per instrument. The sound is sampled, but the performance has no human timing or dynamic variation.

## Tests

~~~bash
python -m unittest discover -s tests -v
~~~

All audio tests use the included recordings or local WAV fixtures; no downloads, credentials or audio hardware are required. Tests cover sample provenance, PCM/float formats, stereo downmixing, resampling without pitch changes, exact onset placement and WAV duration, clipping detection, smooth boundaries, and generation from another working directory with spaces and Unicode in paths. GitHub Actions is configured to run the full suite on Windows, macOS and Linux with Python 3.10 and 3.12, installing binary packages only.

## License

Distributed under the **GNU General Public License v3.0**, as specified in the existing [LICENSE](LICENSE) file.

The included recording is separately released under **CC0 1.0** by SamuelGremaud. See [samples/README.md](samples/README.md), [samples/SOURCES.json](samples/SOURCES.json) and [samples/CC0-1.0.txt](samples/CC0-1.0.txt).
