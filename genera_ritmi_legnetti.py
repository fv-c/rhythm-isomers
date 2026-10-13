#!/usr/bin/env python3
"""Genera n sequenze ritmiche distinte e di complessità simile.

Le durate sono espresse in frazioni di semibreve: in 4/4, 1 = una battuta,
1/4 = una semiminima, 1/8 = una croma, 1/16 = una semicroma.

Richiede: pip install numpy mido scipy
Esempio:
    python genera_ritmi_legnetti.py --n 10 --durata 2 --bpm 100 \
        --durate 1/4 1/8 1/16 --out ritmi --seed 42
"""

import argparse
import csv
import math
import random
import wave
from functools import lru_cache
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import mido
import numpy as np
from scipy.signal import butter, sosfilt


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


def scrivi_midi(sequenza, durata_totale, bpm, destinazione):
    # Risoluzione MIDI sufficiente anche per suddivisioni irregolari.
    ppq = math.lcm(960, *((4 * d).denominator for d in sequenza))
    if ppq > 32_767:
        raise ValueError("Risoluzione MIDI troppo alta: denominatori incompatibili.")

    midi = mido.MidiFile(type=0, ticks_per_beat=ppq)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Pelle grave", time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))

    eventi = []
    posizione = Fraction(0)
    for durata in sequenza:
        inizio = int(4 * posizione * ppq)
        passo = int(4 * durata * ppq)
        fine = inizio + max(1, min(ppq // 10, passo // 2))
        # Canale 10 (channel=9), nota GM 41: Low Floor Tom.
        # Il timbro MIDI dipende dal sintetizzatore e non coincide esattamente
        # con la sintesi WAV della pelle grave.
        eventi.append((inizio, 1, mido.Message("note_on", channel=9, note=41,
                                                 velocity=100, time=0)))
        eventi.append((fine, 0, mido.Message("note_off", channel=9, note=41,
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


@lru_cache(maxsize=4)
def filtri_pelle_grave(sample_rate):
    """Filtri del provino 01 (Pelle grave, senza sonagli) per un dato sample rate."""
    lowpass = butter(3, 2650, 'lowpass', fs=sample_rate, output='sos')
    midpass = butter(2, [420, 2750], 'bandpass', fs=sample_rate, output='sos')
    return lowpass, midpass


def colpo_di_pelle_grave(sample_rate, rng):
    """Sintesi del provino 01: membrana grave (119 Hz), senza sonagli.

    Riproduce la formula del provino '01_pelle_grave.wav': cinque modi
    inarmonici, lieve discesa iniziale di intonazione, rumori della pelle
    e due riflessioni molto deboli. Il guadagno fisso (~0.66) approssima
    il livello del provino senza normalizzare ogni sequenza separatamente.
    """
    n = int(round(0.46 * sample_rate))
    t = np.arange(n, dtype=np.float64) / sample_rate
    intonazione = rng.uniform(0.968, 1.030)

    modi = np.zeros(n, dtype=np.float64)
    for multiplo, ampiezza_relativa, fattore_decay, jitter in (
        (1.00, 1.000, 1.00, 0.000),
        (1.58, 0.480, 0.65, 0.012),
        (2.13, 0.250, 0.44, -0.019),
        (2.76, 0.135, 0.27, 0.025),
        (3.69, 0.075, 0.18, -0.018),
    ):
        frequenza = 119.0 * multiplo * intonazione * (1 + jitter)
        decadimento = 0.205 * fattore_decay
        tau = 0.018 + 0.012 / multiplo
        sweep = 0.22 / math.sqrt(multiplo)
        fase = 2 * np.pi * frequenza * (t + sweep * tau * (1 - np.exp(-t / tau)))
        ampiezza = ampiezza_relativa * (0.31 ** math.log2(multiplo))
        modi += ampiezza * np.exp(-t / decadimento) * np.sin(fase)

    attacco = 1 - np.exp(-t / 0.00115)
    lowpass, midpass = filtri_pelle_grave(sample_rate)
    rumore_grave = sosfilt(lowpass, rng.standard_normal(n))
    rumore_pelle = sosfilt(midpass, rng.standard_normal(n))
    corpo = (
        0.72 * attacco * modi
        + rumore_grave * (0.115 * np.exp(-t / 0.011) + 0.022 * np.exp(-t / 0.035))
        + 0.24 * 0.16 * rumore_pelle * np.exp(-t / 0.018)
    )

    # Prime riflessioni, come nel provino; nessun sonaglio metallico.
    for ritardo, guadagno in ((0.023, 0.55 * 0.045), (0.047, 0.30 * 0.045)):
        campioni = int(round(ritardo * sample_rate))
        corpo[campioni:] += guadagno * corpo[:-campioni].copy()

    return 0.66 * corpo


def scrivi_wav(sequenza, durata_totale, bpm, destinazione, seed, sample_rate=44_100):
    # Quattro semiminime per semibreve: durata in secondi = 4 * 60 / BPM.
    durata_secondi = float(durata_totale) * 4 * 60 / bpm
    campioni = round(durata_secondi * sample_rate)
    audio = np.zeros(campioni, dtype=np.float64)
    rng = np.random.default_rng(seed)

    posizione = Fraction(0)
    for durata in sequenza:
        inizio = round(float(posizione) * 4 * 60 / bpm * sample_rate)
        colpo = colpo_di_pelle_grave(sample_rate, rng)
        fine = min(campioni, inizio + len(colpo))
        if fine > inizio:
            audio[inizio:fine] += colpo[:fine - inizio]
        posizione += durata

    # Evita discontinuità alla fine del WAV senza prolungare la durata musicale.
    campioni_fade = min(campioni, max(1, round(0.008 * sample_rate)))
    if campioni_fade > 1:
        audio[-campioni_fade:] *= np.linspace(1.0, 0.0, campioni_fade)

    # Guadagno fisso e nessuna normalizzazione diversa per ciascuna sequenza.
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(destinazione), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def main():
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
    args = parser.parse_args()

    if not 0 < args.bpm <= 1000:
        parser.error("--bpm deve essere > 0 e <= 1000")
    if args.n < 1:
        parser.error("--n deve essere >= 1")

    try:
        sequenze = genera_sequenze(args.n, args.durata, args.durate, args.seed)
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "sequenze.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["sequenza", "durate", "attacchi_fuori_quarto", "cambi_durata"])
            for i, seq in enumerate(sequenze, start=1):
                base = args.out / f"sequenza_{i:03d}"
                scrivi_midi(seq, args.durata, args.bpm, base.with_suffix(".mid"))
                scrivi_wav(seq, args.durata, args.bpm,
                           base.with_suffix(".wav"), seed=args.seed + i)
                indicatori = complessita(seq)
                writer.writerow([i, " ".join(str(d) for d in seq), *indicatori])
                print(f"{base.name}: {' '.join(map(str, seq))}  | complessità={indicatori}")
    except (ValueError, RuntimeError) as errore:
        parser.error(str(errore))

    print(f"\nCreati {args.n} MIDI + {args.n} WAV + sequenze.csv in {args.out.resolve()}")


if __name__ == "__main__":
    main()
