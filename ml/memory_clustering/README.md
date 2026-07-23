# 2.3 Memory / Document Clustering — CLO04 (clustering)

**Owner:** AI/ML specialist · **Labs reused:** 21–26 (K-Means, DBSCAN, Hierarchical, PCA)

Groups stored memories/documents into topic clusters so retrieval is faster and
the Planner can make proactive suggestions ("you've got 6 items on your DBMS project").

## Data
The **only** component that can use real external data — drop your own notes/docs
into `data/raw/` (short text files or a CSV of snippets). Embed them (TF-IDF is
acceptable for a course project; sentence-embeddings are a stretch goal).

## Pipeline
`documents → embeddings → PCA (dimensionality reduction, Lab 25–26) → clustering`

## Models to compare
K-Means · Hierarchical · DBSCAN

## Graded evidence (`notebooks/2_3_memory_clustering.ipynb`)
- **Silhouette score** per method
- 2-D scatter of clusters **after PCA**
- Note on how many clusters / which method you'd deploy and why

## Production hook
`assign_cluster(doc) -> cluster_id` powering Memory-Agent retrieval + suggestions.
