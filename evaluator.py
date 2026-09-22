from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from statistics import mean
import os

import pandas as pd
from pymongo import MongoClient
from sklearn.metrics import cohen_kappa_score

from coding import CodingLabels, CodingTree, QuestionStep
from dotenv import load_dotenv

# Assumption used for the actionability metric:
# the actionable practice tags are the practice classes that prescribe
# something a developer or specialist could carry out.
ACTIONABLE_TAGS = {"P3", "P4", "P5", "P6"}

AUDIENCE_BY_TAG = {
    "P4": "Security Expert",
    "P5": "IT-Specialist",
    "P6": "End-User",
}
NON_ACTIONABLE_AUDIENCE = "Non Actionable"
AUDIENCE_ORDER = ["End-User", "IT-Specialist", "Security Expert", NON_ACTIONABLE_AUDIENCE]


@dataclass(frozen=True)
class PathStep:
    question: str
    answer: str


@dataclass(frozen=True)
class ComparedPaths:
    matched_tag_a: str
    matched_tag_b: str
    path_a: tuple[PathStep, ...]
    path_b: tuple[PathStep, ...]
    common_prefix_length: int
    divergence_question: str | None


def fetch_collection_dataframe(uri: str, database: str, collection: str) -> pd.DataFrame:
    client = MongoClient(uri)
    documents = list(client[database][collection].find())
    if not documents:
        return pd.DataFrame(columns=["_id", "advice", "codes"])
    return pd.DataFrame(documents)


