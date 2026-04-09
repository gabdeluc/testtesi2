"""
evaluate_bert_sentiment.py
==========================
Valuta il modello BERT reale nlptown/bert-base-multilingual-uncased-sentiment
sul dataset GitHub Gold Standard di Novielli et al. (MSR 2020).

Prerequisiti:
    pip install transformers torch

Dataset: novielli_gold.csv (separatore ';', colonne ID;Polarity;Text)
Scarica da: https://figshare.com/articles/dataset/11604597?file=21001260

Attenzione: su CPU impiega ~20-40 minuti per 7122 esempi.
             Con GPU (CUDA) scende a 2-5 minuti.
"""

import csv
import time
import torch
import torch.nn.functional as F
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ─── Configurazione ───────────────────────────────────────────────────────────
MODEL_NAME   = "nlptown/bert-base-multilingual-uncased-sentiment"
DATASET_PATH = "novielli_gold.csv"
BATCH_SIZE   = 32      # aumenta se hai GPU, riduci se vai out of memory
MAX_LENGTH   = 512
DEVICE       = "cuda" if torch.cuda.is_available() else "cpu"

# Soglie per mappare le stelle in classi (come nel backend)
# stars < 2.5  → negative
# 2.5 ≤ stars ≤ 3.5 → neutral
# stars > 3.5  → positive
THRESH_NEG = 2.5
THRESH_POS = 3.5


# ─── Mappatura etichette Novielli → nostre classi ────────────────────────────
LABEL_MAP_DATASET = {
    "positive": "positive",
    "negative": "negative",
    "neutral":  "neutral",
    "pos": "positive",
    "neg": "negative",
    "neu": "neutral",
}


# ─── Metriche ─────────────────────────────────────────────────────────────────
def compute_metrics(y_true, y_pred, labels=("positive", "neutral", "negative")):
    counts = {l: {"tp": 0, "fp": 0, "fn": 0} for l in labels}
    for true, pred in zip(y_true, y_pred):
        if true not in counts:
            continue
        if pred == true:
            counts[true]["tp"] += 1
        else:
            if pred in counts:
                counts[pred]["fp"] += 1
            counts[true]["fn"] += 1

    results = {}
    for l in labels:
        tp, fp, fn = counts[l]["tp"], counts[l]["fp"], counts[l]["fn"]
        p  = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        results[l] = {"precision": p, "recall": r, "f1": f1, "support": tp + fn}

    accuracy  = sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)
    macro_p   = sum(r["precision"] for r in results.values()) / len(labels)
    macro_r   = sum(r["recall"]    for r in results.values()) / len(labels)
    macro_f1  = sum(r["f1"]        for r in results.values()) / len(labels)

    return results, accuracy, macro_p, macro_r, macro_f1


# ─── Caricamento dataset ──────────────────────────────────────────────────────
def load_dataset(path):
    texts, labels = [], []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            raw = row["Polarity"].strip().lower()
            lbl = LABEL_MAP_DATASET.get(raw)
            if lbl is None:
                continue
            text = row["Text"].strip()
            if text:
                texts.append(text)
                labels.append(lbl)
    return texts, labels


