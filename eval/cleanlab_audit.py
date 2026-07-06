"""Label-quality audit (cleanlab confident learning). Objectively flags which SINGLE-GOLD tasks
in the corpus are likely mislabeled / ambiguous — replacing hand-judgment about "debatable golds".

Features = task embeddings (all-MiniLM); labels = gold skill; a cross-validated logistic head gives
out-of-sample pred_probs; cleanlab.filter.find_label_issues ranks the suspects and suggests a label.

Run:  .venv/Scripts/python.exe eval/cleanlab_audit.py [tasks.jsonl ...]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np                                    # noqa: E402
from sklearn.linear_model import LogisticRegression   # noqa: E402
from sklearn.model_selection import cross_val_predict  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402
from cleanlab.filter import find_label_issues          # noqa: E402
from cleanlab.rank import get_label_quality_scores     # noqa: E402

files = sys.argv[1:] or ["eval/sim_tasks_mega.jsonl"]
rows = []
for f in files:
    for l in Path(f).read_text(encoding="utf-8").splitlines():
        if l.strip():
            rows.append(json.loads(l))
# single-gold only (multi-label is a separate audit); keep classes with >= 4 examples for CV
single = [r for r in rows if len(r.get("gold", [])) == 1]
cnt = Counter(r["gold"][0] for r in single)
keep = {k for k, v in cnt.items() if v >= 4}
data = [r for r in single if r["gold"][0] in keep]
labels_str = [r["gold"][0] for r in data]
classes = sorted(set(labels_str))
cidx = {c: i for i, c in enumerate(classes)}
y = np.array([cidx[s] for s in labels_str])
print(f"{len(rows)} tasks | {len(single)} single-gold | auditing {len(data)} "
      f"across {len(classes)} skills (>=4 ex)\n", flush=True)

emb = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
X = emb.encode([r["task"] for r in data], normalize_embeddings=True, show_progress_bar=False)

clf = LogisticRegression(max_iter=2000, C=3.0)
n_folds = max(3, min(5, int(min(cnt[c] for c in keep))))
pred = cross_val_predict(clf, X, y, cv=n_folds, method="predict_proba")

issues = find_label_issues(labels=y, pred_probs=pred,
                           return_indices_ranked_by="self_confidence", n_jobs=1)
qual = get_label_quality_scores(labels=y, pred_probs=pred)
print(f"cleanlab flags {len(issues)} likely label issues (of {len(data)}):\n", flush=True)
for i in issues:
    gold = classes[y[i]]
    sugg = classes[int(pred[i].argmax())]
    print(f"  [{qual[i]:.2f}] gold={gold}  →suggests={sugg}")
    print(f"        {data[i]['task'][:95]}")
Path("logs/label_issues.json").write_text(json.dumps(
    [{"task": data[i]["task"], "gold": classes[y[i]], "suggested": classes[int(pred[i].argmax())],
      "quality": float(qual[i])} for i in issues], ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nwrote logs/label_issues.json ({len(issues)} items)")
