from __future__ import annotations

import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd
import matplotlib.pyplot as plt

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

    benford_dir = output_dir / "benford"
    benford_dir.mkdir(parents=True, exist_ok=True)
    benford_summary, benford_detail, benford_charts = run_benford_analysis(
        df, benford_dir
    )
    benford_summary.to_csv(benford_dir / "benford_summary.csv", index=False)
    benford_detail.to_csv(benford_dir / "benford_detail.csv", index=False)

    summary_md.append("\n## Benford Analysis\n")
    if benford_summary.empty:
        summary_md.append("- No numeric columns available for Benford analysis.")
    else:
        summary_md.append(
            f"- Overall chart: `{(benford_dir / 'benford_overall.png').name}`"
        )
        if benford_charts:
            chart_list = ", ".join(f"`{Path(chart).name}`" for chart in benford_charts)
            summary_md.append(f"- Column charts: {chart_list}")
        summary_md.append(
            f"- Summary table: `{(benford_dir / 'benford_summary.csv').name}`"
        )
        summary_md.append(
            f"- Detail table: `{(benford_dir / 'benford_detail.csv').name}`"
        )

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


def run_benford_analysis(
    df: pd.DataFrame, output_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    numeric_columns = df.select_dtypes(include="number")
    if numeric_columns.empty:
        return pd.DataFrame(), pd.DataFrame(), []

    expected_pct = {
        digit: math.log10(1 + 1 / digit) for digit in range(1, 10)
    }

    summary_rows: list[dict[str, float | int | str]] = []
    detail_rows: list[dict[str, float | int | str]] = []

    overall_series = pd.Series(dtype="float")
    for column in numeric_columns.columns:
        overall_series = pd.concat(
            [overall_series, numeric_columns[column]], ignore_index=True
        )

    overall_df = compute_benford_table(
        "Overall", overall_series, expected_pct
    )
    summary_rows.append(overall_df["summary"])
    detail_rows.extend(overall_df["detail"])
    plot_benford_chart(
        overall_df["table"],
        output_dir / "benford_overall.png",
        "Overall Benford Analysis",
    )

    chart_files: list[str] = []
    for column in numeric_columns.columns:
        column_df = compute_benford_table(
            str(column), numeric_columns[column], expected_pct
        )
        summary_rows.append(column_df["summary"])
        detail_rows.extend(column_df["detail"])

    summary = pd.DataFrame(summary_rows)
    detail = pd.DataFrame(detail_rows)

    top_columns = (
        summary.sort_values("total_values", ascending=False)
        .query("column != 'Overall'")
        .head(5)["column"]
        .tolist()
    )
    for column in top_columns:
        table = detail.query("column == @column").copy()
        chart_path = output_dir / f"benford_{sanitize_filename(column)}.png"
        plot_benford_chart(
            table,
            chart_path,
            f"Benford Analysis - {column}",
        )
        chart_files.append(str(chart_path))

    return summary, detail, chart_files


def compute_benford_table(
    column: str, series: pd.Series, expected_pct: dict[int, float]
) -> dict[str, object]:
    digits = [
        digit
        for value in series.dropna().values.tolist()
        if (digit := leading_digit(value)) is not None
    ]
    total = len(digits)
    counts = {digit: 0 for digit in range(1, 10)}
    for digit in digits:
        counts[digit] += 1

    table_rows = []
    chi_square = 0.0
    for digit in range(1, 10):
        expected_count = expected_pct[digit] * total
        actual_count = counts[digit]
        actual_pct = (actual_count / total * 100) if total else 0.0
        expected_pct_value = expected_pct[digit] * 100
        diff_pct = actual_pct - expected_pct_value
        if expected_count > 0:
            chi_square += (actual_count - expected_count) ** 2 / expected_count
        table_rows.append(
            {
                "column": column,
                "digit": digit,
                "actual_count": actual_count,
                "actual_pct": round(actual_pct, 2),
                "expected_pct": round(expected_pct_value, 2),
                "expected_count": round(expected_count, 2),
                "diff_pct": round(diff_pct, 2),
            }
        )

    table = pd.DataFrame(table_rows)
    summary = {
        "column": column,
        "total_values": total,
        "chi_square": round(chi_square, 4),
        "max_abs_diff_pct": round(table["diff_pct"].abs().max(), 2)
        if not table.empty
        else 0.0,
    }

    return {
        "summary": summary,
        "detail": table_rows,
        "table": table,
    }


def leading_digit(value: float | int) -> int | None:
    try:
        decimal_value = Decimal(str(value)).copy_abs()
    except (InvalidOperation, ValueError, TypeError):
        return None
    if decimal_value == 0:
        return None
    digits = decimal_value.as_tuple().digits
    if not digits:
        return None
    return int(digits[0])


def plot_benford_chart(df: pd.DataFrame, path: Path, title: str) -> None:
    if df.empty:
        return
    plt.figure(figsize=(8, 5))
    plt.bar(
        df["digit"].astype(str),
        df["actual_pct"],
        color="#4C78A8",
        label="Actual",
    )
    plt.plot(
        df["digit"].astype(str),
        df["expected_pct"],
        color="#F58518",
        marker="o",
        linewidth=2,
        label="Benford Expected",
    )
    plt.title(title)
    plt.xlabel("Leading Digit")
    plt.ylabel("Percent")
    plt.ylim(0, max(df["actual_pct"].max(), df["expected_pct"].max()) * 1.2)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def sanitize_filename(name: str) -> str:
    return "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in name
    ).strip("_")


if __name__ == "__main__":
    main()
