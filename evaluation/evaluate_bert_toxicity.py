"""
evaluate_bert_toxicity.py
=========================
Valuta il modello BERT reale gravitee-io/bert-small-toxicity
sul dataset di Raman et al. (ICSE-NIER 2020).

Prerequisiti:
    pip install transformers torch

Dataset: raman_toxicity.csv
Scarica da: https://github.com/CMUSTRUDEL/toxicity-detector/blob/master/data/training/labeled_test_issues.csv

Su CPU impiega ~2-5 minuti (dataset piccolo, 193 esempi).
"""

import csv
import time
import torch
import torch.nn.functional as F
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ─── Configurazione ───────────────────────────────────────────────────────────
MODEL_NAME       = "gravitee-io/bert-small-toxicity"
DATASET_PATH     = "raman_toxicity.csv"
BATCH_SIZE       = 16
MAX_LENGTH       = 512
TOXICITY_THRESHOLD = 0.6   # coerente col backend (TOXICITY_THRESHOLD = 0.6)
DEVICE           = "cuda" if torch.cuda.is_available() else "cpu"


# ─── Metriche binarie ─────────────────────────────────────────────────────────
def compute_binary_metrics(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)

    n         = len(y_true)
    accuracy  = (tp + tn) / n if n > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    # F0.5: pesa precision doppio del recall (come Raman et al.)
    f05       = (1 + 0.5**2) * precision * recall / (0.5**2 * precision + recall) \
                if (0.5**2 * precision + recall) > 0 else 0.0

    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "accuracy": accuracy, "precision": precision,
            "recall": recall, "f1": f1, "f05": f05}


# ─── Caricamento dataset ──────────────────────────────────────────────────────
def load_dataset(path):
    texts, labels = [], []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get("toxicity", "").strip().lower()
            if raw == "y":
                label = 1
            elif raw == "n":
                label = 0
            else:
                try:
                    label = int(float(raw))
                except ValueError:
                    continue
            text = row.get("total_text", "").strip()
            if text:
                texts.append(text)
                labels.append(label)
    return texts, labels


