# 2.1 Intent Classifier — Results (CLO04)

Winner: **LogisticRegression** by macro-F1.

## Model comparison

| model | accuracy | precision_macro | recall_macro | f1_macro | fit_seconds |
| --- | --- | --- | --- | --- | --- |
| LogisticRegression | 0.9417 | 0.9417 | 0.9417 | 0.9416 | 0.451 |
| SVM | 0.9417 | 0.9417 | 0.9417 | 0.9416 | 3.257 |
| KNN | 0.9383 | 0.9384 | 0.9384 | 0.9383 | 0.211 |
| RandomForest | 0.9283 | 0.9284 | 0.9284 | 0.9282 | 0.626 |
| DecisionTree | 0.8233 | 0.8259 | 0.8236 | 0.8239 | 0.182 |

## Best model — macro metrics

- accuracy: 0.9417
- precision (macro): 0.9417
- recall (macro): 0.9417
- f1 (macro): 0.9416

Confusion matrix: `reports/figures/intent_classifier_confusion_matrix.png`

## Per-class report

```
                    precision    recall  f1-score   support

           browser       0.96      0.93      0.94       101
     communication       0.93      0.96      0.95        99
desktop_automation       0.93      0.93      0.93        99
    document_intel       0.96      0.92      0.94       102
      llm_fallback       0.95      0.97      0.96       101
      memory_query       0.92      0.94      0.93        98

          accuracy                           0.94       600
         macro avg       0.94      0.94      0.94       600
      weighted avg       0.94      0.94      0.94       600
```