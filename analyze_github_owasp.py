from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path

import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

import matplotlib.pyplot as plt


OWASP_ID_PATTERN = re.compile(r"^OWASP/\d+\.\d+\.\d+$")
CATEGORY_PATTERN = re.compile(r"^OWASP/(\d+)\.")
ALERT_MARKER_PATTERN = re.compile(r"\\\[![^\]]*\]")
ADMONITION_PATTERN = re.compile(r"\[!(WARNING|NOTE|TIP|IMPORTANT|CAUTION)\]")
REDACTED_EXAMPLE_PATTERN = re.compile(r"\[[A-Z]+@[^\]]+\]")
DEFAULT_GITHUB_FILE = "githubxowasp.jsonl"
DEFAULT_OWASP_AUDIENCE_FILE = "discussion_audience_distribution.csv"
DEFAULT_OUTPUT_PREFIX = "github_owasp_analysis"
NON_ACTIONABLE_AUDIENCE = "Non Actionable"
OVERLAP_ORDER = [
    "OWASP actionable and GitHub actionable",
    "Not OWASP actionable and GitHub actionable",
    "OWASP actionable and not GitHub actionable",
    "Not OWASP actionable and not GitHub actionable",
]
DOCUMENT_CATEGORY_DENOMINATORS = {
    "actions": 200,
    "code-security": 419,
    "packages": 20,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze GitHub security advice against OWASP actionability outputs."
    )
    parser.add_argument("--github-file", default=DEFAULT_GITHUB_FILE)
    parser.add_argument("--owasp-audience-file", default=DEFAULT_OWASP_AUDIENCE_FILE)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    return parser.parse_args()


