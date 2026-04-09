"""
evaluate_sentiment_mock.py
==========================
Valuta il classificatore mock di sentiment (keyword-based) sul dataset
GitHub Gold Standard di Novielli et al. (MSR 2020).

Dataset: https://figshare.com/articles/dataset/11604597?file=21001260
- Scarica il file ZIP, decomprimi, salva il CSV come "novielli_gold.csv"
  nella stessa directory di questo script.

Metriche calcolate: Accuracy, Precision, Recall, F1 (macro-average)
Output: tabella con risultati per classe + metriche aggregate
"""

import csv
import re
import random
from collections import defaultdict
from pathlib import Path

# ─── Mock classifier (copia identica da backend/main.py) ────────────────────
_POS_KEYWORDS = {
    "great", "good", "excellent", "perfect", "love", "thanks", "helpful",
    "nice", "well", "clean", "easy", "fast", "improved", "appreciate",
    "incredible", "joy", "happy", "fix", "solved", "works", "amazing",
    "outstanding", "wonderful", "brilliant", "fantastic", "superb",
}
_NEG_KEYWORDS = {
    "bad", "wrong", "broken", "fail", "error", "slow", "crash", "bug",
    "issue", "problem", "useless", "stupid", "garbage", "terrible",
    "awful", "hate", "worse", "ugly", "disappointing", "sucks", "shut",
    "disagree", "frustrated", "disappointed", "confused", "concerned",
}

def mock_sentiment(text: str) -> str:
    """Restituisce 'positive', 'neutral' o 'negative'."""
    lower = text.lower()
    words = set(re.findall(r"\w+", lower))
    pos   = len(words & _POS_KEYWORDS)
    neg   = len(words & _NEG_KEYWORDS)
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    else:
        return "neutral"


# ─── Metriche ────────────────────────────────────────────────────────────────
def compute_metrics(y_true, y_pred, labels):
    """Calcola precision, recall, F1 per classe e macro-average."""
    counts = {l: {"tp": 0, "fp": 0, "fn": 0} for l in labels}

    for true, pred in zip(y_true, y_pred):
        if true not in counts:
            continue  # ignora label sconosciute
        if pred == true:
            counts[true]["tp"] += 1
        else:
            counts[pred]["fp"] += 1 if pred in counts else 0
            counts[true]["fn"] += 1

    results = {}
    for l in labels:
        tp = counts[l]["tp"]
        fp = counts[l]["fp"]
        fn = counts[l]["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        results[l] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}

    accuracy = sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true) if y_true else 0.0
    macro_precision = sum(r["precision"] for r in results.values()) / len(labels)
    macro_recall    = sum(r["recall"]    for r in results.values()) / len(labels)
    macro_f1        = sum(r["f1"]        for r in results.values()) / len(labels)

    return results, accuracy, macro_precision, macro_recall, macro_f1