# ─── Inferenza BERT ───────────────────────────────────────────────────────────
def predict_batch(model, tokenizer, texts, threshold):
    """
    Predice la classe tossicità per una lista di testi.
    Restituisce lista di int: 1 (tossico) o 0 (non tossico).
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

    # 2 classi: [non_toxic, toxic] → softmax
    probs = F.softmax(logits, dim=-1)  # shape: (batch, 2)

    predictions = []
    for prob_row in probs:
        toxic_score = prob_row[1].item()  # probabilità classe tossica
        predictions.append(1 if toxic_score > threshold else 0)

    return predictions


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    if not Path(DATASET_PATH).exists():
        print(f"ERRORE: File '{DATASET_PATH}' non trovato.")
        return

    print(f"Device: {DEVICE.upper()}")
    print(f"Soglia is_toxic: {TOXICITY_THRESHOLD}")

    # Carica dataset
    print(f"\nCaricamento dataset '{DATASET_PATH}'...")
    texts, y_true = load_dataset(DATASET_PATH)
    print(f"Esempi: {len(texts)}")
    n_toxic = sum(y_true)
    print(f"Tossici: {n_toxic} | Non tossici: {len(y_true) - n_toxic}\n")

    # Carica modello
    print(f"Caricamento modello '{MODEL_NAME}'...")
    print("(primo avvio: download ~200MB)\n")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model     = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME).to(DEVICE)
    model.eval()
    print("Classi del modello:", model.config.id2label)
    print(f"Modello caricato in {time.time() - t0:.1f}s\n")

    # Inferenza
    print(f"Inferenza su {len(texts)} esempi (batch={BATCH_SIZE})...")
    y_pred  = []
    t_start = time.time()

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i: i + BATCH_SIZE]
        preds = predict_batch(model, tokenizer, batch, TOXICITY_THRESHOLD)
        y_pred.extend(preds)

    elapsed = time.time() - t_start
    print(f"Inferenza completata in {elapsed:.1f}s\n")

    # Calcola metriche
    m = compute_binary_metrics(y_true, y_pred)

    # ── Stampa risultati ──────────────────────────────────────────────────────
    print("=" * 65)
    print(f"RISULTATI — {MODEL_NAME}")
    print(f"Dataset: Raman et al., ICSE-NIER 2020 (n={len(texts)})")
    print(f"Soglia is_toxic: {TOXICITY_THRESHOLD}")
    print("=" * 65)
    print(f"{'Metrica':<20} {'Valore':>10}")
    print("-" * 65)
    print(f"{'Accuracy':<20} {m['accuracy']:>10.3f}")
    print(f"{'Precision':<20} {m['precision']:>10.3f}")
    print(f"{'Recall':<20} {m['recall']:>10.3f}")
    print(f"{'F1':<20} {m['f1']:>10.3f}")
    print(f"{'F0.5 (Raman)':<20} {m['f05']:>10.3f}")
    print("-" * 65)
    print(f"  TP={m['tp']}  FP={m['fp']}  TN={m['tn']}  FN={m['fn']}")
    print("=" * 65)

    # Confronto con SVM di Raman
    print(f"\nCONFRONTO con SVM di Raman et al. (held-out test set, stesso dataset):")
    print(f"  SVM       Precision=0.750  Recall=0.350  F1=0.480  F0.5≈0.620")
    print(f"  gravitee  Precision={m['precision']:.3f}  Recall={m['recall']:.3f}  "
          f"F1={m['f1']:.3f}  F0.5={m['f05']:.3f}")

    # Analisi soglie alternative
    print("\nAnalisi sensibilità alla soglia (stesso modello, soglie diverse):")
    print(f"{'Soglia':>8} {'Precision':>10} {'Recall':>8} {'F1':>8} {'F0.5':>8}")
    for thresh in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        # Ri-predici con soglia diversa
        y_p2 = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i: i + BATCH_SIZE]
            inputs = tokenizer(
                batch, return_tensors="pt", truncation=True,
                max_length=MAX_LENGTH, padding=True
            ).to(DEVICE)
            with torch.no_grad():
                logits = model(**inputs).logits
            probs = F.softmax(logits, dim=-1)
            y_p2.extend([1 if p[1].item() > thresh else 0 for p in probs])
        m2 = compute_binary_metrics(y_true, y_p2)
        marker = " ← usata nel sistema" if thresh == TOXICITY_THRESHOLD else ""
        print(f"{thresh:>8.1f} {m2['precision']:>10.3f} {m2['recall']:>8.3f} "
              f"{m2['f1']:>8.3f} {m2['f05']:>8.3f}{marker}")

    # ── Output LaTeX ─────────────────────────────────────────────────────────
    print("\n\n" + "=" * 65)
    print("TABELLA LaTeX:")
    print("=" * 65)
    print(r"""\begin{table}[htbp]
\centering
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Classificatore} & \textbf{Precision} & \textbf{Recall} & \textbf{F1} & \textbf{F\textsubscript{0.5}} \\
\hline""")
    print(f"gravitee-io (soglia {TOXICITY_THRESHOLD}) & "
          f"{m['precision']:.3f} & {m['recall']:.3f} & {m['f1']:.3f} & {m['f05']:.3f} \\\\")
    print(r"SVM Raman et al.~\cite{Raman2020} & 0.750 & 0.350 & 0.480 & 0.620 \\")
    print(r"""\hline
\end{tabular}
\caption{Prestazioni di \texttt{gravitee-io/bert-small-toxicity} sul dataset
di Raman et al. (ICSE-NIER 2020), \textit{n} = """ + str(len(texts)) + r""".
La soglia $0.6$ è quella configurata nel sistema (\texttt{TOXICITY\_THRESHOLD}).
$F_{0.5}$ pesa la precision doppio del recall, coerentemente con Raman et al.}
\label{tab:bert_toxicity_eval}
\end{table}""")


if __name__ == "__main__":
    main()