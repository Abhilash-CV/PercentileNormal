import streamlit as stimport pandas as pdimport numpy as np

st.set_page_config(page_title="KEAM Full Normalization",layout="wide")

st.title("KEAM 2026 Percentile + Normalization Calculator")

uploaded_file = st.file_uploader("Upload Excel File",type=["xlsx"])

if uploaded_file:

# ==================================================
# LOAD EXCEL
# ==================================================
df = pd.read_excel(uploaded_file)

# Clean column names
df.columns = [
    c.strip().replace(" ", "_")
    for c in df.columns
]

# ==================================================
# REQUIRED COLUMNS
# ==================================================
required_cols = [
    "Roll_No",
    "MatheMatics",
    "Physics",
    "Chemistry",
    "Batch"
]

for col in required_cols:

    if col not in df.columns:

        st.error(f"Missing column: {col}")
        st.stop()

# ==================================================
# CALCULATE RAW SCORE
# ==================================================
# Raw score out of 600
df["Raw_Total"] = (
    df["MatheMatics"] +
    df["Physics"] +
    df["Chemistry"]
)

# Convert to 300 scale
df["Score"] = (
    df["Raw_Total"] / 2
)

# ==================================================
# EXACT KEAM PERCENTILE
# ==================================================
percentile_frames = []

for batch in df["Batch"].unique():

    temp = df[
        df["Batch"] == batch
    ].copy()

    scores = (
        temp["Score"]
        .to_numpy(dtype=np.float64)
    )

    n = len(scores)

    percentiles = []

    # Official KEAM formula
    for s in scores:

        # tolerance handling
        count = np.sum(
            scores <= (s + 1e-9)
        )

        p = (
            count / n
        ) * 100

        percentiles.append(
            round(p, 8)
        )

    temp["Percentile"] = (
        percentiles
    )

    percentile_frames.append(
        temp
    )

df = pd.concat(
    percentile_frames
)

# ==================================================
# SORT
# ==================================================
df = df.sort_values(
    ["Batch", "Percentile"]
).reset_index(drop=True)

batches = sorted(
    df["Batch"].unique()
)

# ==================================================
# PREPROCESS BATCHES
# ==================================================
batch_lookup = {}

for batch in batches:

    temp = (
        df[
            df["Batch"] == batch
        ]
        .sort_values(
            "Percentile"
        )
    )

    batch_lookup[batch] = {

        "percentiles":
            temp[
                "Percentile"
            ].to_numpy(
                dtype=np.float64
            ),

        "scores":
            temp[
                "Score"
            ].to_numpy(
                dtype=np.float64
            )
    }

# ==================================================
# INTERPOLATION FUNCTION
# ==================================================
def interpolate_score(
    target_percentile,
    p_arr,
    s_arr
):

    idx = np.searchsorted(
        p_arr,
        target_percentile
    )

    # Below minimum
    if idx == 0:

        return float(
            s_arr[0]
        )

    # Above maximum
    if idx >= len(p_arr):

        return float(
            s_arr[-1]
        )

    p1 = p_arr[idx - 1]
    p2 = p_arr[idx]

    s1 = s_arr[idx - 1]
    s2 = s_arr[idx]

    # Exact match
    if abs(
        p1 - target_percentile
    ) < 1e-9:

        return float(s1)

    if abs(
        p2 - target_percentile
    ) < 1e-9:

        return float(s2)

    # Linear interpolation
    interpolated = (
        s1 +
        (
            (
                target_percentile - p1
            )
            /
            (
                p2 - p1
            )
        )
        *
        (
            s2 - s1
        )
    )

    return float(
        round(
            interpolated,
            8
        )
    )

# ==================================================
# NORMALIZATION
# ==================================================
output = []

rows = list(
    df.itertuples(
        index=False
    )
)

total_rows = len(rows)

progress = st.progress(0)

for i, row in enumerate(rows):

    percentile = float(
        row.Percentile
    )

    current_batch = (
        row.Batch
    )

    scores = []

    row_data = {

        "RollNo":
            row.Roll_No,

        "Batch":
            current_batch,

        "Percentile":
            round(
                percentile,
                8
            ),

        "Score":
            round(
                row.Score,
                8
            )
    }

    scores.append(
        row.Score
    )

    score_index = 2

    for batch in batches:

        if batch == current_batch:
            continue

        interp_score = (
            interpolate_score(

                percentile,

                batch_lookup[
                    batch
                ][
                    "percentiles"
                ],

                batch_lookup[
                    batch
                ][
                    "scores"
                ]
            )
        )

        row_data[
            f"Score{score_index}"
        ] = round(
            interp_score,
            8
        )

        scores.append(
            interp_score
        )

        score_index += 1

    # Final normalized score
    row_data[
        "Norm_Score"
    ] = round(
        np.mean(scores),
        4
    )

    output.append(
        row_data
    )

    # Progress update
    if i % 1000 == 0:

        progress.progress(
            i / total_rows
        )

# ==================================================
# FINAL OUTPUT
# ==================================================
out_df = pd.DataFrame(
    output
)

fixed_cols = [
    "RollNo",
    "Batch",
    "Percentile",
    "Score"
]

score_cols = sorted(

    [
        c
        for c in out_df.columns

        if c.startswith("Score")
        and c != "Score"
    ],

    key=lambda x: int(
        x.replace(
            "Score",
            ""
        )
    )
)

final_cols = (
    fixed_cols +
    score_cols +
    ["Norm_Score"]
)

out_df = out_df[
    final_cols
]

# ==================================================
# DISPLAY
# ==================================================
st.success(
    "Normalization Completed"
)

st.dataframe(
    out_df,
    use_container_width=True
)

# ==================================================
# EXPORT EXCEL
# ==================================================
output_file = (
    "keam_normalized_output.xlsx"
)

with pd.ExcelWriter(
    output_file,
    engine="openpyxl"
) as writer:

    out_df.to_excel(
        writer,
        index=False
    )

with open(
    output_file,
    "rb"
) as f:

    st.download_button(
        label="Download Output Excel",
        data=f,
        file_name=output_file,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