# ─── Caricamento dataset ──────────────────────────────────────────────────────
def load_novielli(path: str):
    """
    Carica il dataset Novielli. Prova diverse colonne comuni.
    Adatta i nomi colonna se necessario guardando l'header del CSV.
    """
    y_true, texts = [], []
    label_map = {
        "positive": "positive", "pos": "positive", "1": "positive", "2": "positive",
        "negative": "negative", "neg": "negative", "-1": "negative",
        "neutral":  "neutral",  "neu": "neutral",   "0": "neutral",
    }

    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        # Mostra header per debug
        header_line = f.readline().strip()
        print(f"Header: {header_line}")
        f.seek(0)

        reader = csv.DictReader(f, delimiter=';')
        headers = reader.fieldnames
        print(f"Colonne rilevate: {headers}\n")

        # Cerca la colonna testo (case-insensitive)
        headers_lower = {h.lower(): h for h in headers}
        text_col = None
        for candidate in ["text", "sentence", "body", "comment", "content"]:
            if candidate in headers_lower:
                text_col = headers_lower[candidate]; break
        if text_col is None:
            raise ValueError(f"Nessuna colonna testo trovata. Colonne: {headers}")

        # Cerca la colonna label (case-insensitive)
        label_col = None
        for candidate in ["polarity", "label", "sentiment", "oracle", "annotation"]:
            if candidate in headers_lower:
                label_col = headers_lower[candidate]; break
        if label_col is None:
            raise ValueError(f"Nessuna colonna label trovata. Colonne: {headers}")

        print(f"Colonna testo: '{text_col}' | Colonna label: '{label_col}'\n")

        for row in reader:
            raw_label = row[label_col].strip().lower()
            mapped    = label_map.get(raw_label)
            if mapped is None:
                continue  # ignora righe con label sconosciute
            texts.append(row[text_col].strip())
            y_true.append(mapped)

    return texts, y_true


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    dataset_path = "novielli_gold.csv"
    if not Path(dataset_path).exists():
        print(f"ERRORE: File '{dataset_path}' non trovato.")
        print("Scarica il dataset da: https://figshare.com/articles/dataset/11604597?file=21001260")
        print("Salva il CSV come 'novielli_gold.csv' nella stessa directory di questo script.")
        return

    print("=" * 60)
    print("VALUTAZIONE MOCK SENTIMENT — Novielli et al. 2020")
    print("=" * 60)

    texts, y_true = load_novielli(dataset_path)
    print(f"Esempi caricati: {len(y_true)}")
    dist = defaultdict(int)
    for l in y_true: dist[l] += 1
    print(f"Distribuzione ground truth: {dict(dist)}\n")

    # Applica il classificatore mock
    y_pred = [mock_sentiment(t) for t in texts]

    labels = ["positive", "neutral", "negative"]
    per_class, accuracy, macro_p, macro_r, macro_f1 = compute_metrics(y_true, y_pred, labels)

    # ── Stampa risultati ──────────────────────────────────────────────────────
    print("=" * 60)
    print(f"{'Classe':<12} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Support':>10}")
    print("-" * 60)
    for l in labels:
        r = per_class[l]
        print(f"{l:<12} {r['precision']:>10.3f} {r['recall']:>8.3f} {r['f1']:>8.3f} {r['support']:>10}")
    print("-" * 60)
    print(f"{'MACRO AVG':<12} {macro_p:>10.3f} {macro_r:>8.3f} {macro_f1:>8.3f}")
    print(f"\nAccuracy: {accuracy:.3f} ({accuracy*100:.1f}%)")
    print("=" * 60)

    # Errori più comuni
    errors = [(texts[i], y_true[i], y_pred[i])
              for i in range(len(texts)) if y_true[i] != y_pred[i]]
    print(f"\nErrori totali: {len(errors)}/{len(texts)} ({len(errors)/len(texts)*100:.1f}%)")

    print("\nEsempi di predizioni errate (prime 5):")
    for text, true, pred in errors[:5]:
        snippet = text[:80] + "…" if len(text) > 80 else text
        print(f"  True={true:8s} | Pred={pred:8s} | '{snippet}'")

    # ── Output per LaTeX ─────────────────────────────────────────────────────
    print("\n\n" + "=" * 60)
    print("TABELLA LaTeX (copia nel capitolo Testing):")
    print("=" * 60)
    print(r"""\begin{table}[htbp]
\centering
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Classe} & \textbf{Precision} & \textbf{Recall} & \textbf{F1} & \textbf{Support} \\
\hline""")
    for l in labels:
        r = per_class[l]
        label_it = {"positive": "Positive", "neutral": "Neutral", "negative": "Negative"}[l]
        print(f"{label_it} & {r['precision']:.3f} & {r['recall']:.3f} & {r['f1']:.3f} & {r['support']} \\\\")
    print(r"\hline")
    print(f"Macro avg & {macro_p:.3f} & {macro_r:.3f} & {macro_f1:.3f} & {len(y_true)} \\\\")
    print(r"\hline")
    print(f"\\multicolumn{{4}}{{l}}{{Accuracy}} & {accuracy:.3f} \\\\")
    print(r"""\hline
\end{tabular}
\caption{Prestazioni del classificatore mock sentiment sul dataset GitHub Gold Standard
(Novielli et al., MSR 2020), \textit{n} = """ + str(len(y_true)) + r""".
Metriche calcolate con macro-average, coerentemente con Novielli et al.}
\label{tab:mock_sentiment_eval}
\end{table}""")


if __name__ == "__main__":
    main()