def flatten_labels(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        flattened: list[str] = []
        for item in value:
            flattened.extend(flatten_labels(item))
        return flattened
    raise TypeError(f"Unsupported final_classification value: {value!r}")


def extract_owasp_ids(labels: list[str]) -> list[str]:
    return sorted(label for label in labels if OWASP_ID_PATTERN.match(label))


def extract_category_key(owasp_id: str) -> str | None:
    match = CATEGORY_PATTERN.match(owasp_id)
    return match.group(1) if match else None


def load_github_dataframe(path: str) -> pd.DataFrame:
    github_df = pd.read_json(path, lines=True)
    github_df["final_labels"] = github_df["final_classification"].apply(flatten_labels)
    github_df["owasp_classification"] = github_df["owasp_classification"].apply(flatten_labels)
    github_df["final_owasp_ids"] = github_df["final_labels"].apply(extract_owasp_ids)
    github_df["candidate_owasp_ids"] = github_df["owasp_classification"].apply(extract_owasp_ids)
    github_df["admonition_types"] = github_df["extraction_text"].fillna("").apply(
        lambda text: ADMONITION_PATTERN.findall(text)
    )
    github_df["has_alert_marker"] = github_df["extraction_text"].fillna("").str.contains(ALERT_MARKER_PATTERN)
    github_df["has_redacted_example"] = github_df["extraction_text"].fillna("").str.contains(REDACTED_EXAMPLE_PATTERN)
    github_df["has_plus"] = github_df["final_labels"].apply(lambda labels: "+" in labels)
    github_df["other_markers"] = github_df["final_labels"].apply(
        lambda labels: sorted(
            {
                label
                for label in labels
                if label not in {"+"} and not OWASP_ID_PATTERN.match(label)
            }
        )
    )
    github_df["has_other_marker"] = github_df["other_markers"].apply(bool)
    github_df["is_empty"] = github_df["final_labels"].apply(lambda labels: len(labels) == 0)
    github_df["is_mapped_actionable"] = github_df["final_owasp_ids"].apply(bool)
    github_df["is_extra_actionable"] = github_df["has_plus"]
    github_df["is_actionable"] = (
        github_df["is_mapped_actionable"] | github_df["is_extra_actionable"]
    )
    github_df["is_extra_only_actionable"] = (
        github_df["is_extra_actionable"] & ~github_df["is_mapped_actionable"]
    )
    github_df["n_final_owasp_ids"] = github_df["final_owasp_ids"].apply(len)
    github_df["n_candidate_owasp_ids"] = github_df["candidate_owasp_ids"].apply(len)
    github_df["source_category"] = github_df["document_id"].str.split("/").str[0]
    github_df["primary_category_key"] = github_df["final_owasp_ids"].apply(
        lambda ids: extract_category_key(ids[0]) if ids else None
    )
    github_df["document_category_keys"] = github_df["final_owasp_ids"].apply(
        lambda ids: sorted({extract_category_key(owasp_id) for owasp_id in ids if extract_category_key(owasp_id)})
    )
    github_df["candidate_set"] = github_df["candidate_owasp_ids"].apply(set)
    github_df["final_set"] = github_df["final_owasp_ids"].apply(set)
    github_df["mapping_relation"] = github_df.apply(classify_mapping_relation, axis=1)
    return github_df


def validate_final_classification(github_df: pd.DataFrame) -> None:
    invalid_rows = github_df.loc[github_df["has_other_marker"]]
    if invalid_rows.empty:
        return

    first_invalid = invalid_rows.iloc[0]
    raise ValueError(
        "Unsupported final_classification marker(s) found in "
        f"{first_invalid['document_id']}: {first_invalid['other_markers']}. "
        "Expected only [], ['+'], or OWASP IDs."
    )


def classify_mapping_relation(row: pd.Series) -> str:
    final_set = row["final_set"]
    candidate_set = row["candidate_set"]
    if not row["is_mapped_actionable"]:
        if row["is_extra_actionable"]:
            return "extra-actionable"
        if row["has_other_marker"]:
            return "other-marker"
        return "not-actionable"
    if final_set == candidate_set:
        return "exact-match"
    if final_set < candidate_set:
        return "subset-of-candidates"
    if candidate_set < final_set:
        return "superset-of-candidates"
    if final_set & candidate_set:
        return "partial-overlap"
    return "disjoint"


def load_owasp_dataframe(path: str) -> pd.DataFrame:
    owasp_df = pd.read_csv(path)
    owasp_df["is_actionable"] = owasp_df["audience"] != NON_ACTIONABLE_AUDIENCE
    owasp_df["category_key"] = owasp_df["_id"].str.extract(r"OWASP/(\d+)\.")
    return owasp_df


def build_overlap_dataframe(github_df: pd.DataFrame, owasp_df: pd.DataFrame) -> pd.DataFrame:
    github_ids = pd.Series(
        sorted({owasp_id for ids in github_df["final_owasp_ids"] for owasp_id in ids}),
        name="_id",
    )
    owasp_ids = pd.Series(sorted(owasp_df["_id"].unique()), name="_id")
    universe_df = pd.DataFrame({"_id": pd.concat([github_ids, owasp_ids], ignore_index=True).drop_duplicates()})

    github_actionable_ids = set(github_ids.tolist())
    owasp_actionable_ids = set(owasp_df.loc[owasp_df["is_actionable"], "_id"])

    universe_df["github_actionable"] = universe_df["_id"].isin(github_actionable_ids)
    universe_df["owasp_actionable"] = universe_df["_id"].isin(owasp_actionable_ids)
    universe_df["category_key"] = universe_df["_id"].str.extract(r"OWASP/(\d+)\.")
    universe_df["overlap_bucket"] = universe_df.apply(classify_overlap_bucket, axis=1)
    return universe_df.sort_values("_id").reset_index(drop=True)


def classify_overlap_bucket(row: pd.Series) -> str:
    if row["owasp_actionable"] and row["github_actionable"]:
        return "OWASP actionable and GitHub actionable"
    if not row["owasp_actionable"] and row["github_actionable"]:
        return "Not OWASP actionable and GitHub actionable"
    if row["owasp_actionable"] and not row["github_actionable"]:
        return "OWASP actionable and not GitHub actionable"
    return "Not OWASP actionable and not GitHub actionable"


def build_summary(github_df: pd.DataFrame, owasp_df: pd.DataFrame, overlap_df: pd.DataFrame) -> dict:
    mapped_df = github_df.loc[github_df["is_mapped_actionable"]].copy()
    final_id_series = mapped_df["final_owasp_ids"].explode().dropna()
    final_category_series = final_id_series.str.extract(r"OWASP/(\d+)\.")[0].dropna()
    mapped_id_counts = final_id_series.value_counts()

    all_categories = [str(index) for index in range(1, 11)]
    included_categories = sorted(set(final_category_series), key=int)
    missing_categories = [category for category in all_categories if category not in included_categories]

    top_owasp_ids = (
        mapped_id_counts
        .head(5)
        .rename_axis("owasp_id")
        .reset_index(name="count")
        .to_dict(orient="records")
    )
    top_percent_count = max(1, math.ceil(mapped_id_counts.shape[0] * 0.05))
    top_5_percent_ids = (
        mapped_id_counts
        .head(top_percent_count)
        .rename_axis("owasp_id")
        .reset_index(name="count")
        .to_dict(orient="records")
    )

    top_documents = (
        github_df.loc[github_df["is_actionable"], "document_id"]
        .value_counts()
        .head(5)
        .rename_axis("document_id")
        .reset_index(name="actionable_excerpt_count")
        .to_dict(orient="records")
    )
    source_category_stats_df = (
        github_df.assign(
            actionable_excerpt=github_df["is_actionable"].astype(int),
            non_actionable_excerpt=github_df["is_empty"].astype(int),
            special_excerpt=(~github_df["is_empty"] & ~github_df["is_actionable"]).astype(int),
        )
        .groupby("source_category", as_index=False)[
            ["actionable_excerpt", "non_actionable_excerpt", "special_excerpt"]
        ]
        .sum()
    )
    source_category_stats_df["total_excerpts"] = (
        source_category_stats_df["actionable_excerpt"]
        + source_category_stats_df["non_actionable_excerpt"]
        + source_category_stats_df["special_excerpt"]
    )
    source_category_stats_df["n_documents"] = source_category_stats_df["source_category"].map(
        DOCUMENT_CATEGORY_DENOMINATORS
    )
    source_category_stats_df["mean_advices_per_document"] = (
        source_category_stats_df["total_excerpts"] / source_category_stats_df["n_documents"]
    )
    source_category_stats = source_category_stats_df.sort_values("source_category").to_dict(orient="records")

    overlap_counts = (
        overlap_df["overlap_bucket"]
        .value_counts()
        .reindex(OVERLAP_ORDER, fill_value=0)
        .astype(int)
    )
    overlap_proportions = (overlap_counts / overlap_counts.sum()).round(6)

    return {
        "github": {
            "n_total_excerpts": int(len(github_df)),
            "n_actionable_excerpts": int(github_df["is_actionable"].sum()),
            "n_non_actionable_excerpts": int(github_df["is_empty"].sum()),
            "n_extra_actionable_excerpts": int(github_df["is_extra_actionable"].sum()),
            "n_extra_only_actionable_excerpts": int(github_df["is_extra_only_actionable"].sum()),
            "n_mapped_actionable_excerpts": int(github_df["is_mapped_actionable"].sum()),
            "n_other_marker_excerpts": int(github_df["has_other_marker"].sum()),
            "other_marker_counts": (
                github_df.loc[github_df["has_other_marker"], "other_markers"]
                .explode()
                .value_counts()
                .sort_index()
                .to_dict()
            ),
            "n_unique_mapped_owasp_ids": int(final_id_series.nunique()),
            "n_total_mapped_owasp_references": int(final_id_series.shape[0]),
            "avg_mapped_ids_per_mapped_excerpt": round(float(mapped_df["n_final_owasp_ids"].mean()), 3),
            "n_extractions_with_alert_markers": int(github_df["has_alert_marker"].sum()),
            "alert_admonition_counts": (
                github_df["admonition_types"]
                .explode()
                .dropna()
                .value_counts()
                .sort_index()
                .to_dict()
            ),
            "n_extractions_with_redacted_examples": int(github_df["has_redacted_example"].sum()),
            "mapping_relation_counts": github_df["mapping_relation"].value_counts().sort_index().to_dict(),
            "top_5_mapped_owasp_ids": top_owasp_ids,
            "top_5_percent_mapped_owasp_ids": top_5_percent_ids,
            "included_categories": [f"SEC-{category}" for category in included_categories],
            "missing_categories": [f"SEC-{category}" for category in missing_categories],
            "category_frequency": (
                final_category_series.value_counts()
                .sort_index(key=lambda index: index.astype(int))
                .to_dict()
            ),
            "source_category_stats": source_category_stats,
            "top_5_documents_by_actionable_excerpts": top_documents,
        },
        "owasp": {
            "n_total_ids": int(owasp_df["_id"].nunique()),
            "n_actionable_ids": int(owasp_df.loc[owasp_df["is_actionable"], "_id"].nunique()),
            "n_non_actionable_ids": int(owasp_df.loc[~owasp_df["is_actionable"], "_id"].nunique()),
        },
        "overlap": {
            "n_ids_in_union": int(len(overlap_df)),
            "counts": overlap_counts.to_dict(),
            "proportions": overlap_proportions.to_dict(),
        },
    }


def write_stats_tables(
    github_df: pd.DataFrame,
    overlap_df: pd.DataFrame,
    output_prefix: str,
) -> None:
    mapped_id_counts_df = (
        github_df.loc[github_df["is_mapped_actionable"], "final_owasp_ids"]
        .explode()
        .dropna()
        .value_counts()
        .rename_axis("owasp_id")
        .reset_index(name="count")
    )
    mapped_id_counts_df["category_key"] = mapped_id_counts_df["owasp_id"].str.extract(r"OWASP/(\d+)\.")
    mapped_id_counts_df.to_csv(f"{output_prefix}_mapped_id_counts.csv", index=False)

    overlap_df.to_csv(f"{output_prefix}_overlap_by_id.csv", index=False)

    github_excerpt_df = github_df[
        [
            "document_id",
            "final_labels",
            "final_owasp_ids",
            "is_actionable",
            "is_extra_actionable",
            "is_mapped_actionable",
            "is_extra_only_actionable",
            "has_other_marker",
            "other_markers",
            "mapping_relation",
        ]
    ].copy()
    github_excerpt_df["final_labels"] = github_excerpt_df["final_labels"].apply(json.dumps)
    github_excerpt_df["final_owasp_ids"] = github_excerpt_df["final_owasp_ids"].apply(json.dumps)
    github_excerpt_df["other_markers"] = github_excerpt_df["other_markers"].apply(json.dumps)
    github_excerpt_df.to_csv(f"{output_prefix}_github_excerpt_summary.csv", index=False)


def plot_overlap_proportions(overlap_df: pd.DataFrame, output_path: str) -> None:
    overlap_counts_by_category = (
        overlap_df.assign(category_label="SEC-" + overlap_df["category_key"].astype(str))
        .groupby(["category_label", "overlap_bucket"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=OVERLAP_ORDER, fill_value=0)
        .sort_index(key=lambda index: index.str.extract(r"SEC-(\d+)")[0].astype(int))
    )
    proportions_by_category = overlap_counts_by_category.div(
        overlap_counts_by_category.sum(axis=1),
        axis=0,
    )
    fills = {
        "OWASP actionable and GitHub actionable": {"color": "#F2F2F2", "hatch": None},
        "Not OWASP actionable and GitHub actionable": {"color": "#D9D9D9", "hatch": None},
        "OWASP actionable and not GitHub actionable": {"color": "#BFBFBF", "hatch": None},
        "Not OWASP actionable and not GitHub actionable": {"color": "#8C8C8C", "hatch": None},
    }

    fig_height = max(5.4, 0.72 * len(proportions_by_category))
    fig, axis = plt.subplots(figsize=(12, fig_height))
    left = pd.Series(0.0, index=proportions_by_category.index)

    for bucket in OVERLAP_ORDER:
        widths = proportions_by_category[bucket]
        bars = axis.barh(
            proportions_by_category.index,
            widths,
            left=left,
            color=fills[bucket]["color"],
            hatch=fills[bucket]["hatch"],
            edgecolor="black",
            linewidth=0.8,
            height=0.7,
            label=bucket,
        )
        counts = overlap_counts_by_category[bucket]
        for bar, width, count in zip(bars, widths, counts, strict=False):
            if width < 0.08:
                continue
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_y() + bar.get_height() / 2,
                f"{int(count)} ({width * 100:.0f}%)",
                ha="center",
                va="center",
                fontsize=16,
            )
        left = left + widths

    axis.set_xlim(0, 1)
    axis.set_xlabel("Proportion of OWASP recommendations within per category", fontsize=16)
    axis.set_ylabel("OWASP category", fontsize=16)
    axis.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    axis.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    axis.tick_params(axis="both", labelsize=15)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="x", linestyle=":", alpha=0.4)
    legend = axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=False)
    for text in legend.get_texts():
        text.set_text(text.get_text().replace("GitHub","GA"))
        text.set_fontsize(17)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def format_stdout_summary(summary: dict) -> str:
    github = summary["github"]
    owasp = summary["owasp"]
    overlap = summary["overlap"]
    lines = [
        "GitHub vs OWASP totals",
        (
            "GitHub excerpts: "
            f"{github['n_total_excerpts']} total, "
            f"{github['n_actionable_excerpts']} actionable, "
            f"{github['n_mapped_actionable_excerpts']} mapped, "
            f"{github['n_extra_only_actionable_excerpts']} extra-only, "
            f"{github['n_non_actionable_excerpts']} non-actionable"
        ),
        (
            "GitHub mapped OWASP IDs: "
            f"{github['n_unique_mapped_owasp_ids']} unique IDs, "
            f"{github['n_total_mapped_owasp_references']} total references"
        ),
        (
            "Extraction text markers: "
            f"{github['n_extractions_with_alert_markers']} with ![...] alerts, "
            f"{github['n_extractions_with_redacted_examples']} with [REDACTED@x]-style examples"
        ),
        (
            "OWASP IDs: "
            f"{owasp['n_total_ids']} total, "
            f"{owasp['n_actionable_ids']} actionable, "
            f"{owasp['n_non_actionable_ids']} non-actionable"
        ),
        (
            "Overlap over OWASP-ID universe: "
            f"{overlap['n_ids_in_union']} IDs total"
        ),
        "GitHub source-category totals:",
    ]

    for row in github["source_category_stats"]:
        mean_value = row["mean_advices_per_document"]
        mean_text = f"{mean_value:.2f}" if pd.notna(mean_value) else "n/a"
        n_documents = row["n_documents"]
        n_text = str(int(n_documents)) if pd.notna(n_documents) else "n/a"
        lines.append(
            f"- {row['source_category']}: "
            f"{int(row['actionable_excerpt'])} actionable, "
            f"{int(row['non_actionable_excerpt'])} non-actionable, "
            f"{int(row['special_excerpt'])} special, "
            f"{int(row['total_excerpts'])} total, "
            f"mean advices/document={mean_text} (N={n_text})"
        )

    if github["alert_admonition_counts"]:
        lines.append("GitHub admonition counts:")
        for admonition, count in github["alert_admonition_counts"].items():
            lines.append(f"- {admonition}: {count}")

    lines.extend(
        [
        "Top 5% most-mentioned mapped OWASP IDs in GitHub:",
        ]
    )

    for row in github["top_5_percent_mapped_owasp_ids"]:
        lines.append(f"- {row['owasp_id']}: {row['count']}")

    lines.append("Overlap buckets:")
    for bucket in OVERLAP_ORDER:
        lines.append(
            f"- {bucket}: {overlap['counts'][bucket]} ({overlap['proportions'][bucket] * 100:.1f}%)"
        )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    output_prefix = args.output_prefix

    github_df = load_github_dataframe(args.github_file)
    validate_final_classification(github_df)
    owasp_df = load_owasp_dataframe(args.owasp_audience_file)
    overlap_df = build_overlap_dataframe(github_df, owasp_df)
    summary = build_summary(github_df, owasp_df, overlap_df)

    Path(f"{output_prefix}_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_stats_tables(github_df, overlap_df, output_prefix)
    plot_overlap_proportions(overlap_df, f"{output_prefix}_overlap_proportions.pdf")

    print(format_stdout_summary(summary))


if __name__ == "__main__":
    main()