# ─── Inferenza BERT ───────────────────────────────────────────────────────────
def predict_batch(model, tokenizer, texts):
    """
    Predice la classe sentiment per una lista di testi.
    Restituisce lista di stringhe: 'positive', 'neutral', 'negative'.
    """
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_LENGTH,
        padding=True,
    ).to(DEVICE)

    with torch.no_grad():
        logits = model(**inputs).logits

    # 5 classi (1-5 stelle) → probabilità
    probs = F.softmax(logits, dim=-1)  # shape: (batch, 5)

    predictions = []
    for prob_row in probs:
        # Media pesata → stima del valore atteso stelle ∈ [1, 5]
        stars = sum((i + 1) * prob_row[i].item() for i in range(5))

        if stars < THRESH_NEG:
            predictions.append("negative")
        elif stars > THRESH_POS:
            predictions.append("positive")
        else:
            predictions.append("neutral")

    return predictions


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    if not Path(DATASET_PATH).exists():
        print(f"ERRORE: File '{DATASET_PATH}' non trovato.")
        return

    print(f"Device: {DEVICE.upper()}")
    print(f"Batch size: {BATCH_SIZE}")

    # Carica dataset
    print(f"\nCaricamento dataset '{DATASET_PATH}'...")
    texts, y_true = load_dataset(DATASET_PATH)
    print(f"Esempi: {len(texts)}")
    from collections import Counter
    print(f"Distribuzione: {dict(Counter(y_true))}\n")

    # Carica modello
    print(f"Caricamento modello '{MODEL_NAME}'...")
    print("(primo avvio: download ~400MB — potrebbe richiedere qualche minuto)\n")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model     = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).to(DEVICE)
    model.eval()
    print(f"Modello caricato in {time.time() - t0:.1f}s\n")

    # Inferenza in batch con progress
    print(f"Inferenza su {len(texts)} esempi (batch={BATCH_SIZE})...")
    print("Questo richiede ~20-40 minuti su CPU, ~2-5 minuti su GPU.\n")

    y_pred  = []
    t_start = time.time()

    for i in range(0, len(texts), BATCH_SIZE):
        batch   = texts[i: i + BATCH_SIZE]
        preds   = predict_batch(model, tokenizer, batch)
        y_pred.extend(preds)

        # Progress ogni 10 batch
        if (i // BATCH_SIZE) % 10 == 0:
            done     = i + len(batch)
            elapsed  = time.time() - t_start
            per_item = elapsed / done if done > 0 else 0
            eta      = per_item * (len(texts) - done)
            print(f"  {done}/{len(texts)} esempi | "
                  f"elapsed: {elapsed/60:.1f}min | ETA: {eta/60:.1f}min")

    elapsed = time.time() - t_start
    print(f"\nInferenza completata in {elapsed/60:.1f} minuti\n")

    # Calcola metriche
    labels   = ["positive", "neutral", "negative"]
    per_class, accuracy, macro_p, macro_r, macro_f1 = compute_metrics(y_true, y_pred, labels)

    # ── Stampa risultati ──────────────────────────────────────────────────────
    print("=" * 65)
    print(f"RISULTATI — {MODEL_NAME}")
    print(f"Dataset: GitHub Gold Standard, Novielli et al. 2020 (n={len(texts)})")
    print("=" * 65)
    print(f"{'Classe':<12} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Support':>10}")
    print("-" * 65)
    for l in labels:
        r = per_class[l]
        print(f"{l:<12} {r['precision']:>10.3f} {r['recall']:>8.3f} "
              f"{r['f1']:>8.3f} {r['support']:>10}")
    print("-" * 65)
    print(f"{'Macro avg':<12} {macro_p:>10.3f} {macro_r:>8.3f} {macro_f1:>8.3f}")
    print(f"\nAccuracy: {accuracy:.3f} ({accuracy * 100:.1f}%)")
    print("=" * 65)

    # Confronto con benchmark Novielli
    print("\nCONFRONTO con strumenti SE-specifici (Novielli et al. 2020):")
    print(f"  Senti4SD  Macro F1: 0.92 (within-platform, stesso dataset)")
    print(f"  SentiCR   Macro F1: 0.80 (within-platform)")
    print(f"  nlptown   Macro F1: {macro_f1:.3f} (questo risultato)")
    print("\nNota: Senti4SD è addestrato sullo stesso dominio (GitHub).")
    print("      nlptown è addestrato su recensioni consumer — domain shift atteso.")

    # ── Output LaTeX ─────────────────────────────────────────────────────────
    print("\n\n" + "=" * 65)
    print("TABELLA LaTeX:")
    print("=" * 65)
    print(r"""\begin{table}[htbp]
\centering
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Classe} & \textbf{Precision} & \textbf{Recall} & \textbf{F1} & \textbf{Support} \\
\hline""")
    label_it = {"positive": "Positive", "neutral": "Neutral", "negative": "Negative"}
    for l in labels:
        r = per_class[l]
        print(f"{label_it[l]} & {r['precision']:.3f} & {r['recall']:.3f} "
              f"& {r['f1']:.3f} & {r['support']} \\\\")
    print(r"\hline")
    print(f"Macro avg & {macro_p:.3f} & {macro_r:.3f} & {macro_f1:.3f} & {len(texts)} \\\\")
    print(r"\hline")
    print(f"\\multicolumn{{4}}{{l}}{{Accuracy}} & {accuracy:.3f} \\\\")
    print(r"""\hline
\end{tabular}
\caption{Prestazioni di \texttt{nlptown/bert-base-multilingual-uncased-sentiment}
sul dataset GitHub Gold Standard (Novielli et al., MSR 2020), \textit{n} = """ +
          str(len(texts)) + r""".
Soglie di classificazione: $<2.5$ stelle $\rightarrow$ negative,
$2.5$--$3.5$ $\rightarrow$ neutral, $>3.5$ $\rightarrow$ positive,
coerenti con la model card del modello.}
\label{tab:bert_sentiment_eval}
\end{table}""")


if __name__ == "__main__":
    main()