# Recorded claves

This is an acoustic recording from Freesound, released by SamuelGremaud under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
The license text is retained in [CC0-1.0.txt](CC0-1.0.txt).

| File | Author | Source |
| --- | --- | --- |
| `claves.wav` (default) | SamuelGremaud | [CLAVES, 517609](https://freesound.org/people/SamuelGremaud/sounds/517609/) |

The bundled PCM16 mono WAV was decoded from the **public HQ MP3 preview**.
It is not the original lossless file, whose Freesound download requires
login. No login or network access is required to play the bundled sample.

Preparation used FFmpeg to decode/downmix/resample to 44.1 kHz and a fixed
0.5 gain, avoiding clipping from decoded MP3 overshoots. The first claves
strike was extracted. No EQ, denoising, normalization, pitch shift or time
stretching was added.

[SOURCES.json](SOURCES.json) records source pages, exact preview URLs, source
and derived-file hashes, extraction boundaries, gain and format information.
FFmpeg was used only to prepare this asset; it is not a runtime dependency.

The player adds a 20 ms sample-tail fade and an 8 ms file-boundary fade,
without extending the requested musical duration. A custom WAV can be selected
with `--sample`; a downloaded original can therefore replace a preview later.
