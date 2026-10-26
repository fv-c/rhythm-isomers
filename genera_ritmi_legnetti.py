#!/usr/bin/env python3
"""Genera n sequenze ritmiche distinte e di complessità simile.

Le durate sono espresse in frazioni di semibreve: in 4/4, 1 = una battuta,
1/4 = una semiminima, 1/8 = una croma, 1/16 = una semicroma.

Installazione: pip install -r requirements.txt
Esempio:
    python genera_ritmi_legnetti.py --n 10 --durata 2 --bpm 100 \
        --durate 1/4 1/8 1/16 --out ritmi --seed 42
"""

import argparse
import csv
import math
import random
import sys
import wave
from functools import lru_cache
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import mido
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


DEFAULT_SAMPLE = Path(__file__).resolve().parent / "samples" / "claves.wav"


def numero_permutazioni(conteggi, limite):
    """Numero di permutazioni del multinsieme, eventualmente troncato a limite."""
    risultato = 1
    totale = 0
    for k in conteggi:
        risultato *= math.comb(totale + k, k)
        totale += k
        if risultato >= limite:
            return limite
    return risultato


def scegli_profilo(durata_totale, durate, n, rng):
    """Trova conteggi di durate con somma esatta e >= n permutazioni.

    Fra i profili possibili privilegia una distribuzione equilibrata delle
    durate: tutte le sequenze useranno esattamente questo stesso multinsieme.
    """
    scala = math.lcm(durata_totale.denominator, *(d.denominator for d in durate))
    totale = int(durata_totale * scala)
    valori = [int(d * scala) for d in durate]
    divisore = math.gcd(totale, *valori)
    totale //= divisore
    valori = [v // divisore for v in valori]

    if totale > 200_000:
        raise ValueError("Suddivisione razionale troppo fine: più di 200.000 unità.")

    # Verifica che sia possibile riempire ESATTAMENTE la durata richiesta.
    raggiungibile = [False] * (totale + 1)
    raggiungibile[0] = True
    for t in range(1, totale + 1):
        raggiungibile[t] = any(t >= v and raggiungibile[t - v] for v in valori)
    if not raggiungibile[totale]:
        raise ValueError("Nessuna combinazione delle durate ammesse somma alla durata totale.")

    # Verifica rapida: n non può superare il numero totale di sequenze ordinate.
    modi = [0] * (totale + 1)
    modi[0] = 1
    for t in range(1, totale + 1):
        modi[t] = min(n, sum(modi[t - v] for v in valori if t >= v))
    if modi[totale] < n:
        raise ValueError(f"Esistono solo {modi[totale]} sequenze distinte con questi parametri.")

    migliore = None
    migliore_score = None
    budget = 200_000
    visite = 0
    esaurito = False

    def considera(conteggi):
        nonlocal migliore, migliore_score
        if numero_permutazioni(conteggi, n) < n:
            return
        num_note = sum(conteggi)
        probabilita = [k / num_note for k in conteggi if k]
        entropia = -sum(p * math.log(p) for p in probabilita)
        # Entropia prima, poi copertura dei valori consentiti.
        score = (entropia, len(probabilita), rng.random())
        if migliore_score is None or score > migliore_score:
            migliore = tuple(conteggi)
            migliore_score = score

    # Enumerazione con un budget per non esplodere con liste molto grandi.
    suffissi_gcd = [0] * len(valori)
    corrente = 0
    for i in range(len(valori) - 1, -1, -1):
        corrente = math.gcd(corrente, valori[i])
        suffissi_gcd[i] = corrente

    def visita(indice, residuo, conteggi):
        nonlocal visite, esaurito
        if visite >= budget:
            esaurito = True
            return
        visite += 1
        if residuo % suffissi_gcd[indice] != 0:
            return
        if indice == len(valori) - 1:
            if residuo % valori[indice] == 0:
                considera(conteggi + [residuo // valori[indice]])
            return
        v = valori[indice]
        for k in range(residuo // v, -1, -1):
            visita(indice + 1, residuo - k * v, conteggi + [k])
            if esaurito:
                return

    visita(0, totale, [])

    # Ricerca complementare randomizzata, utile con molte durate ammesse.
    if esaurito or migliore is None:
        for _ in range(3000):
            residuo = totale
            conteggi = Counter()
            while residuo:
                scelte = [i for i, v in enumerate(valori)
                           if v <= residuo and raggiungibile[residuo - v]]
                i = rng.choice(scelte)
                conteggi[i] += 1
                residuo -= valori[i]
            considera([conteggi[i] for i in range(len(valori))])

    if migliore is None:
        raise ValueError(
            "Non è stato trovato un multinsieme che ammetta n permutazioni "
            "distinte. Ridurre n oppure ampliare le durate consentite."
        )
    return [d for d, k in zip(durate, migliore) for _ in range(k)]


def permutazioni_uniche(elementi):
    """Enumera permutazioni senza duplicati, per problemi piccoli."""
    contatore = Counter(elementi)
    ordine = sorted(contatore)
    lunghezza = len(elementi)
    corrente = []

    def ricorsione():
        if len(corrente) == lunghezza:
            yield tuple(corrente)
            return
        for d in ordine:
            if contatore[d]:
                contatore[d] -= 1
                corrente.append(d)
                yield from ricorsione()
                corrente.pop()
                contatore[d] += 1

    yield from ricorsione()


def complessita(sequenza):
    """Due indicatori: attacchi fuori dai quarti e cambi di durata."""
    posizione = Fraction(0)
    fuori_battito = 0
    for durata in sequenza:
        if (posizione * 4).denominator != 1:
            fuori_battito += 1
        posizione += durata
    cambi = sum(a != b for a, b in zip(sequenza, sequenza[1:]))
    return fuori_battito, cambi


def genera_sequenze(n, durata_totale, durate, seed):
    if n < 1 or durata_totale <= 0 or any(d <= 0 for d in durate):
        raise ValueError("n deve essere positivo e tutte le durate devono essere > 0.")

    rng = random.Random(seed)
    durate = sorted({d for d in durate if d <= durata_totale}, reverse=True)
    if not durate:
        raise ValueError("Nessuna durata ammessa è <= alla durata totale.")

    profilo = scegli_profilo(durata_totale, durate, n, rng)
    numero = numero_permutazioni(Counter(profilo).values(), max(15_001, n))

    if numero <= 15_000:
        candidati = list(permutazioni_uniche(profilo))
    else:
        obiettivo = max(n, min(20_000, max(350, n * 35)))
        candidati_set = set()
        tentativi = 0
        while len(candidati_set) < obiettivo and tentativi < obiettivo * 35:
            tentativi += 1
            permutazione = profilo.copy()
            rng.shuffle(permutazione)
            candidati_set.add(tuple(permutazione))
        candidati = list(candidati_set)

    if len(candidati) < n:
        raise RuntimeError("Non sono state campionate abbastanza permutazioni distinte.")

    # Preferisci sequenze con IDENTICI valori dei due indicatori; se n è
    # elevato, estendi il gruppo agli indicatori più vicini possibili.
    gruppi = defaultdict(list)
    for seq in candidati:
        gruppi[complessita(seq)].append(seq)
    riferimento = max(gruppi, key=lambda k: (len(gruppi[k]), -sum(k)))

    def distanza_complessita(seq):
        a, b = complessita(seq)
        return abs(a - riferimento[0]) + abs(b - riferimento[1])

    distanze = sorted(distanza_complessita(seq) for seq in candidati)
    soglia = distanze[n - 1]
    candidati = [seq for seq in candidati if distanza_complessita(seq) <= soglia]
    rng.shuffle(candidati)

    # Massimizza la diversità d'ordine senza alterare la complessità.
    # La distanza minima da ogni sequenza già scelta viene aggiornata a ogni giro:
    # costo O(n * candidati * eventi), invece di O(n^2 * candidati * eventi).
    if n <= 100:
        scelti = []
        disponibili = set(range(len(candidati)))
        distanze_minime = [len(profilo)] * len(candidati)
        while len(scelti) < n:
            indice = max(disponibili, key=lambda i: distanze_minime[i])
            nuovo = candidati[indice]
            scelti.append(nuovo)
            disponibili.remove(indice)
            for i in disponibili:
                d = sum(a != b for a, b in zip(candidati[i], nuovo))
                if d < distanze_minime[i]:
                    distanze_minime[i] = d
    else:
        scelti = candidati[:n]

    assert len(set(scelti)) == n
    assert all(sum(s) == durata_totale for s in scelti)
    return scelti


def scrivi_midi(sequenza, durata_totale, bpm, destinazione, nota_midi=75):
    if not 35 <= nota_midi <= 81:
        raise ValueError("La nota della percussione GM deve essere fra 35 e 81.")
    # Risoluzione MIDI sufficiente anche per suddivisioni irregolari.
    ppq = math.lcm(960, *((4 * d).denominator for d in sequenza))
    if ppq > 32_767:
        raise ValueError("Risoluzione MIDI troppo alta: denominatori incompatibili.")

    midi = mido.MidiFile(type=0, ticks_per_beat=ppq)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=f"GM percussion {nota_midi}", time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    track.append(mido.Message("program_change", channel=9, program=0, time=0))

    eventi = []
    posizione = Fraction(0)
    for durata in sequenza:
        inizio = int(4 * posizione * ppq)
        passo = int(4 * durata * ppq)
        fine = inizio + max(1, min(ppq // 10, passo // 2))
        # Canale 10 (channel=9); 75 = Claves, 41 = Low Floor Tom.
        eventi.append((inizio, 1, mido.Message("note_on", channel=9, note=nota_midi,
                                                 velocity=100, time=0)))
        eventi.append((fine, 0, mido.Message("note_off", channel=9, note=nota_midi,
                                             velocity=0, time=0)))
        posizione += durata

    precedente = 0
    for tick, _, messaggio in sorted(eventi, key=lambda x: (x[0], x[1])):
        messaggio.time = tick - precedente
        track.append(messaggio)
        precedente = tick
    fine_brano = int(durata_totale * 4 * ppq)
    track.append(mido.MetaMessage("end_of_track", time=fine_brano - precedente))
    midi.save(destinazione)


def sfuma_coda(audio, sample_rate, durata=0.020):
    """Porta la coda a zero in-place con una curva a coseno e pendenza nulla."""
    campioni = min(len(audio), max(1, round(durata * sample_rate)))
    if campioni == 1:
        audio[-1] = 0.0
    elif campioni > 1:
        fase = np.linspace(0.0, np.pi, campioni)
        audio[-campioni:] *= 0.5 * (1.0 + np.cos(fase))


@lru_cache(maxsize=8)
def carica_sample(sample, sample_rate=44_100):
    """Carica un colpo WAV mono/stereo e converte il sample rate senza reintonarlo."""
    path = Path(sample).expanduser().resolve()
    if not path.is_file():
        raise ValueError(
            f"Sample non trovato: {path}. Ripristinare la cartella samples "
            "oppure specificare --sample con un colpo WAV."
        )
    try:
        rate_originale, dati = wavfile.read(str(path))
    except (ValueError, EOFError) as errore:
        raise ValueError(f"Sample WAV non valido: {path}: {errore}") from errore
    if not dati.size or dati.ndim not in (1, 2):
        raise ValueError("Il sample WAV deve contenere audio mono o stereo.")
    if dati.ndim == 2 and dati.shape[1] != 2:
        raise ValueError("Il sample WAV deve contenere audio mono o stereo.")
    if sample_rate <= 0 or rate_originale <= 0:
        raise ValueError("Il sample rate deve essere positivo.")

    colpo = dati.astype(np.float64)
    if dati.dtype.kind == "u":
        centro = 2 ** (8 * dati.dtype.itemsize - 1)
        colpo = (colpo - centro) / centro
    elif dati.dtype.kind == "i":
        # SciPy restituisce il PCM 24-bit allineato a sinistra in int32.
        colpo /= 2 ** (8 * dati.dtype.itemsize - 1)
    elif dati.dtype.kind != "f":
        raise ValueError("Formato WAV non supportato: usare PCM o floating point.")
    if not np.all(np.isfinite(colpo)):
        raise ValueError("Il sample WAV contiene valori NaN o infiniti.")
    if dati.ndim == 2:
        colpo = colpo.mean(axis=1)
    if np.max(np.abs(colpo)) < 1e-12:
        raise ValueError("Il sample WAV è silenzioso dopo la conversione mono.")

    if rate_originale != sample_rate:
        divisore = math.gcd(rate_originale, sample_rate)
        lunghezza = round(len(colpo) * sample_rate / rate_originale)
        colpo = resample_poly(colpo, sample_rate // divisore,
                              rate_originale // divisore)[:lunghezza]
    if not len(colpo):
        raise ValueError("Il sample WAV è troppo corto per il sample rate richiesto.")
    sfuma_coda(colpo, sample_rate)
    colpo.setflags(write=False)
    return colpo


def scrivi_wav(sequenza, durata_totale, bpm, destinazione, seed=None,
               sample_rate=44_100, sample=DEFAULT_SAMPLE, gain=1.0):
    # seed è mantenuto per compatibilità; i campioni non vengono randomizzati.
    if not math.isfinite(gain) or gain <= 0:
        raise ValueError("--gain deve essere un numero finito > 0.")
    colpo = carica_sample(str(Path(sample).expanduser().resolve()), sample_rate)
    # Quattro semiminime per semibreve: durata in secondi = 4 * 60 / BPM.
    durata_secondi = float(durata_totale) * 4 * 60 / bpm
    campioni = round(durata_secondi * sample_rate)
    audio = np.zeros(campioni, dtype=np.float64)

    posizione = Fraction(0)
    for durata in sequenza:
        inizio = round(float(posizione) * 4 * 60 / bpm * sample_rate)
        fine = min(campioni, inizio + len(colpo))
        if fine > inizio:
            audio[inizio:fine] += gain * colpo[:fine - inizio]
        posizione += durata

    # Evita discontinuità alla fine del WAV senza prolungare la durata musicale.
    sfuma_coda(audio, sample_rate, durata=0.008)

    # Guadagno fisso e nessuna normalizzazione diversa per ciascuna sequenza.
    if np.max(np.abs(audio), initial=0) > 1:
        raise ValueError("Il mix supera 0 dBFS: ridurre --gain per evitare distorsione.")
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(destinazione), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def main():
    # I terminali Windows usano Unicode; le pipe possono usare ancora una
    # code page locale. Un percorso Unicode non deve interrompere l'export.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, required=True, help="Numero di sequenze")
    parser.add_argument("--durata", type=Fraction, required=True,
                        help="Durata totale in semibrevi: 2 = due battute da 4/4")
    parser.add_argument("--bpm", type=float, required=True, help="BPM della semiminima")
    parser.add_argument("--durate", type=Fraction, nargs="+", required=True,
                        help="Durate ammesse, es.: 1/4 1/8 1/16")
    parser.add_argument("--out", type=Path, default=Path("ritmi"),
                        help="Cartella di destinazione")
    parser.add_argument("--seed", type=int, default=42,
                        help="Seme per ottenere sempre gli stessi risultati")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE,
                        help="Colpo WAV mono/stereo (default: claves di SamuelGremaud, Freesound)")
    parser.add_argument("--gain", type=float, default=1.0,
                        help="Guadagno fisso del campione, senza normalizzazione (default: 1.0)")
    parser.add_argument("--nota-midi", type=int, default=75,
                        help="Nota GM 35–81 solo nel MIDI; il WAV usa sempre --sample")
    args = parser.parse_args()

    if not 0 < args.bpm <= 1000:
        parser.error("--bpm deve essere > 0 e <= 1000")
    if args.n < 1:
        parser.error("--n deve essere >= 1")
    if not 35 <= args.nota_midi <= 81:
        parser.error("--nota-midi deve essere fra 35 e 81")
    if not math.isfinite(args.gain) or args.gain <= 0:
        parser.error("--gain deve essere un numero finito > 0")

    try:
        sequenze = genera_sequenze(args.n, args.durata, args.durate, args.seed)
        # Verifica il campione prima di creare file di uscita parziali.
        carica_sample(str(args.sample.expanduser().resolve()), 44_100)
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "sequenze.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["sequenza", "durate", "attacchi_fuori_quarto", "cambi_durata"])
            for i, seq in enumerate(sequenze, start=1):
                base = args.out / f"sequenza_{i:03d}"
                scrivi_midi(seq, args.durata, args.bpm, base.with_suffix(".mid"),
                            nota_midi=args.nota_midi)
                scrivi_wav(seq, args.durata, args.bpm,
                           base.with_suffix(".wav"), seed=args.seed + i,
                           sample=args.sample, gain=args.gain)
                indicatori = complessita(seq)
                writer.writerow([i, " ".join(str(d) for d in seq), *indicatori])
                print(f"{base.name}: {' '.join(map(str, seq))}  | complessità={indicatori}")
    except (OSError, ValueError, RuntimeError) as errore:
        parser.error(str(errore))

    print(f"\nCreati {args.n} MIDI + {args.n} WAV + sequenze.csv in {args.out.resolve()}")


if __name__ == "__main__":
    main()
