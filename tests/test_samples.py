"""Regression tests for direct WAV samples, timing and portable CLI use."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from fractions import Fraction
from pathlib import Path

import mido
import numpy as np
from scipy.io import wavfile

from genera_ritmi_legnetti import DEFAULT_SAMPLE, carica_sample, scrivi_midi, scrivi_wav


ROOT = Path(__file__).resolve().parents[1]


def leggi_wav(path):
    with wave.open(str(path), "rb") as wav:
        info = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(),
                wav.getnframes())
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    return info, audio


class SampleTests(unittest.TestCase):
    def test_bundled_recordings_match_provenance_checksums(self):
        records = json.loads((ROOT / "samples" / "SOURCES.json").read_text())
        self.assertEqual({record["file"] for record in records}, {"claves.wav"})
        for record in records:
            with self.subTest(file=record["file"]):
                source = ROOT / "samples" / record["file"]
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                                 record["sha256"])
                self.assertEqual(record["license"], "CC0-1.0")
                hit = carica_sample(str(source))
                self.assertFalse(hit.flags.writeable)
                self.assertGreater(np.max(np.abs(hit)), 0.05)
                self.assertEqual(hit[-1], 0)

    def test_missing_invalid_empty_and_silent_samples_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "hit.wav"
            with self.assertRaisesRegex(ValueError, "--sample"):
                carica_sample(str(target))
            target.write_bytes(b"not a wave file")
            with self.assertRaisesRegex(ValueError, "WAV non valido"):
                carica_sample(str(target))
            wavfile.write(target, 44100, np.zeros(0, dtype=np.int16))
            with self.assertRaisesRegex(ValueError, "contenere audio"):
                carica_sample(str(target))
            wavfile.write(target, 44100, np.zeros(100, dtype=np.int16))
            with self.assertRaisesRegex(ValueError, "silenzioso"):
                carica_sample(str(target))

    def test_pcm_and_float_formats_have_consistent_gain(self):
        with tempfile.TemporaryDirectory() as tmp:
            for dtype, values in (
                (np.uint8, [192] * 1000),
                (np.int16, [16384] * 1000),
                (np.int32, [1073741824] * 1000),
                (np.float32, [0.5] * 1000),
                (np.float64, [0.5] * 1000),
            ):
                with self.subTest(dtype=dtype):
                    target = Path(tmp) / f"{np.dtype(dtype).name}.wav"
                    wavfile.write(target, 44100, np.array(values, dtype=dtype))
                    hit = carica_sample(str(target))
                    self.assertEqual(hit[0], 0.5)
                    self.assertEqual(hit[-1], 0)

    def test_24_bit_pcm_is_scaled_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "24bit.wav"
            with wave.open(str(target), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(3)
                wav.setframerate(44100)
                wav.writeframes(b"\x00\x00\x40" * 1000)
            self.assertEqual(carica_sample(str(target))[0], 0.5)

    def test_stereo_is_downmixed_without_doubling_gain(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "stereo.wav"
            wavfile.write(target, 44100, np.tile([0.25, 0.75], (1000, 1)).astype(np.float32))
            hit = carica_sample(str(target))
            self.assertEqual(hit.ndim, 1)
            self.assertEqual(hit[0], 0.5)

    def test_nonfinite_and_multichannel_samples_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for label, audio in (("nan", [0.0, np.nan]),
                                 ("inf", [0.0, np.inf]),
                                 ("surround", np.ones((1000, 6)))):
                target = Path(tmp) / f"{label}.wav"
                wavfile.write(target, 44100, np.asarray(audio, dtype=np.float32))
                with self.subTest(label=label), self.assertRaises(ValueError):
                    carica_sample(str(target))

    def test_resampling_preserves_pitch_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            for input_rate, output_rate in ((48000, 44100), (44100, 22050),
                                             (44100, 96000)):
                with self.subTest(input_rate=input_rate, output_rate=output_rate):
                    target = Path(tmp) / f"{input_rate}_{output_rate}.wav"
                    time = np.arange(input_rate) / input_rate
                    wavfile.write(target, input_rate,
                                  (0.5 * np.sin(2 * np.pi * 1000 * time)).astype(np.float32))
                    hit = carica_sample(str(target), output_rate)
                    self.assertEqual(len(hit), output_rate)
                    peak = np.argmax(np.abs(np.fft.rfft(hit)))
                    self.assertEqual(peak, 1000)
                    self.assertEqual(hit[-1], 0)

    def test_onsets_and_amplitude_are_preserved_without_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "impulse.wav"
            impulse = np.zeros(2000, dtype=np.float32)
            impulse[0] = 0.5
            wavfile.write(sample, 44100, impulse)
            for gain, expected_level in ((0.5, 8191), (0.25, 4095)):
                target = Path(tmp) / f"{gain}.wav"
                scrivi_wav([Fraction(1, 4)] * 4, Fraction(1), 120, target,
                           sample=sample, gain=gain)
                info, audio = leggi_wav(target)
                self.assertEqual(info, (44100, 1, 2, 88200))
                np.testing.assert_array_equal(np.flatnonzero(audio),
                                              [0, 22050, 44100, 66150])
                np.testing.assert_array_equal(audio[audio != 0], [expected_level] * 4)

    def test_wav_duration_and_boundary_fade_at_multiple_rates(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rate in (22050, 44100, 48000, 96000):
                target = Path(tmp) / f"{rate}.wav"
                scrivi_wav([Fraction(1, 4)], Fraction(1, 4), 1000,
                           target, sample_rate=rate)
                info, audio = leggi_wav(target)
                self.assertEqual(info, (rate, 1, 2, round(0.06 * rate)))
                self.assertGreater(np.max(np.abs(audio)), 500)
                self.assertEqual(audio[-1], 0)
                self.assertEqual(audio[-2], 0)

    def test_clipping_is_rejected_before_writing_the_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.wav"
            with self.assertRaisesRegex(ValueError, "ridurre --gain"):
                scrivi_wav([Fraction(1, 4)], Fraction(1, 4), 120,
                           target, gain=100)
            self.assertFalse(target.exists())

    def test_seed_does_not_randomize_the_recorded_strike(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "first.wav", Path(tmp) / "second.wav"
            for target, seed in ((first, 42), (second, 99)):
                scrivi_wav([Fraction(1, 4)] * 4, Fraction(1), 120, target, seed=seed)
            self.assertEqual(first.read_bytes(), second.read_bytes())


class MidiAndCliTests(unittest.TestCase):
    def test_midi_keeps_note_selection_and_exact_musical_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            for note in (41, 64, 76):
                target = Path(tmp) / f"{note}.mid"
                scrivi_midi([Fraction(1, 4)] * 4, Fraction(1), 120, target, nota_midi=note)
                midi = mido.MidiFile(target)
                onsets = [msg for track in midi.tracks for msg in track
                          if msg.type == "note_on" and msg.velocity > 0]
                self.assertEqual(len(onsets), 4)
                self.assertTrue(all(msg.channel == 9 and msg.note == note
                                    for msg in onsets))
                self.assertAlmostEqual(midi.length, 2.0, places=5)

    def test_invalid_sample_fails_before_creating_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            result = subprocess.run(
                [sys.executable, str(ROOT / "genera_ritmi_legnetti.py"),
                 "--n", "1", "--durata", "1/4", "--bpm", "120", "--durate", "1/4",
                 "--sample", str(Path(tmp) / "missing.wav"), "--out", str(out)],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--sample", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(out.exists())

    def test_custom_sample_and_unicode_paths_work_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "percussioni è 漢字"
            directory.mkdir()
            sample = directory / "colpo reale.wav"
            shutil.copyfile(DEFAULT_SAMPLE, sample)
            out = directory / "uscita audio"
            result = subprocess.run(
                [sys.executable, str(ROOT / "genera_ritmi_legnetti.py"),
                 "--n", "2", "--durata", "1", "--bpm", "120",
                 "--durate", "1/4", "1/8", "--sample", str(sample), "--out", str(out)],
                cwd=tmp, capture_output=True, text=True,
                env={**os.environ, "PYTHONIOENCODING": "ascii"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(out.glob("*.wav"))), 2)
            self.assertEqual(len(list(out.glob("*.mid"))), 2)
            self.assertTrue((out / "sequenze.csv").is_file())
            for target in out.glob("*.wav"):
                info, audio = leggi_wav(target)
                self.assertEqual(info, (44100, 1, 2, 88200))
                self.assertGreater(np.max(np.abs(audio)), 500)

    def test_bundled_sample_is_found_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "genera_ritmi_legnetti.py"),
                 "--n", "1", "--durata", "1/4", "--bpm", "120", "--durate", "1/4"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(tmp) / "ritmi" / "sequenza_001.wav").is_file())


if __name__ == "__main__":
    unittest.main()
