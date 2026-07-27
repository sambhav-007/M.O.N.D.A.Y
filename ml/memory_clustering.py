"""
M.O.N.D.A.Y. — Component 2.3: Memory / Document Clustering
============================================================
Course Mapping : CLO04 — Clustering with metrics
Lab Reference  : Lab 21–26 (K-Means, DBSCAN, Hierarchical, PCA)
Owner          : AI/ML Specialist

Purpose
-------
Group stored memories/documents into topic clusters so retrieval is faster
and the Planner Agent can make proactive suggestions:
  "You have 6 items related to your DBMS project."

Pipeline
--------
synthetic document embeddings → PCA (dim reduction) → clustering

Models compared
---------------
  K-Means | Hierarchical (Agglomerative) | DBSCAN

Evaluation (CLO04 requirement)
-------------------------------
Silhouette Score per method. Cluster visualisation post-PCA.

Production Role
---------------
Powers the Memory Agent's retrieval and the "proactive suggestion" feature.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich import box
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sklearn.datasets import make_classification

warnings.filterwarnings("ignore")
console = Console()

# ── Topic Categories (simulating M.O.N.D.A.Y. Memory) ─────────────────────────
MEMORY_TOPICS = [
    "Machine Learning Coursework",
    "Project Monday Development",
    "Job Applications & Internships",
    "Personal Finance & Shopping",
    "Research Papers & References",
    "Communication & Emails",
    "Desktop Files & Organisation",
]

N_TOPICS = len(MEMORY_TOPICS)


# ── Synthetic Document Embedding Generator ────────────────────────────────────
def generate_memory_embeddings(
    n_samples: int = 700,
    embedding_dim: int = 64,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Simulates document embeddings as would come from a sentence-transformer
    or TF-IDF vectoriser on real memory entries.

    In production, these would be real embeddings from the Memory Agent's
    vector store (Chroma / FAISS). Here we generate Gaussian clusters in
    a high-dimensional space to approximate the structure.

    Returns
    -------
    embeddings : (n_samples, embedding_dim) float array
    true_labels : (n_samples,) int array (for evaluation only)
    sample_texts : List[str] of representative memory content labels
    """
    rng = np.random.default_rng(seed)
    embeddings = []
    true_labels = []
    sample_texts = []

    samples_per_topic = n_samples // N_TOPICS

    topic_centers = rng.standard_normal((N_TOPICS, embedding_dim)) * 3.0

    for topic_idx, topic in enumerate(MEMORY_TOPICS):
        center = topic_centers[topic_idx]
        noise_scale = 0.8 + rng.random() * 0.6  # vary cluster tightness

        topic_embeddings = (
            center[None, :] +
            rng.standard_normal((samples_per_topic, embedding_dim)) * noise_scale
        )
        embeddings.append(topic_embeddings)
        true_labels.extend([topic_idx] * samples_per_topic)
        sample_texts.extend([f"[{topic}] memory entry {i}" for i in range(samples_per_topic)])

    embeddings_arr = np.vstack(embeddings)
    labels_arr = np.array(true_labels)

    # Shuffle
    perm = rng.permutation(len(labels_arr))
    return embeddings_arr[perm], labels_arr[perm], [sample_texts[i] for i in perm]


