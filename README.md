# data

This repo includes a lightweight workflow to summarize `je_samples.xlsx` and publish
outputs as a downloadable artifact in GitHub Actions.

## How it works
- `scripts/analyze_je_samples.py` reads the Excel file and writes summaries to `outputs/`.
- `.github/workflows/je-samples-analysis.yml` installs dependencies and runs the script.

## Running locally
```bash
pip install -r requirements.txt
python scripts/analyze_je_samples.py
```

## Outputs
The following files are generated in `outputs/`:
- `summary.json`: Row counts, date ranges, and missing values.
- `summary.md`: Human-readable summary.
- `column_profile.csv`: Column-level profile statistics.
- `numeric_describe.csv`: Descriptive stats for numeric columns.
- `benford/benford_summary.csv`: Benford summary statistics per numeric column.
- `benford/benford_detail.csv`: Benford detail distribution per digit.
- `benford/benford_overall.png`: Overall Benford distribution chart.
