"""Regression tests for the Pelle grave synthesis and MIDI export."""

import tempfile
import unittest
import wave
from fractions import Fraction
from pathlib import Path

import mido
import numpy as np

from genera_ritmi_legnetti import colpo_di_pelle_grave, scrivi_midi, scrivi_wav


class PelleGraveTests(unittest.TestCase):
    def test_hit_is_deterministic_and_low(self):
        first = colpo_di_pelle_grave(44_100, np.random.default_rng(123))
        second = colpo_di_pelle_grave(44_100, np.random.default_rng(123))
        np.testing.assert_array_equal(first, second)
        self.assertEqual(len(first), round(0.46 * 44_100))
        self.assertGreater(np.max(np.abs(first)), 0.1)
        self.assertLess(np.max(np.abs(first)), 1.0)

        # Membrane resonance must dominate high-frequency attack noise.
        frequencies = np.fft.rfftfreq(len(first), d=1 / 44_100)
        energy = np.abs(np.fft.rfft(first)) ** 2
        self.assertGreater(energy[frequencies < 500].sum(),
                           5 * energy[frequencies > 3000].sum())

    def test_hit_tail_reaches_silence_without_a_step(self):
        for sample_rate in (22_050, 44_100, 48_000, 96_000):
            for seed in (42, 123):
                with self.subTest(sample_rate=sample_rate, seed=seed):
                    hit = colpo_di_pelle_grave(
                        sample_rate, np.random.default_rng(seed))
                    self.assertEqual(len(hit), round(0.46 * sample_rate))
                    self.assertEqual(hit[-1], 0.0)
                    # The transition to silence must fall below one PCM step.
                    self.assertLess(abs(hit[-2]), 1 / 32767)

    def test_midi_uses_low_floor_tom(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'test.mid'
            scrivi_midi([Fraction(1, 4)] * 4, Fraction(1), 120, target)
            midi = mido.MidiFile(target)
            onsets = [msg for track in midi.tracks for msg in track
                      if msg.type == 'note_on' and msg.velocity > 0]
            self.assertEqual(len(onsets), 4)
            self.assertTrue(all(msg.channel == 9 and msg.note == 41
                                for msg in onsets))
            self.assertAlmostEqual(midi.length, 2.0, places=5)

    def test_wav_keeps_requested_musical_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'test.wav'
            scrivi_wav([Fraction(1, 4)] * 4, Fraction(1), 120, target, seed=123)
            with wave.open(str(target), 'rb') as wav:
                self.assertEqual(wav.getframerate(), 44_100)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getnframes(), 2 * 44_100)
                data = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
            self.assertGreater(np.max(np.abs(data)), 500)
            self.assertEqual(data[-1], 0)

    def test_wav_internal_hit_tails_reach_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'test.wav'
            scrivi_wav([Fraction(1, 2)] * 2, Fraction(1), 120,
                       target, seed=123)
            with wave.open(str(target), 'rb') as wav:
                sample_rate = wav.getframerate()
                data = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
            hit_length = round(0.46 * sample_rate)
            for onset in (0, sample_rate):
                end = onset + hit_length
                self.assertEqual(data[end - 2], 0)
                self.assertEqual(data[end - 1], 0)
                self.assertTrue(np.all(data[end:onset + sample_rate] == 0))

    def test_wav_smoothly_releases_a_truncated_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'test.wav'
            scrivi_wav([Fraction(1, 4)], Fraction(1, 4), 1000,
                       target, seed=123)
            with wave.open(str(target), 'rb') as wav:
                self.assertEqual(wav.getnframes(), round(0.06 * 44_100))
                data = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
            self.assertEqual(data[-1], 0)
            self.assertEqual(data[-2], 0)


if __name__ == '__main__':
    unittest.main()