def normalize_codes_dataframe(documents_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    all_coders: set[str] = set()
    columns = list(documents_df.columns)

    for values in documents_df.itertuples(index=False, name=None):
        row = dict(zip(columns, values, strict=False))
        codes = row.get("codes") or {}
        all_coders.update(codes.keys())

        normalized_row = {
            "_id": row.get("_id"),
            "advice": row.get("advice"),
            "codes": codes,
        }
        for coder_id, coder_codes in codes.items():
            tags = extract_tags(coder_codes)
            normalized_row[f"{coder_id}_tags"] = tuple(tags)
            normalized_row[f"{coder_id}_tag_count"] = len(tags)
            normalized_row[f"{coder_id}_tag1"] = tags[0] if tags else None
            normalized_row[f"{coder_id}_tag2"] = tags[1] if len(tags) > 1 else None
        rows.append(normalized_row)

    normalized_df = pd.DataFrame(rows)
    for coder_id in sorted(all_coders):
        defaults = {
            f"{coder_id}_tags": tuple(),
            f"{coder_id}_tag_count": 0,
            f"{coder_id}_tag1": None,
            f"{coder_id}_tag2": None,
        }
        for column, default in defaults.items():
            if column not in normalized_df.columns:
                normalized_df[column] = default

    return normalized_df


def infer_coders(normalized_df: pd.DataFrame) -> list[str]:
    return sorted(
        column[:-5]
        for column in normalized_df.columns
        if column.endswith("_tags")
    )


def extract_tags(coder_codes: dict | None) -> list[str]:
    if not coder_codes:
        return []
    return [tag for tag in (coder_codes.get("tag1"), coder_codes.get("tag2")) if tag]


def extract_owasp_category(item_id: object) -> str | None:
    if item_id is None:
        return None

    item_id_str = str(item_id).rsplit("/", 1)[-1]
    category = item_id_str.split(".", 1)[0]
    return category or None


def translate_tags(tags: tuple[str, ...] | list[str]) -> list[str]:
    return [CodingLabels.get(tag, tag) for tag in tags]


def build_leaf_paths(root) -> dict[str, tuple[PathStep, ...]]:
    leaf_paths: dict[str, tuple[PathStep, ...]] = {}

    def walk(node, current_path: tuple[PathStep, ...]) -> None:
        if node.is_leaf():
            leaf_paths[node.label] = current_path
            return

        question: QuestionStep = node.question()
        walk(node.no, current_path + (PathStep(question.code, "No"),))
        walk(node.yes, current_path + (PathStep(question.code, "Yes"),))

    walk(root, tuple())
    return leaf_paths


def common_prefix_length(path_a: tuple[PathStep, ...], path_b: tuple[PathStep, ...]) -> int:
    prefix_length = 0
    for step_a, step_b in zip(path_a, path_b):
        if step_a != step_b:
            break
        prefix_length += 1
    return prefix_length


def infer_divergence_question(
    path_a: tuple[PathStep, ...],
    path_b: tuple[PathStep, ...],
    prefix_length: int,
) -> str | None:
    if prefix_length >= len(path_a) and prefix_length >= len(path_b):
        return None
    if prefix_length < len(path_a):
        return path_a[prefix_length].question
    if prefix_length < len(path_b):
        return path_b[prefix_length].question
    return None


def compare_paths_for_nonagreement(
    tags_a: list[str],
    tags_b: list[str],
    leaf_paths: dict[str, tuple[PathStep, ...]],
) -> ComparedPaths:
    candidates = []
    for tag_a, tag_b in product(tags_a, tags_b):
        path_a = leaf_paths[tag_a]
        path_b = leaf_paths[tag_b]
        prefix_length = common_prefix_length(path_a, path_b)
        candidates.append(
            ComparedPaths(
                matched_tag_a=tag_a,
                matched_tag_b=tag_b,
                path_a=path_a,
                path_b=path_b,
                common_prefix_length=prefix_length,
                divergence_question=infer_divergence_question(path_a, path_b, prefix_length),
            )
        )

    # Operational definition:
    # for SD and DD nonagreements, use the path pair with the longest
    # shared prefix to locate the most downstream divergence point.
    return max(candidates, key=lambda candidate: candidate.common_prefix_length)


def comparison_type(tags_a: list[str], tags_b: list[str]) -> str:
    return f"{'S' if len(tags_a) == 1 else 'D'}{'S' if len(tags_b) == 1 else 'D'}"


def compute_t_agreement(tags_a: list[str], tags_b: list[str]) -> bool:
    if len(tags_a) == 1 and len(tags_b) == 1:
        return tags_a[0] == tags_b[0]
    return bool(set(tags_a) & set(tags_b))


def is_actionable(tag: str) -> bool:
    return tag in ACTIONABLE_TAGS


def tags_to_audience(tags: list[str] | tuple[str, ...]) -> str:
    actionable_audiences = {
        AUDIENCE_BY_TAG[tag]
        for tag in tags
        if tag in AUDIENCE_BY_TAG
    }
    if not actionable_audiences:
        return NON_ACTIONABLE_AUDIENCE
    if len(actionable_audiences) > 1:
        raise ValueError(f"Multiple actionable audiences found for tags: {tags}")
    return next(iter(actionable_audiences))


def category_sort_key(category: str) -> tuple[int, str]:
    digits = "".join(character for character in str(category) if character.isdigit())
    if digits:
        return (0, f"{int(digits):04d}")
    return (1, str(category))


def format_category_label(category: str | int | None) -> str:
    if category is None or pd.isna(category):
        return "Unknown"
    digits = "".join(character for character in str(category) if character.isdigit())
    if digits:
        return f"SEC-{int(digits)}"
    return str(category)


def normalize_category_key(category: str | int | None) -> str | None:
    if category is None:
        return None
    category_str = str(category).strip()
    if not category_str:
        return None
    digits = "".join(character for character in category_str if character.isdigit())
    return str(int(digits)) if digits else category_str


def parse_resolved_audience(resolved_note: str | None) -> str | None:
    if not resolved_note:
        return None

    normalized = resolved_note.casefold()
    if "security expert" in normalized:
        return "Security Expert"
    if "it specialist" in normalized:
        return "IT-Specialist"
    if "end-user" in normalized or "end user" in normalized:
        return "End-User"

    non_actionable_markers = (
        "non actionable",
        "non-actionable",
        "outcome",
        "general procedure",
        "general policy",
        "security principle",
        "unfocused",
        "unclear",
        "not security related",
        "not security",
        "incompletely specified",
    )
    if any(marker in normalized for marker in non_actionable_markers):
        return NON_ACTIONABLE_AUDIENCE

    return None


def load_resolution_map(path: str | None) -> dict[str, str]:
    if not path:
        return {}

    with open(path, encoding="utf-8") as file:
        data = json.load(file)

    resolution_map: dict[str, str] = {}
    for row in data:
        audience = parse_resolved_audience(row.get("resolved"))
        if audience is not None:
            resolution_map[str(row["_id"])] = audience
    return resolution_map


def compute_actionability_agreement(tags_a: list[str], tags_b: list[str]) -> bool:
    if len(tags_a) == 1 and len(tags_b) == 1:
        return is_actionable(tags_a[0]) == is_actionable(tags_b[0])
    if len(tags_a) == 1:
        return any(is_actionable(tags_a[0]) == is_actionable(tag_b) for tag_b in tags_b)
    if len(tags_b) == 1:
        return any(is_actionable(tag_a) == is_actionable(tags_b[0]) for tag_a in tags_a)
    return any(
        is_actionable(tag_a) == is_actionable(tag_b)
        for tag_a, tag_b in product(tags_a, tags_b)
    )


def build_pairwise_dataframe(
    normalized_df: pd.DataFrame,
    coder_a: str,
    coder_b: str,
) -> pd.DataFrame:
    leaf_paths = build_leaf_paths(CodingTree)
    rows: list[dict] = []
    columns = list(normalized_df.columns)
    tags_a_column = f"{coder_a}_tags"
    tags_b_column = f"{coder_b}_tags"

    for values in normalized_df.itertuples(index=False, name=None):
        row = dict(zip(columns, values, strict=False))
        tags_a = list(row.get(tags_a_column, ()) or ())
        tags_b = list(row.get(tags_b_column, ()) or ())
        if not tags_a or not tags_b:
            continue

        compared = compare_paths_for_nonagreement(tags_a, tags_b, leaf_paths)
        t_agreement = compute_t_agreement(tags_a, tags_b)

        rows.append(
            {
                "_id": row["_id"],
                "owasp_category": extract_owasp_category(row["_id"]),
                "advice": row["advice"],
                "coder_a": coder_a,
                "coder_b": coder_b,
                "tags_a": tuple(tags_a),
                "tags_b": tuple(tags_b),
                "comparison_type": comparison_type(tags_a, tags_b),
                "t_agreement": t_agreement,
                "exact_tag_set_agreement": set(tags_a) == set(tags_b),
                "actionability_agreement": compute_actionability_agreement(tags_a, tags_b),
                "matched_tag_a": compared.matched_tag_a,
                "matched_tag_b": compared.matched_tag_b,
                "common_prefix_length": compared.common_prefix_length,
                "divergence_question": None if t_agreement else compared.divergence_question,
                "path_a": compared.path_a,
                "path_b": compared.path_b,
                "path_a_json": json.dumps([asdict(step) for step in compared.path_a]),
                "path_b_json": json.dumps([asdict(step) for step in compared.path_b]),
            }
        )

    return pd.DataFrame(rows)


def compute_question_exposure_counts(pairwise_df: pd.DataFrame) -> dict[str, int]:
    exposure_counts: dict[str, int] = {}

    for row in pairwise_df.itertuples(index=False):
        path_a: tuple[PathStep, ...] = row.path_a
        path_b: tuple[PathStep, ...] = row.path_b
        prefix_length = row.common_prefix_length

        for step in path_a[:prefix_length]:
            exposure_counts[step.question] = exposure_counts.get(step.question, 0) + 1

        divergence_question = row.divergence_question
        if divergence_question is not None:
            exposure_counts[divergence_question] = exposure_counts.get(divergence_question, 0) + 1

    return dict(sorted(exposure_counts.items()))


def compute_q_nonagreement_metrics(pairwise_df: pd.DataFrame) -> tuple[dict[str, int], dict[str, float]]:
    q_nonagreements = pairwise_df.loc[pairwise_df["divergence_question"].notna(), "divergence_question"]
    distribution = q_nonagreements.value_counts().sort_index().to_dict()
    exposure_counts = compute_question_exposure_counts(pairwise_df)
    proportions = {
        question: distribution.get(question, 0) / exposure
        for question, exposure in exposure_counts.items()
        if exposure
    }
    return distribution, proportions


def compute_binary_tag_kappas(pairwise_df: pd.DataFrame) -> dict[str, float]:
    if pairwise_df.empty:
        return {}

    all_tags = sorted(
        tag
        for tags in pairwise_df["tags_a"].tolist() + pairwise_df["tags_b"].tolist()
        for tag in tags
    )
    unique_tags = sorted(set(all_tags))

    kappas: dict[str, float] = {}
    for tag in unique_tags:
        coder_a_values = [int(tag in tags) for tags in pairwise_df["tags_a"]]
        coder_b_values = [int(tag in tags) for tags in pairwise_df["tags_b"]]
        if len({*coder_a_values, *coder_b_values}) < 2:
            continue
        kappa = cohen_kappa_score(coder_a_values, coder_b_values)
        if pd.isna(kappa):
            continue
        kappas[tag] = float(kappa)

    return kappas


def extract_actionability_nonagreement_items(pairwise_df: pd.DataFrame) -> list[dict]:
    if pairwise_df.empty:
        return []

    rows: list[dict] = []
    filtered_df = pairwise_df.loc[~pairwise_df["actionability_agreement"]]
    columns = list(filtered_df.columns)

    for values in filtered_df.itertuples(index=False, name=None):
        row = dict(zip(columns, values, strict=False))
        rows.append(
            {
                "_id": row["_id"],
                "owasp_category": row["owasp_category"],
                "advice": row["advice"],
                "coder_a": row["coder_a"],
                "coder_b": row["coder_b"],
                "tags_a": list(row["tags_a"]),
                "tags_b": list(row["tags_b"]),
                "tag_labels_a": translate_tags(row["tags_a"]),
                "tag_labels_b": translate_tags(row["tags_b"]),
                "t_agreement": bool(row["t_agreement"]),
                "exact_tag_set_agreement": bool(row["exact_tag_set_agreement"]),
                "actionability_agreement": bool(row["actionability_agreement"]),
                "divergence_question": row["divergence_question"],
                "resolved": "",
            }
        )

    return sorted(rows, key=lambda row: str(row["_id"]))


def empty_metrics() -> dict:
    return {
        "n_compared_items": 0,
        "comparison_type_counts": {},
        "t_agreement_rate": None,
        "exact_tag_set_agreement_rate": None,
        "actionability_agreement_rate": None,
        "actionability_agreement_rate_by_owasp_category": {},
        "actionability_nonagreement_items": [],
        "q_nonagreement_distribution": {},
        "q_nonagreement_proportion_by_question": {},
        "binary_tag_kappas": {},
        "binary_tag_kappa_macro_average": None,
    }


def compute_metrics_summary(pairwise_df: pd.DataFrame) -> dict:
    if pairwise_df.empty:
        return empty_metrics()

    q_distribution, q_proportions = compute_q_nonagreement_metrics(pairwise_df)
    binary_tag_kappas = compute_binary_tag_kappas(pairwise_df)

    return {
        "n_compared_items": int(len(pairwise_df)),
        "comparison_type_counts": pairwise_df["comparison_type"].value_counts().sort_index().to_dict(),
        "t_agreement_rate": float(pairwise_df["t_agreement"].mean()),
        "exact_tag_set_agreement_rate": float(pairwise_df["exact_tag_set_agreement"].mean()),
        "actionability_agreement_rate": float(pairwise_df["actionability_agreement"].mean()),
        "actionability_agreement_rate_by_owasp_category": {},
        "actionability_nonagreement_items": extract_actionability_nonagreement_items(pairwise_df),
        "q_nonagreement_distribution": q_distribution,
        "q_nonagreement_proportion_by_question": q_proportions,
        "binary_tag_kappas": binary_tag_kappas,
        "binary_tag_kappa_macro_average": (
            float(mean(binary_tag_kappas.values())) if binary_tag_kappas else None
        ),
    }


def compute_metrics(pairwise_df: pd.DataFrame) -> dict:
    metrics = compute_metrics_summary(pairwise_df)

    if pairwise_df.empty or "owasp_category" not in pairwise_df.columns:
        return metrics

    actionability_by_owasp_category: dict[str, float] = {}
    grouped_pairwise_df = pairwise_df.loc[pairwise_df["owasp_category"].notna()]
    for category in sorted(grouped_pairwise_df["owasp_category"].unique()):
        category_pairwise_df = grouped_pairwise_df.loc[grouped_pairwise_df["owasp_category"] == category]
        actionability_by_owasp_category[str(category)] = float(
            category_pairwise_df["actionability_agreement"].mean()
        )

    metrics["actionability_agreement_rate_by_owasp_category"] = actionability_by_owasp_category
    return metrics


def serialize_dataframe_for_csv(df: pd.DataFrame) -> pd.DataFrame:
    serialized = df.copy()
    for column in ("tags_a", "tags_b"):
        if column in serialized.columns:
            serialized[column] = serialized[column].apply(lambda tags: json.dumps(list(tags)))
    return serialized


def load_exported_documents_dataframe(path: str) -> pd.DataFrame:
    documents_df = pd.read_csv(path)
    for column in documents_df.columns:
        if column.endswith("_tags"):
            documents_df[column] = documents_df[column].apply(
                lambda value: tuple(ast.literal_eval(value)) if pd.notna(value) else tuple()
            )
    return documents_df


def load_exported_pairwise_dataframe(path: str) -> pd.DataFrame:
    pairwise_df = pd.read_csv(path)
    for column in ("tags_a", "tags_b"):
        if column in pairwise_df.columns:
            pairwise_df[column] = pairwise_df[column].apply(
                lambda value: tuple(json.loads(value)) if pd.notna(value) else tuple()
            )
    for column in ("t_agreement", "exact_tag_set_agreement", "actionability_agreement"):
        if column in pairwise_df.columns:
            pairwise_df[column] = pairwise_df[column].astype(str).map({"True": True, "False": False})
    return pairwise_df


def resolve_audience_for_document(
    row: pd.Series,
    pairwise_lookup: dict[str, dict],
    audience_source: str,
    resolution_map: dict[str, str],
    coder_a: str,
    coder_b: str,
) -> str:
    item_id = str(row["_id"])
    tags_a = list(row.get(f"{coder_a}_tags", ()) or ())
    tags_b = list(row.get(f"{coder_b}_tags", ()) or ())
    pairwise_row = pairwise_lookup.get(item_id, {})

    if audience_source == "coder-a":
        return tags_to_audience(tags_a)
    if audience_source == "coder-b":
        return tags_to_audience(tags_b)
    if audience_source == "resolved" and item_id in resolution_map:
        return resolution_map[item_id]

    if pairwise_row.get("exact_tag_set_agreement"):
        return tags_to_audience(tags_a)

    audience_a = tags_to_audience(tags_a)
    audience_b = tags_to_audience(tags_b)
    if audience_a == audience_b:
        return audience_a

    if audience_source == "consensus":
        raise ValueError(
            f"Cannot infer a consensus audience for {item_id} without a resolution entry."
        )

    if audience_source == "resolved" and item_id in resolution_map:
        return resolution_map[item_id]

    return audience_a


def build_document_audience_dataframe(
    normalized_df: pd.DataFrame,
    pairwise_df: pd.DataFrame,
    coder_a: str,
    coder_b: str,
    audience_source: str,
    resolution_map: dict[str, str],
) -> pd.DataFrame:
    pairwise_lookup = {
        str(row["_id"]): row
        for row in pairwise_df.to_dict(orient="records")
    }
    rows: list[dict] = []

    for _, row in normalized_df.iterrows():
        if not row.get(f"{coder_a}_tags") or not row.get(f"{coder_b}_tags"):
            continue

        category_key = normalize_category_key(extract_owasp_category(row["_id"]))
        rows.append(
            {
                "_id": row["_id"],
                "category_key": category_key,
                "category": format_category_label(category_key),
                "audience": resolve_audience_for_document(
                    row,
                    pairwise_lookup,
                    audience_source,
                    resolution_map,
                    coder_a,
                    coder_b,
                ),
            }
        )

    return pd.DataFrame(rows)


def compute_publication_summary(
    pairwise_df: pd.DataFrame,
    document_audience_df: pd.DataFrame,
) -> pd.DataFrame:
    agreement_rows: list[dict] = []
    grouped_pairwise_df = pairwise_df.loc[pairwise_df["owasp_category"].notna()]
    for category_key, category_df in grouped_pairwise_df.groupby("owasp_category"):
        normalized_key = normalize_category_key(category_key)
        agreement_rows.append(
            {
                "category_key": normalized_key,
                "category": format_category_label(normalized_key),
                "agreement": float(category_df["actionability_agreement"].mean()),
            }
        )

    agreement_df = pd.DataFrame(agreement_rows)

    actionable_counts = (
        document_audience_df.assign(
            actionable=document_audience_df["audience"] != NON_ACTIONABLE_AUDIENCE
        )
        .groupby(["category_key", "category"], as_index=False)["actionable"]
        .sum()
        .rename(columns={"actionable": "actionable_count"})
    )

    summary_df = actionable_counts.merge(
        agreement_df,
        on=["category_key", "category"],
        how="outer",
    )
    summary_df["actionable_count"] = summary_df["actionable_count"].fillna(0).astype(int)
    summary_df["agreement"] = summary_df["agreement"].astype(float)
    return summary_df.sort_values("category_key", key=lambda series: series.map(category_sort_key))


def load_category_counts(path: str) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        counts_df = pd.read_csv(path)
    elif suffix == ".json":
        counts_df = pd.DataFrame(json.loads(Path(path).read_text(encoding="utf-8")))
    else:
        raise ValueError("Category counts file must be a .csv or .json file.")

    required_columns = {"category", "before", "after", "modified"}
    missing_columns = required_columns - set(counts_df.columns)
    if missing_columns:
        raise ValueError(
            f"Category counts file is missing required columns: {sorted(missing_columns)}"
        )

    counts_df = counts_df.copy()
    counts_df["category_key"] = counts_df["category"].map(normalize_category_key)
    counts_df["category"] = counts_df["category_key"].map(format_category_label)
    for column in ("before", "after", "modified"):
        counts_df[column] = counts_df[column].astype(int)

    return counts_df.sort_values("category_key", key=lambda series: series.map(category_sort_key))


def build_latex_table(
    table_df: pd.DataFrame,
    caption: str,
    label: str,
    total_agreement: float,
) -> str:
    lines = [
        r"\begin{table}[h]",
        r"\small",
        r"\centering",
        rf"\caption{{{caption}}}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"\textbf{Category} & \textbf{Before} & \textbf{After} & \textbf{Modified} & \textbf{Actionable} & \textbf{Agreement} \\",
        r"\midrule",
    ]

    for row in table_df.itertuples(index=False):
        lines.append(
            f"{row.category} & {row.before} & {row.after} & {row.modified} & "
            f"{row.actionable_count} & {row.agreement * 100:.1f}\\% \\\\"
        )

    lines.extend(
        [
            r"\midrule",
            f"\\textbf{{Total}} & \\textbf{{{int(table_df['before'].sum())}}} & "
            f"\\textbf{{{int(table_df['after'].sum())}}} & "
            f"\\textbf{{{int(table_df['modified'].sum())}}} & "
            f"\\textbf{{{int(table_df['actionable_count'].sum())}}} & "
            f"\\textbf{{{total_agreement * 100:.1f}\\%}} \\\\",
            r"\bottomrule",
            r"\end{tabular}",
            rf"\label{{{label}}}",
            r"\end{table}",
        ]
    )

    return "\n".join(lines) + "\n"


def plot_audience_distribution(document_audience_df: pd.DataFrame, output_path: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        plot_audience_distribution_with_pillow(document_audience_df, output_path)
        return

    counts_df = (
        document_audience_df.groupby(["category", "audience"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=AUDIENCE_ORDER, fill_value=0)
        .sort_index(key=lambda values: [category_sort_key(value) for value in values])
    )

    fig_height = max(4.5, 0.55 * len(counts_df))
    fig, axis = plt.subplots(figsize=(11, fig_height))
    left = pd.Series(0, index=counts_df.index, dtype=float)
    colors = {
        "End-User": "#5B8FF9",
        "IT-Specialist": "#61DDAA",
        "Security Expert": "#65789B",
        NON_ACTIONABLE_AUDIENCE: "#D9D9D9",
    }

    for audience in AUDIENCE_ORDER:
        values = counts_df[audience]
        bars = axis.barh(
            counts_df.index,
            values,
            left=left,
            label=audience,
            color=colors[audience],
            edgecolor="white",
        )
        for bar, value in zip(bars, values, strict=False):
            if value <= 0:
                continue
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_y() + bar.get_height() / 2,
                f"{int(value)}",
                ha="center",
                va="center",
                fontsize=9,
                color="black",
            )
        left = left + values

    axis.set_xlabel("Recommendations")
    axis.set_ylabel("Category")
    axis.legend(loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.08))
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="x", linestyle=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_audience_distribution_with_pillow(
    document_audience_df: pd.DataFrame,
    output_path: str,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    counts_df = (
        document_audience_df.groupby(["category", "audience"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=AUDIENCE_ORDER, fill_value=0)
        .sort_index(key=lambda values: [category_sort_key(value) for value in values])
    )

    colors = {
        "End-User": "#5B8FF9",
        "IT-Specialist": "#61DDAA",
        "Security Expert": "#65789B",
        NON_ACTIONABLE_AUDIENCE: "#D9D9D9",
    }

    row_height = 42
    left_margin = 120
    right_margin = 30
    top_margin = 80
    bottom_margin = 40
    chart_width = 820
    legend_height = 30
    image_width = left_margin + chart_width + right_margin
    image_height = top_margin + legend_height + len(counts_df) * row_height + bottom_margin

    image = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    bold_font = font

    max_total = max(int(counts_df.sum(axis=1).max()), 1)
    scale = chart_width / max_total

    legend_x = left_margin
    legend_y = 20
    for audience in AUDIENCE_ORDER:
        draw.rectangle((legend_x, legend_y, legend_x + 16, legend_y + 16), fill=colors[audience])
        draw.text((legend_x + 22, legend_y + 2), audience, fill="black", font=font)
        legend_x += 165

    axis_y = top_margin + legend_height + len(counts_df) * row_height
    draw.line((left_margin, top_margin + legend_height - 10, left_margin, axis_y), fill="#333333", width=1)
    draw.line((left_margin, axis_y, left_margin + chart_width, axis_y), fill="#333333", width=1)

    for tick in range(0, max_total + 1):
        x = left_margin + tick * scale
        draw.line((x, top_margin + legend_height - 10, x, axis_y), fill="#EEEEEE", width=1)
        draw.text((x - 4, axis_y + 6), str(tick), fill="#555555", font=font)

    for row_index, (category, counts) in enumerate(counts_df.iterrows()):
        y_top = top_margin + legend_height + row_index * row_height
        bar_y = y_top + 8
        draw.text((20, bar_y + 3), str(category), fill="black", font=bold_font)

        current_left = left_margin
        for audience in AUDIENCE_ORDER:
            value = int(counts[audience])
            if value <= 0:
                continue
            width = max(int(round(value * scale)), 1)
            draw.rectangle(
                (current_left, bar_y, current_left + width, bar_y + 22),
                fill=colors[audience],
                outline="white",
            )
            label = str(value)
            text_box = draw.textbbox((0, 0), label, font=font)
            text_width = text_box[2] - text_box[0]
            text_height = text_box[3] - text_box[1]
            draw.text(
                (
                    current_left + max((width - text_width) / 2, 2),
                    bar_y + (22 - text_height) / 2 - 1,
                ),
                label,
                fill="black",
                font=font,
            )
            current_left += width

    draw.text((left_margin + chart_width / 2 - 40, image_height - 22), "Recommendations", fill="black", font=bold_font)
    image.save(output_path)


def write_publication_outputs(
    output_prefix: str,
    pairwise_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
    args: argparse.Namespace,
) -> dict[str, str]:
    resolution_map = load_resolution_map(args.resolution_file)
    document_audience_df = build_document_audience_dataframe(
        normalized_df,
        pairwise_df,
        args.coder_a,
        args.coder_b,
        args.audience_source,
        resolution_map,
    )
    summary_df = compute_publication_summary(pairwise_df, document_audience_df)

    output_paths: dict[str, str] = {}

    summary_csv_path = f"{output_prefix}_category_summary.csv"
    summary_df.to_csv(summary_csv_path, index=False)
    output_paths["category_summary_csv"] = summary_csv_path

    audience_csv_path = f"{output_prefix}_audience_distribution.csv"
    document_audience_df.to_csv(audience_csv_path, index=False)
    output_paths["audience_distribution_csv"] = audience_csv_path

    plot_path = f"{output_prefix}_audience_distribution.png"
    plot_audience_distribution(document_audience_df, plot_path)
    output_paths["audience_distribution_plot"] = plot_path

    if args.table_counts_file:
        table_counts_df = load_category_counts(args.table_counts_file)
        table_df = table_counts_df.merge(
            summary_df[["category_key", "actionable_count", "agreement"]],
            on="category_key",
            how="left",
        )
        table_df["actionable_count"] = table_df["actionable_count"].fillna(0).astype(int)
        table_df["agreement"] = table_df["agreement"].fillna(0.0).astype(float)
        latex_table = build_latex_table(
            table_df[["category", "before", "after", "modified", "actionable_count", "agreement"]],
            args.table_caption,
            args.table_label,
            float(pairwise_df["actionability_agreement"].mean()) if not pairwise_df.empty else 0.0,
        )
        latex_path = f"{output_prefix}_category_summary.tex"
        Path(latex_path).write_text(latex_table, encoding="utf-8")
        output_paths["latex_table"] = latex_path

    return output_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate SAcoding coder agreement from MongoDB.")
    parser.add_argument("--uri", default=os.environ.get("URI",""), help="MongoDB connection string")
    parser.add_argument("--database", default=os.environ.get("DATABASE",""), help="MongoDB database name")
    parser.add_argument("--collection", default=os.environ.get("COLLECTION",""), help="MongoDB collection name")
    parser.add_argument("--coder-a", default="C0", help="First coder id")
    parser.add_argument("--coder-b", default="C1", help="Second coder id")
    parser.add_argument(
        "--input-prefix",
        help=(
            "Load previously exported <prefix>_documents.csv, <prefix>_pairwise.csv, "
            "and optionally <prefix>_actionability_nonagreements.json instead of querying MongoDB."
        ),
    )
    parser.add_argument(
        "--output-prefix",
        help=(
            "Optional output prefix. Writes <prefix>_documents.csv, "
            "<prefix>_pairwise.csv, and <prefix>_actionability_nonagreements.json"
        ),
    )
    parser.add_argument(
        "--output-mode",
        choices=("metrics", "publication", "all"),
        default="metrics",
        help="Choose whether to print metrics only, generate publication assets, or do both.",
    )
    parser.add_argument(
        "--table-counts-file",
        help="Optional CSV or JSON file with category,before,after,modified columns for LaTeX table generation.",
    )
    parser.add_argument(
        "--table-caption",
        default=(
            "Number of recommendation \\emph{before} and \\emph{after} transforming "
            "recommendations into singular units."
        ),
        help="Caption used for the generated LaTeX table.",
    )
    parser.add_argument(
        "--table-label",
        default="tab:sacoding-category-summary",
        help="Label used for the generated LaTeX table.",
    )
    parser.add_argument(
        "--resolution-file",
        help="Optional JSON file containing resolved audience decisions for disagreements.",
    )
    parser.add_argument(
        "--audience-source",
        choices=("coder-a", "coder-b", "consensus", "resolved"),
        default="coder-a",
        help="Source used to derive the per-item audience bucket for publication outputs.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.input_prefix:
        normalized_df = load_exported_documents_dataframe(f"{args.input_prefix}_documents.csv")
        pairwise_df = load_exported_pairwise_dataframe(f"{args.input_prefix}_pairwise.csv")
        if not args.output_prefix:
            args.output_prefix = args.input_prefix
        if not args.resolution_file:
            default_resolution_file = f"{args.input_prefix}_actionability_nonagreements.json"
            if Path(default_resolution_file).exists():
                args.resolution_file = default_resolution_file
    else:
        documents_df = fetch_collection_dataframe(args.uri, args.database, args.collection)
        normalized_df = normalize_codes_dataframe(documents_df)
        pairwise_df = build_pairwise_dataframe(normalized_df, args.coder_a, args.coder_b)

    metrics = None

    if args.output_mode in {"metrics", "all"}:
        metrics = compute_metrics(pairwise_df)
        print(json.dumps(metrics, indent=2, sort_keys=True))

    if args.output_prefix and not args.input_prefix:
        if metrics is None:
            metrics = compute_metrics(pairwise_df)
        serialize_dataframe_for_csv(normalized_df).to_csv(
            f"{args.output_prefix}_documents.csv",
            index=False,
        )
        serialize_dataframe_for_csv(pairwise_df).to_csv(
            f"{args.output_prefix}_pairwise.csv",
            index=False,
        )
        with open(
            f"{args.output_prefix}_actionability_nonagreements.json",
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                metrics["actionability_nonagreement_items"],
                file,
                indent=2,
                ensure_ascii=True,
                sort_keys=True,
            )

    if args.output_mode in {"publication", "all"}:
        if not args.output_prefix:
            raise ValueError("--output-prefix is required when --output-mode is publication or all.")
        publication_outputs = write_publication_outputs(
            args.output_prefix,
            pairwise_df,
            normalized_df,
            args,
        )
        print(json.dumps({"publication_outputs": publication_outputs}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
