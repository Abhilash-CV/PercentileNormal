import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="KEAM 2026 Normalization", layout="wide")

st.title("KEAM 2026 – Percentile Interpolated Average Normalization")
st.markdown(
    "Implements the exact 3-step method from the KEAM 2026 Prospectus "
    "(Clause 9.4.4(i), pages 56–58)."
)

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:

    # ─────────────────────────────────────────────────────────
    # LOAD & VALIDATE
    # ─────────────────────────────────────────────────────────
    df = pd.read_excel(uploaded_file)
    df.columns = [c.strip().replace(" ", "_") for c in df.columns]

    required_cols = ["Roll_No", "MatheMatics", "Physics", "Chemistry", "Batch"]
    for col in required_cols:
        if col not in df.columns:
            st.error(f"Missing column: {col}")
            st.stop()

    df["MatheMatics"] = pd.to_numeric(df["MatheMatics"], errors="coerce")
    df["Physics"]     = pd.to_numeric(df["Physics"],     errors="coerce")
    df["Chemistry"]   = pd.to_numeric(df["Chemistry"],   errors="coerce")
    df = df.fillna(0)

    # ─────────────────────────────────────────────────────────
    # RAW MARK  X_ij  (out of 300)
    # Engineering: 75 Maths (×4) + 45 Physics (×4) + 30 Chem (×4) = 600 max
    # Normalise to 300 by dividing by 2  →  X_ij
    # ─────────────────────────────────────────────────────────
    df["Raw_Total"] = df["MatheMatics"] + df["Physics"] + df["Chemistry"]
    df["X"] = np.round(df["Raw_Total"] / 2, 8)   # X_ij : score out of 300

    sessions = sorted(df["Batch"].unique())
    K = len(sessions)                             # total number of sessions

    # ─────────────────────────────────────────────────────────
    # STEP 1 – Percentile score  P_ij  for each session
    #
    # P_ij = ( Σ_{r=1}^{N_i} I(X_ir ≤ X_ij) ) / N_i  × 100
    #
    # where I(·) is the indicator function.
    # Calculated up to 8 decimal places (Prospectus requirement).
    # ─────────────────────────────────────────────────────────
    percentile_parts = []

    for session in sessions:
        mask   = df["Batch"] == session
        temp   = df[mask].copy()
        Ni     = len(temp)                        # N_i : candidates in session i
        X_arr  = temp["X"].to_numpy(dtype=np.float64)

        # Count of X_ir ≤ X_ij for every j  (vectorised)
        counts = np.array([(X_arr <= xj).sum() for xj in X_arr], dtype=np.float64)
        temp["P"] = np.round(counts / Ni * 100, 8)

        percentile_parts.append(temp)

    df = pd.concat(percentile_parts).reset_index(drop=True)

    # ─────────────────────────────────────────────────────────
    # Pre-build lookup tables for Step 2
    # Each session stores sorted (P_values, X_values) arrays.
    # ─────────────────────────────────────────────────────────
    session_lookup: dict[str, dict] = {}

    for session in sessions:
        sub = df[df["Batch"] == session].sort_values("P")
        session_lookup[session] = {
            "P_arr": sub["P"].to_numpy(dtype=np.float64),   # percentiles (sorted)
            "X_arr": sub["X"].to_numpy(dtype=np.float64),   # raw marks (sorted by P)
        }

    # ─────────────────────────────────────────────────────────
    # STEP 2 – Interpolated mark  Y_ij^(r)  for each other session r
    #
    # Given P_ij and the sorted (P, X) table of session r:
    #
    # (i)  Exact match  → Y = X corresponding to that percentile.
    # (ii) Otherwise    → linear interpolation between immediate
    #                     lower P^(1)_r  and upper P^(2)_r.
    # (iii) No lower    → Y = min(X in session r)   [P_ij < all P values]
    # (iv)  No upper    → Y = max(X in session r)   [P_ij > all P values]
    #       (implicit from the formula – maps top percentile to top mark)
    # ─────────────────────────────────────────────────────────
    def interpolate(P_ij: float, P_arr: np.ndarray, X_arr: np.ndarray) -> float:
        """
        Return the interpolated raw mark Y_ij^(r) for a candidate whose
        percentile in their own session is P_ij, given the sorted percentile
        and mark arrays of target session r.
        """
        n = len(P_arr)

        # (iii) P_ij is below the minimum percentile in session r
        if P_ij <= P_arr[0]:
            # Exact match at minimum, or below → minimum mark
            if abs(P_ij - P_arr[0]) < 1e-9:
                return float(X_arr[0])
            return float(X_arr[0])          # min(X_rm) as per Prospectus

        # (iv) P_ij is at or above the maximum percentile in session r
        if P_ij >= P_arr[-1]:
            return float(X_arr[-1])         # max mark

        # Binary search: find the first index where P_arr[idx] >= P_ij
        idx = int(np.searchsorted(P_arr, P_ij, side="left"))

        # (i) Exact match
        if abs(P_arr[idx] - P_ij) < 1e-9:
            return float(X_arr[idx])

        # The value P_ij lies strictly between P_arr[idx-1] and P_arr[idx]
        P1 = P_arr[idx - 1]                # immediate lower  P^(1)_r
        P2 = P_arr[idx]                    # immediate higher P^(2)_r
        X1 = X_arr[idx - 1]               # corresponding X^(1)_r
        X2 = X_arr[idx]                   # corresponding X^(2)_r

        # (ii) Linear interpolation (Prospectus Step 2, formula ii)
        Y = X1 + ((P_ij - P1) / (P2 - P1)) * (X2 - X1)
        return float(round(Y, 8))

    # ─────────────────────────────────────────────────────────
    # STEP 3 – Normalized mark  Z_ij
    #
    # Z_ij = (1/K) × ( X_ij + Σ_{r=1, r≠i}^{K}  Y_ij^(r) )
    #
    # i.e. the simple average of the candidate's own mark and
    # the K-1 interpolated marks from every other session.
    # Taken with 4 decimal places (Prospectus requirement).
    # ─────────────────────────────────────────────────────────
    progress = st.progress(0, text="Computing normalized scores…")
    rows_out  = []
    total     = len(df)

    for i, row in enumerate(df.itertuples(index=False)):

        own_session = row.Batch
        P_ij        = float(row.P)
        X_ij        = float(row.X)

        # Collect X_ij and all interpolated Y_ij^(r)
        all_scores = [X_ij]

        for r_session in sessions:
            if r_session == own_session:
                continue
            Y_r = interpolate(
                P_ij,
                session_lookup[r_session]["P_arr"],
                session_lookup[r_session]["X_arr"],
            )
            all_scores.append(Y_r)

        # Z_ij = (1/K) * sum of all_scores
        Z_ij = round(np.mean(all_scores), 4)

        row_dict = {
            "Roll_No":   row.Roll_No,
            "Session":   own_session,
            # Step 1 output
            "X_ij (Score/300)": round(X_ij, 8),
            "P_ij (Percentile)": round(P_ij, 8),
        }

        # Step 2 outputs  Y_ij^(r)  for each other session
        col_idx = 1
        for r_session in sessions:
            if r_session == own_session:
                continue
            row_dict[f"Y_({r_session})"] = round(all_scores[col_idx], 8)
            col_idx += 1

        # Step 3 output
        row_dict["Z_ij (Norm_Score)"] = Z_ij

        rows_out.append(row_dict)

        if i % 500 == 0:
            progress.progress(i / total, text=f"Processing {i}/{total}…")

    progress.progress(1.0, text="Done!")

    # ─────────────────────────────────────────────────────────
    # DISPLAY & EXPORT
    # ─────────────────────────────────────────────────────────
    out_df = pd.DataFrame(rows_out)

    st.success(f"Normalization complete — {len(out_df):,} candidates processed.")

    # Summary statistics
    st.subheader("Summary Statistics")
    summary = (
        out_df.groupby("Session")["Z_ij (Norm_Score)"]
        .agg(Count="count", Mean="mean", Max="max", Min="min", Std="std")
        .round(4)
    )
    st.dataframe(summary, use_container_width=True)

    st.subheader("Full Results")
    st.dataframe(out_df, use_container_width=True)

    # Export
    output_path = "keam_normalized_output.xlsx"
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        out_df.to_excel(writer, index=False, sheet_name="Normalized")
        summary.to_excel(writer, sheet_name="Summary")

    with open(output_path, "rb") as f:
        st.download_button(
            label="⬇ Download Normalized Output (.xlsx)",
            data=f,
            file_name=output_path,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
