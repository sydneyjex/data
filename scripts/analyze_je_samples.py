from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def build_summary(df: pd.DataFrame) -> dict:
    row_count, column_count = df.shape
    missing_by_column = df.isna().sum().to_dict()

    date_columns = {
        column
        for column in df.columns
        if "date" in str(column).lower()
        or pd.api.types.is_datetime64_any_dtype(df[column])
    }
    date_ranges: dict[str, dict[str, str | int | None]] = {}
    for column in sorted(date_columns):
        coerced = pd.to_datetime(df[column], errors="coerce")
        non_null = int(coerced.notna().sum())
        if non_null == 0:
            date_ranges[column] = {"min": None, "max": None, "non_null": 0}
            continue
        date_ranges[column] = {
            "min": coerced.min().date().isoformat(),
            "max": coerced.max().date().isoformat(),
            "non_null": non_null,
        }

    return {
        "row_count": int(row_count),
        "column_count": int(column_count),
        "missing_by_column": missing_by_column,
        "date_ranges": date_ranges,
    }


def write_outputs(df: pd.DataFrame, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = build_summary(df)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True)
    )

    column_profile = pd.DataFrame(
        {
            "column": df.columns,
            "dtype": df.dtypes.astype(str),
            "missing": df.isna().sum().values,
            "missing_pct": (df.isna().mean() * 100).round(2).values,
        }
    )
    column_profile.to_csv(output_dir / "column_profile.csv", index=False)

    numeric_columns = df.select_dtypes(include="number")
    if numeric_columns.empty:
        (output_dir / "numeric_describe.csv").write_text(
            "No numeric columns detected."
        )
    else:
        numeric_columns.describe().T.to_csv(
            output_dir / "numeric_describe.csv"
        )

    summary_md = [
        "# JE Samples Summary",
        "",
        f"- Rows: **{summary['row_count']}**",
        f"- Columns: **{summary['column_count']}**",
        "",
        "## Date Ranges",
    ]
    if summary["date_ranges"]:
        for column, date_info in summary["date_ranges"].items():
            summary_md.append(
                f"- {column}: {date_info['min']} to {date_info['max']}"
            )
    else:
        summary_md.append("- No date columns detected.")

    summary_md.append("\n## Missing Values (Top 10)\n")
    missing_sorted = (
        column_profile.sort_values("missing", ascending=False)
        .head(10)
        .loc[:, ["column", "missing", "missing_pct"]]
    )
    summary_md.append(render_markdown_table(missing_sorted))

    (output_dir / "summary.md").write_text("\n".join(summary_md))


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    input_path = repo_root / "je_samples.xlsx"
    output_dir = repo_root / "outputs"

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    df = pd.read_excel(input_path)
    write_outputs(df, output_dir)


def render_markdown_table(df: pd.DataFrame) -> str:
    headers = [str(column) for column in df.columns]
    rows = df.astype(str).values.tolist()

    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    row_lines = ["| " + " | ".join(row) + " |" for row in rows]

    return "\n".join([header_line, separator_line] + row_lines)


if __name__ == "__main__":
    main()
