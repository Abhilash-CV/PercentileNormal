import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="KEAM Full Normalization", layout="wide")

st.title("KEAM 2026 Percentile + Normalization Calculator")

uploaded_file = st.file_uploader(
    "Upload Excel File",
    type=["xlsx"]
)

if uploaded_file:

    # =========================
    # LOAD DATA
    # =========================
    df = pd.read_excel(uploaded_file)

    required_cols = [
        "Roll No",
        "MatheMatics",
        "Physics",
        "Chemistry",
        "Batch"
    ]

    for col in required_cols:
        if col not in df.columns:
            st.error(f"Missing column: {col}")
            st.stop()

    # =========================
    # CALCULATE RAW SCORE
    # =========================
    # Total raw score out of 600
    df["Raw_Total"] = (
        df["MatheMatics"] +
        df["Physics"] +
        df["Chemistry"]
    )

    # Convert to scale of 300
    df["Score"] = df["Raw_Total"] / 2

    # =========================
    # CALCULATE PERCENTILE
    # =========================
    percentile_list = []

    for batch in df["Batch"].unique():

        temp = df[df["Batch"] == batch].copy()

        n = len(temp)

        # Rank method
        temp["Percentile"] = (
            temp["Score"]
            .rank(method="max", pct=True)
            * 100
        )

        percentile_list.append(temp)

    df = pd.concat(percentile_list)

    # =========================
    # SORT
    # =========================
    df = df.sort_values(
        ["Batch", "Percentile"]
    ).reset_index(drop=True)

    batches = sorted(df["Batch"].unique())

    # =========================
    # PREPROCESS
    # =========================
    batch_lookup = {}

    for batch in batches:

        temp = (
            df[df["Batch"] == batch]
            .sort_values("Percentile")
        )

        batch_lookup[batch] = {
            "percentiles": temp["Percentile"].to_numpy(),
            "scores": temp["Score"].to_numpy()
        }

    # =========================
    # FAST INTERPOLATION
    # =========================
    def interpolate_score(
        target_percentile,
        p_arr,
        s_arr
    ):

        idx = np.searchsorted(
            p_arr,
            target_percentile
        )

        # Lower than minimum
        if idx == 0:
            return float(s_arr[0])

        # Greater than maximum
        if idx >= len(p_arr):
            return float(s_arr[-1])

        p1 = p_arr[idx - 1]
        p2 = p_arr[idx]

        s1 = s_arr[idx - 1]
        s2 = s_arr[idx]

        # Exact match
        if p1 == target_percentile:
            return float(s1)

        if p2 == target_percentile:
            return float(s2)

        # Linear interpolation
        return float(
            s1 +
            (
                (target_percentile - p1)
                / (p2 - p1)
            ) * (s2 - s1)
        )

    # =========================
    # NORMALIZATION
    # =========================
    output = []

    rows = list(df.itertuples(index=False))

    total_rows = len(rows)

    progress = st.progress(0)

    for i, row in enumerate(rows):

        percentile = row.Percentile
        current_batch = row.Batch

        scores = []

        row_data = {
            "RollNo": row._asdict()["Roll No"],
            "Batch": current_batch,
            "Percentile": round(percentile, 8),
            "Score": round(row.Score, 8)
        }

        scores.append(row.Score)

        score_index = 2

        for batch in batches:

            if batch == current_batch:
                continue

            interp_score = interpolate_score(
                percentile,
                batch_lookup[batch]["percentiles"],
                batch_lookup[batch]["scores"]
            )

            row_data[f"Score{score_index}"] = round(
                interp_score,
                8
            )

            scores.append(interp_score)

            score_index += 1

        # Final normalized score
        row_data["Norm_Score"] = round(
            np.mean(scores),
            4
        )

        output.append(row_data)

        if i % 1000 == 0:
            progress.progress(i / total_rows)

    # =========================
    # OUTPUT DATAFRAME
    # =========================
    out_df = pd.DataFrame(output)

    fixed_cols = [
        "RollNo",
        "Batch",
        "Percentile",
        "Score"
    ]

    score_cols = sorted(
        [
            c for c in out_df.columns
            if c.startswith("Score")
            and c != "Score"
        ],
        key=lambda x: int(
            x.replace("Score", "")
        )
    )

    final_cols = (
        fixed_cols +
        score_cols +
        ["Norm_Score"]
    )

    out_df = out_df[final_cols]

    st.success("Normalization Completed")

    st.dataframe(
        out_df,
        use_container_width=True
    )

    # =========================
    # EXPORT EXCEL
    # =========================
    output_file = "keam_normalized_output.xlsx"

    with pd.ExcelWriter(
        output_file,
        engine="openpyxl"
    ) as writer:

        out_df.to_excel(
            writer,
            index=False
        )

    with open(output_file, "rb") as f:

        st.download_button(
            label="Download Output Excel",
            data=f,
            file_name=output_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