def apply_pca(
    embeddings: np.ndarray,
    n_components: int = 2,
    n_components_full: int = 20,
) -> Tuple[np.ndarray, np.ndarray, PCA]:
    """
    Applies PCA in two steps:
      1. Reduce to n_components_full dims (for clustering — retains more info)
      2. Reduce to n_components dims (for visualisation)

    Returns
    -------
    X_cluster : (n_samples, n_components_full) — for clustering
    X_vis     : (n_samples, n_components)      — for 2D visualisation
    pca_full  : fitted PCA object
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(embeddings)

    pca_full = PCA(n_components=n_components_full, random_state=42)
    X_cluster = pca_full.fit_transform(X_scaled)

    pca_vis = PCA(n_components=n_components, random_state=42)
    X_vis = pca_vis.fit_transform(X_scaled)

    return X_cluster, X_vis, pca_full


def cluster_kmeans(X: np.ndarray, n_clusters: int) -> np.ndarray:
    """K-Means clustering."""
    model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    return model.fit_predict(X)


def cluster_hierarchical(X: np.ndarray, n_clusters: int) -> np.ndarray:
    """Agglomerative (Hierarchical) clustering."""
    model = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
    return model.fit_predict(X)


def cluster_dbscan(X: np.ndarray) -> np.ndarray:
    """
    DBSCAN clustering (auto-determines n_clusters).
    eps and min_samples tuned for the PCA-reduced space.
    """
    model = DBSCAN(eps=1.8, min_samples=5, n_jobs=-1)
    return model.fit_predict(X)


def evaluate_clustering(X: np.ndarray, labels: np.ndarray) -> float:
    """
    Computes Silhouette Score. Returns -1 if only one cluster found
    (degenerate DBSCAN result).
    """
    unique = np.unique(labels[labels >= 0])
    if len(unique) < 2:
        return -1.0
    # Exclude noise points (label = -1 from DBSCAN)
    mask = labels >= 0
    if mask.sum() < 2:
        return -1.0
    return float(silhouette_score(X[mask], labels[mask], sample_size=500, random_state=42))


def print_cluster_sizes(labels: np.ndarray, method_name: str) -> None:
    """Prints a summary of cluster sizes."""
    unique, counts = np.unique(labels, return_counts=True)
    table = Table(
        title=f"[bold gold1]Cluster Sizes — {method_name}[/]",
        box=box.SIMPLE,
        header_style="bold cyan",
    )
    table.add_column("Cluster ID", justify="center")
    table.add_column("Size", justify="right")
    table.add_column("Interpretation", style="dim")

    topic_names = MEMORY_TOPICS + ["Noise (outliers)"]
    for cid, cnt in zip(unique, counts):
        name = topic_names[cid] if cid >= 0 else "Noise (DBSCAN outliers)"
        table.add_row(str(cid), str(cnt), name[:40])
    console.print(table)


def describe_clusters(labels: np.ndarray, texts: List[str]) -> None:
    """Shows 3 example memories from each cluster."""
    console.print("\n[bold cyan]Sample Memory Entries per Cluster:[/]")
    unique_labels = sorted(set(labels))
    for cid in unique_labels[:N_TOPICS]:
        indices = [i for i, l in enumerate(labels) if l == cid][:3]
        console.print(f"\n  [bold gold1]Cluster {cid}[/] ({MEMORY_TOPICS[cid] if cid < N_TOPICS else 'outlier'}):")
        for idx in indices:
            console.print(f"    • {texts[idx]}")


def run() -> Tuple[np.ndarray, np.ndarray]:
    """
    Main entry point. Generates embeddings, applies PCA, clusters with all
    three methods, evaluates, and returns (best_labels, X_vis).
    """
    console.rule("[bold gold1]M.O.N.D.A.Y. — Component 2.3: Memory Clustering[/]")
    console.print("\n[dim]CLO04 · Clustering · Lab 21–26[/]\n")

    # ── Generate Embeddings ────────────────────────────────────────────────────
    console.print("[cyan]► Generating synthetic memory embeddings...[/]")
    embeddings, true_labels, texts = generate_memory_embeddings(n_samples=700, embedding_dim=64)
    console.print(f"  Embeddings shape : {embeddings.shape}")
    console.print(f"  Ground-truth topics: {N_TOPICS}\n")

    # ── PCA ───────────────────────────────────────────────────────────────────
    console.print("[cyan]► Applying PCA (64→20 dims for clustering, 64→2 for vis)...[/]")
    X_cluster, X_vis, pca_full = apply_pca(embeddings, n_components=2, n_components_full=20)
    var_20 = pca_full.explained_variance_ratio_.sum()
    console.print(f"  Variance explained by top 20 PCs: [bold]{var_20:.1%}[/]\n")

    # ── Clustering ────────────────────────────────────────────────────────────
    console.print("[cyan]► Clustering with K-Means, Hierarchical, DBSCAN...[/]\n")
    labels_km = cluster_kmeans(X_cluster, n_clusters=N_TOPICS)
    labels_hc = cluster_hierarchical(X_cluster, n_clusters=N_TOPICS)
    labels_db = cluster_dbscan(X_cluster)

    # ── Evaluation ────────────────────────────────────────────────────────────
    scores = {
        "K-Means (k=7)": evaluate_clustering(X_cluster, labels_km),
        "Hierarchical (Ward, k=7)": evaluate_clustering(X_cluster, labels_hc),
        "DBSCAN (eps=1.8, min=5)": evaluate_clustering(X_cluster, labels_db),
    }

    eval_table = Table(
        title="[bold gold1]Clustering Evaluation — Silhouette Scores[/]",
        box=box.ROUNDED,
        header_style="bold cyan",
    )
    eval_table.add_column("Method", style="bold white", min_width=28)
    eval_table.add_column("Silhouette Score", justify="right")
    eval_table.add_column("N Clusters Found", justify="right")
    eval_table.add_column("Status", justify="center")

    best_method = max(scores, key=lambda k: scores[k])
    for name, score in scores.items():
        labels_map = {
            "K-Means (k=7)": labels_km,
            "Hierarchical (Ward, k=7)": labels_hc,
            "DBSCAN (eps=1.8, min=5)": labels_db,
        }
        n_found = len(set(labels_map[name]) - {-1})
        is_best = name == best_method
        style = "bold green" if is_best else ""
        mark = " ★" if is_best else ""
        status = "[green]Valid[/]" if score > 0 else "[red]Degenerate[/]"
        eval_table.add_row(
            f"{name}{mark}", f"{score:.4f}", str(n_found), status, style=style
        )

    console.print(eval_table)

    # ── Best Cluster Breakdown ─────────────────────────────────────────────────
    best_labels_map = {
        "K-Means (k=7)": labels_km,
        "Hierarchical (Ward, k=7)": labels_hc,
        "DBSCAN (eps=1.8, min=5)": labels_db,
    }
    best_labels = best_labels_map[best_method]

    console.print(f"\n[bold green]► Best method: {best_method}[/]")
    print_cluster_sizes(best_labels, best_method)
    describe_clusters(best_labels, texts)

    # ── Proactive Suggestion Demo ──────────────────────────────────────────────
    console.rule("[bold gold1]Proactive Suggestion Demo[/]")
    suggestion_table = Table(box=box.SIMPLE, header_style="bold cyan",
                              title="[bold gold1]What M.O.N.D.A.Y. Would Suggest[/]")
    suggestion_table.add_column("Detected Topic Cluster", min_width=32)
    suggestion_table.add_column("Proactive Suggestion", style="italic")

    unique, counts = np.unique(best_labels[best_labels >= 0], return_counts=True)
    for cid, cnt in zip(unique[:5], counts[:5]):
        topic = MEMORY_TOPICS[cid] if cid < N_TOPICS else "Unknown"
        suggestion = f"You have {cnt} memory entries about '{topic}'. Want me to summarise or organise them?"
        suggestion_table.add_row(topic, suggestion)

    console.print(suggestion_table)

    console.print(
        "\n[bold green]✓ Component 2.3 complete.[/] "
        f"Best clustering: [bold]{best_method}[/] — memory retrieval optimised.\n"
    )
    return best_labels, X_vis


if __name__ == "__main__":
    run()
