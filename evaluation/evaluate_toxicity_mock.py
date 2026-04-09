"""
evaluate_toxicity_mock.py
=========================
Valuta il classificatore mock di toxicity (keyword-based) sul dataset
di Raman et al. (ICSE-NIER 2020).

Dataset: https://github.com/CMUSTRUDEL/toxicity-detector/blob/master/data/training/labeled_test_issues.csv
- Clicca "Raw" e salva come "raman_toxicity.csv" nella stessa directory.

Metriche calcolate: Accuracy, Precision, Recall, F1 (binario, classe tossica)
Output: tabella risultati + confronto con SVM di Raman et al.
"""

import csv
import re
from pathlib import Path

# ─── Mock classifier (copia identica da backend/main.py) ────────────────────
_TOX_KEYWORDS = {
    "stupid", "idiot", "garbage", "shut up", "useless", "hate", "awful",
    "damn", "crap", "jerk", "moron", "shut", "racist", "dumb", "pathetic",
    "disgusting", "terrible", "worthless", "horrible", "incompetent",
}

def mock_toxicity(text: str) -> int:
    """Restituisce 1 (tossico) o 0 (non tossico)."""
    lower = text.lower()
    words = set(re.findall(r"\w+", lower))
    hits  = len(words & _TOX_KEYWORDS)
    # Soglia: almeno 1 keyword = tossico (soglia conservativa)
    return 1 if hits >= 1 else 0


# ─── Metriche binarie ────────────────────────────────────────────────────────
def compute_binary_metrics(y_true, y_pred):
    """
    Metriche per classificazione binaria.
    Classe positiva = tossico (1).
    """
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)

    accuracy  = (tp + tn) / len(y_true) if y_true else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    # F0.5 — usato da Raman et al., pesa precision doppio del recall
    f05       = (1 + 0.5**2) * precision * recall / (0.5**2 * precision + recall) \
                if (0.5**2 * precision + recall) > 0 else 0.0

    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "accuracy": accuracy, "precision": precision,
            "recall": recall, "f1": f1, "f05": f05}


# ─── Caricamento dataset ──────────────────────────────────────────────────────
def load_raman(path: str):
    """Carica il dataset Raman. Adatta i nomi colonna se necessario."""
    y_true, texts = [], []

    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        header_line = f.readline().strip()
        print(f"Header: {header_line}")
        f.seek(0)

        reader = csv.DictReader(f)
        headers = reader.fieldnames
        print(f"Colonne rilevate: {headers}\n")

        # Cerca colonna testo (il dataset Raman usa 'total_text')
        text_col = None
        for candidate in ["total_text", "body", "text", "comment", "content", "sentence"]:
            if candidate in headers:
                text_col = candidate; break
        if text_col is None:
            raise ValueError(f"Nessuna colonna testo. Colonne: {headers}")

        # Cerca colonna label (il dataset Raman usa 'toxicity' con valori 'y'/'n')
        label_col = None
        for candidate in ["toxicity", "label", "toxic", "is_toxic", "annotation"]:
            if candidate in headers:
                label_col = candidate; break
        if label_col is None:
            raise ValueError(f"Nessuna colonna label. Colonne: {headers}")

        print(f"Colonna testo: '{text_col}' | Colonna label: '{label_col}'\n")

        for row in reader:
            raw = row[label_col].strip().lower()
            # Supporta: 'y'/'n', 0/1, 'toxic'/'nontoxic', 'true'/'false'
            label_map_str = {"y": 1, "n": 0, "toxic": 1, "nontoxic": 0,
                             "non-toxic": 0, "true": 1, "false": 0}
            if raw in label_map_str:
                label = label_map_str[raw]
            else:
                try:
                    label = int(float(raw))
                except ValueError:
                    continue
            text = row[text_col].strip()
            if not text:
                continue
            y_true.append(label)
            texts.append(text)

    return texts, y_true


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    dataset_path = "raman_toxicity.csv"
    if not Path(dataset_path).exists():
        print(f"ERRORE: File '{dataset_path}' non trovato.")
        print("Scarica da: https://raw.githubusercontent.com/CMUSTRUDEL/toxicity-detector/"
              "master/data/training/labeled_test_issues.csv")
        print("Salva come 'raman_toxicity.csv' nella stessa directory di questo script.")
        return

    print("=" * 60)
    print("VALUTAZIONE MOCK TOXICITY — Raman et al. 2020")
    print("=" * 60)

    texts, y_true = load_raman(dataset_path)
    print(f"Esempi caricati: {len(y_true)}")
    n_toxic     = sum(y_true)
    n_nontoxic  = len(y_true) - n_toxic
    print(f"Tossici: {n_toxic} | Non tossici: {n_nontoxic}\n")

    y_pred = [mock_toxicity(t) for t in texts]
    m      = compute_binary_metrics(y_true, y_pred)

    print("=" * 60)
    print(f"{'Metrica':<20} {'Valore':>10}")
    print("-" * 60)
    print(f"{'Accuracy':<20} {m['accuracy']:>10.3f}")
    print(f"{'Precision':<20} {m['precision']:>10.3f}")
    print(f"{'Recall':<20} {m['recall']:>10.3f}")
    print(f"{'F1':<20} {m['f1']:>10.3f}")
    print(f"{'F0.5 (Raman)':<20} {m['f05']:>10.3f}")
    print("-" * 60)
    print(f"  TP={m['tp']}  FP={m['fp']}  TN={m['tn']}  FN={m['fn']}")
    print("=" * 60)

    # Confronto con baseline SVM di Raman
    print("\nCONFRONTO con SVM di Raman et al. (held-out test set):")
    print(f"  SVM Precision: 0.75 | Recall: 0.35 | F1: 0.48 | F0.5: ≈0.62")
    print(f"  Mock Precision: {m['precision']:.2f} | Recall: {m['recall']:.2f} "
          f"| F1: {m['f1']:.2f} | F0.5: {m['f05']:.2f}")

    # Esempi di errori
    errors_fp = [(texts[i],) for i in range(len(texts)) if y_true[i] == 0 and y_pred[i] == 1]
    errors_fn = [(texts[i],) for i in range(len(texts)) if y_true[i] == 1 and y_pred[i] == 0]
    print(f"\nFalsi positivi: {len(errors_fp)} | Falsi negativi: {len(errors_fn)}")
    print("\nEsempi falsi negativi (tossici non rilevati):")
    for (t,) in errors_fn[:3]:
        print(f"  '{t[:100]}…'")

    # ── Output LaTeX ─────────────────────────────────────────────────────────
    print("\n\n" + "=" * 60)
    print("TABELLA LaTeX:")
    print("=" * 60)
    print(r"""\begin{table}[htbp]
\centering
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Classificatore} & \textbf{Precision} & \textbf{Recall} & \textbf{F1} & \textbf{F\textsubscript{0.5}} \\
\hline""")
    print(f"Mock keyword-based & {m['precision']:.3f} & {m['recall']:.3f} & {m['f1']:.3f} & {m['f05']:.3f} \\\\")
    print(r"SVM Raman et al.~\cite{Raman2020} & 0.750 & 0.350 & 0.480 & 0.620 \\")
    print(r"""\hline
\end{tabular}
\caption{Prestazioni del classificatore mock toxicity sul dataset di Raman et al. (ICSE-NIER 2020)
confrontate con il classificatore SVM degli autori (held-out test set).
$F_{0.5}$ pesa la precision doppio del recall, coerentemente con la metrica di ottimizzazione originale.}
\label{tab:mock_toxicity_eval}
\end{table}""")


if __name__ == "__main__":
    main()