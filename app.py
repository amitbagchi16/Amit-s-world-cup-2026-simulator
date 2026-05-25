import os
import json
import pandas as pd
import numpy as np
import streamlit as st


# ============================================================
# FIFA World Cup 2026 Prediction
# Stable Local Version
#
# Required minimum file:
# - world_cup_2026_live_tournament_state_phase10.csv
#
# Optional but recommended:
# - nation_team_strength_features_phase2.csv
# ============================================================


st.set_page_config(
    page_title="FIFA World Cup 2026 Prediction & Interactive Simulation",
    layout="wide"
)

st.title("FIFA World Cup 2026 Prediction & Interactive Simulation")
st.caption(
    "An interactive prediction and scenario simulation tool for exploring FIFA World Cup 2026 outcomes."
)

st.info(
    "This app allows users to explore possible FIFA World Cup 2026 outcomes using data-driven predictions "
    "and interactive scenario testing. Users can update match results, check revised group tables, "
    "generate knockout paths, and observe how the predicted champion changes."
)

with st.expander("Why this matters"):
    st.write(
        """
        Large sporting events create uncertainty for fans, media platforms, sponsors, advertisers, and merchandise sellers. 
        A prediction simulator can help users understand how tournament outcomes may change as real results become available.

        For example, before the tournament, a team may appear as a likely champion based on available data. 
        After each match, updated results can change the group ranking, knockout path, and final prediction. 
        This makes the tool useful not only for football analysis, but also for scenario-based planning.
        """
    )

with st.expander("How to use this app"):
    st.write(
        """
        1. Start with the initial model-based prediction.
        2. Go to the Group Stage Editor.
        3. Enter actual results or manual what-if scores.
        4. Check the updated group tables and Round of 32 qualifiers.
        5. Review the knockout bracket and predicted champion.
        6. Export the simulation result if needed.
        """
    )

# ============================================================
# Helper: find files by prefix
# ============================================================

def find_file_by_prefix(prefix, extension=".csv"):
    files = os.listdir()
    matched = [
        file for file in files
        if file.startswith(prefix) and file.endswith(extension)
    ]
    if matched:
        return matched[0]
    return None


TOURNAMENT_STATE_FILE = find_file_by_prefix(
    "world_cup_2026_live_tournament_state_phase10",
    ".csv"
)

TEAM_STRENGTH_FILE = find_file_by_prefix(
    "nation_team_strength_features_phase2",
    ".csv"
)


if TOURNAMENT_STATE_FILE is None:
    st.error("Missing required file: world_cup_2026_live_tournament_state_phase10.csv")
    st.write("Put this CSV file in the same folder as app.py.")
    st.stop()


# ============================================================
# Load files
# ============================================================

@st.cache_data
def load_tournament_state(file_path):
    return pd.read_csv(file_path)


@st.cache_data
def load_team_strength(file_path):
    if file_path is None:
        return None
    return pd.read_csv(file_path)


original_state = load_tournament_state(TOURNAMENT_STATE_FILE)
team_strength = load_team_strength(TEAM_STRENGTH_FILE)


# ============================================================
# Country name standardisation
# ============================================================

country_name_map = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "USA": "United States",
    "United States": "United States",
    "Korea Republic": "South Korea",
    "South Korea": "South Korea",
    "IR Iran": "Iran",
    "Iran": "Iran",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Ivory Coast": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Czech Republic": "Czech Republic",
    "Türkiye": "Turkey",
    "Turkey": "Turkey",
    "DR Congo": "Congo DR",
    "Democratic Republic of the Congo": "Congo DR",
    "Congo DR": "Congo DR",
    "Cape Verde": "Cape Verde Islands",
    "Cabo Verde": "Cape Verde Islands",
    "Cape Verde Islands": "Cape Verde Islands",
    "Curacao": "Curaçao",
    "Curaçao": "Curaçao",
}


def std_name(name):
    if pd.isna(name):
        return name
    name = str(name).strip()
    return country_name_map.get(name, name)


original_state["team_a"] = original_state["team_a"].apply(std_name)
original_state["team_b"] = original_state["team_b"].apply(std_name)

if team_strength is not None and "nation" in team_strength.columns:
    team_strength["nation"] = team_strength["nation"].apply(std_name)


# ============================================================
# Required columns check
# ============================================================

required_state_columns = [
    "match_id",
    "group",
    "team_a",
    "team_b",
    "model_team_a_score",
    "model_team_b_score",
    "model_team_a_win_probability",
    "model_draw_probability",
    "model_team_b_win_probability",
    "actual_team_a_score",
    "actual_team_b_score",
    "manual_team_a_score",
    "manual_team_b_score",
    "match_status",
    "effective_team_a_score",
    "effective_team_b_score",
    "effective_source",
]

missing_cols = [
    col for col in required_state_columns
    if col not in original_state.columns
]

if missing_cols:
    st.error("Your tournament state file is missing these columns:")
    st.write(missing_cols)
    st.stop()


if "matchday" not in original_state.columns:
    original_state["matchday"] = 1

if "group_letter" not in original_state.columns:
    original_state["group_letter"] = (
        original_state["group"]
        .astype(str)
        .str.replace("Group ", "", regex=False)
    )


# ============================================================
# Team strength dictionary
# ============================================================

def build_strength_dict(team_strength_df):
    if team_strength_df is None:
        return {}

    if "nation" not in team_strength_df.columns:
        return {}

    if "composite_team_strength" not in team_strength_df.columns:
        return {}

    strength = {}

    for _, row in team_strength_df.iterrows():
        team = row["nation"]
        value = row["composite_team_strength"]

        if pd.notna(team) and pd.notna(value):
            strength[team] = float(value)

    return strength


team_strength_dict = build_strength_dict(team_strength)


def get_team_strength(team):
    if team in team_strength_dict:
        return team_strength_dict[team]

    # Conservative fallback if strength is missing
    if len(team_strength_dict) > 0:
        return np.percentile(list(team_strength_dict.values()), 25)

    return 50.0


# ============================================================
# Session state
# ============================================================

if "state" not in st.session_state:
    st.session_state.state = original_state.copy()

if "knockout_overrides" not in st.session_state:
    st.session_state.knockout_overrides = {}


# ============================================================
# Group-stage engine
# ============================================================

def refresh_effective_results(state_df):
    state_df = state_df.copy()

    for idx, row in state_df.iterrows():
        status = row["match_status"]

        if status == "actual_entered":
            state_df.at[idx, "effective_team_a_score"] = row["actual_team_a_score"]
            state_df.at[idx, "effective_team_b_score"] = row["actual_team_b_score"]
            state_df.at[idx, "effective_source"] = "actual_result"

        elif status == "manual_override":
            state_df.at[idx, "effective_team_a_score"] = row["manual_team_a_score"]
            state_df.at[idx, "effective_team_b_score"] = row["manual_team_b_score"]
            state_df.at[idx, "effective_source"] = "manual_override"

        else:
            state_df.at[idx, "effective_team_a_score"] = row["model_team_a_score"]
            state_df.at[idx, "effective_team_b_score"] = row["model_team_b_score"]
            state_df.at[idx, "effective_source"] = "model_prediction"

    return state_df


def calculate_group_tables(state_df):
    all_tables = []

    for group_name, group_matches in state_df.groupby("group", sort=False):
        teams = sorted(
            set(group_matches["team_a"]).union(set(group_matches["team_b"]))
        )

        table = {}

        for team in teams:
            table[team] = {
                "team": team,
                "played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goals_for": 0,
                "goals_against": 0,
                "goal_difference": 0,
                "points": 0,
            }

        for _, match in group_matches.iterrows():
            team_a = match["team_a"]
            team_b = match["team_b"]

            score_a = int(match["effective_team_a_score"])
            score_b = int(match["effective_team_b_score"])

            table[team_a]["played"] += 1
            table[team_b]["played"] += 1

            table[team_a]["goals_for"] += score_a
            table[team_a]["goals_against"] += score_b

            table[team_b]["goals_for"] += score_b
            table[team_b]["goals_against"] += score_a

            if score_a > score_b:
                table[team_a]["wins"] += 1
                table[team_b]["losses"] += 1
                table[team_a]["points"] += 3

            elif score_a < score_b:
                table[team_b]["wins"] += 1
                table[team_a]["losses"] += 1
                table[team_b]["points"] += 3

            else:
                table[team_a]["draws"] += 1
                table[team_b]["draws"] += 1
                table[team_a]["points"] += 1
                table[team_b]["points"] += 1

            table[team_a]["goal_difference"] = (
                table[team_a]["goals_for"] - table[team_a]["goals_against"]
            )

            table[team_b]["goal_difference"] = (
                table[team_b]["goals_for"] - table[team_b]["goals_against"]
            )

        group_table = pd.DataFrame(table.values())
        group_table["group"] = group_name
        group_table["group_letter"] = str(group_name).replace("Group ", "")

        group_table = group_table.sort_values(
            by=["points", "goal_difference", "goals_for"],
            ascending=[False, False, False],
        ).reset_index(drop=True)

        group_table["group_position"] = group_table.index + 1

        all_tables.append(group_table)

    return pd.concat(all_tables, ignore_index=True)


def calculate_qualified_32(group_tables):
    top_two = group_tables[group_tables["group_position"] <= 2].copy()
    third_placed = group_tables[group_tables["group_position"] == 3].copy()

    best_third = third_placed.sort_values(
        by=["points", "goal_difference", "goals_for"],
        ascending=[False, False, False],
    ).head(8).copy()

    top_two["qualification_type"] = "Top 2"
    best_third["qualification_type"] = "Best third-placed"

    qualified = pd.concat([top_two, best_third], ignore_index=True)

    qualified = qualified.sort_values(
        by=["group", "group_position"]
    ).reset_index(drop=True)

    return qualified


# ============================================================
# Knockout engine
# ============================================================

third_place_slots = {
    "M74": ["A", "B", "C", "D", "F"],
    "M77": ["C", "D", "F", "G", "H"],
    "M79": ["C", "E", "F", "H", "I"],
    "M80": ["E", "H", "I", "J", "K"],
    "M81": ["B", "E", "F", "I", "J"],
    "M82": ["A", "E", "H", "I", "J"],
    "M85": ["E", "F", "G", "I", "J"],
    "M87": ["D", "E", "I", "J", "L"],
}


def get_team(qualified, group_letter, position):
    row = qualified[
        (qualified["group_letter"] == group_letter)
        & (qualified["group_position"] == position)
    ]

    if row.empty:
        return None

    return row.iloc[0]["team"]


def assign_third_placed_teams(qualified):
    third_pool = qualified[qualified["group_position"] == 3].copy()

    third_pool = third_pool.sort_values(
        by=["points", "goal_difference", "goals_for"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    third_pool["third_rank"] = third_pool.index + 1

    third_records = third_pool.to_dict("records")

    assignments = {}
    used_groups = set()

    for slot, allowed_groups in third_place_slots.items():
        candidates = [
            record
            for record in third_records
            if record["group_letter"] in allowed_groups
            and record["group_letter"] not in used_groups
        ]

        if not candidates:
            candidates = [
                record
                for record in third_records
                if record["group_letter"] not in used_groups
            ]

        if candidates:
            chosen = sorted(candidates, key=lambda x: x["third_rank"])[0]
            assignments[slot] = chosen["team"]
            used_groups.add(chosen["group_letter"])
        else:
            assignments[slot] = None

    return assignments


def build_round_of_32(qualified):
    t3 = assign_third_placed_teams(qualified)

    matches = [
        {"round": "Round of 32", "match_id": "M73", "team_a": get_team(qualified, "A", 2), "team_b": get_team(qualified, "B", 2)},
        {"round": "Round of 32", "match_id": "M74", "team_a": get_team(qualified, "E", 1), "team_b": t3["M74"]},
        {"round": "Round of 32", "match_id": "M75", "team_a": get_team(qualified, "F", 1), "team_b": get_team(qualified, "C", 2)},
        {"round": "Round of 32", "match_id": "M76", "team_a": get_team(qualified, "C", 1), "team_b": get_team(qualified, "F", 2)},
        {"round": "Round of 32", "match_id": "M77", "team_a": get_team(qualified, "I", 1), "team_b": t3["M77"]},
        {"round": "Round of 32", "match_id": "M78", "team_a": get_team(qualified, "E", 2), "team_b": get_team(qualified, "I", 2)},
        {"round": "Round of 32", "match_id": "M79", "team_a": get_team(qualified, "A", 1), "team_b": t3["M79"]},
        {"round": "Round of 32", "match_id": "M80", "team_a": get_team(qualified, "L", 1), "team_b": t3["M80"]},
        {"round": "Round of 32", "match_id": "M81", "team_a": get_team(qualified, "D", 1), "team_b": t3["M81"]},
        {"round": "Round of 32", "match_id": "M82", "team_a": get_team(qualified, "G", 1), "team_b": t3["M82"]},
        {"round": "Round of 32", "match_id": "M83", "team_a": get_team(qualified, "K", 2), "team_b": get_team(qualified, "L", 2)},
        {"round": "Round of 32", "match_id": "M84", "team_a": get_team(qualified, "H", 1), "team_b": get_team(qualified, "J", 2)},
        {"round": "Round of 32", "match_id": "M85", "team_a": get_team(qualified, "B", 1), "team_b": t3["M85"]},
        {"round": "Round of 32", "match_id": "M86", "team_a": get_team(qualified, "J", 1), "team_b": get_team(qualified, "H", 2)},
        {"round": "Round of 32", "match_id": "M87", "team_a": get_team(qualified, "K", 1), "team_b": t3["M87"]},
        {"round": "Round of 32", "match_id": "M88", "team_a": get_team(qualified, "D", 2), "team_b": get_team(qualified, "G", 2)},
    ]

    matches = [
        match for match in matches
        if match["team_a"] is not None and match["team_b"] is not None
    ]

    return matches


def predict_knockout_match(team_a, team_b):
    strength_a = get_team_strength(team_a)
    strength_b = get_team_strength(team_b)

    if strength_a + strength_b == 0:
        prob_a = 0.5
        prob_b = 0.5
    else:
        prob_a = strength_a / (strength_a + strength_b)
        prob_b = strength_b / (strength_a + strength_b)

    winner = team_a if prob_a >= prob_b else team_b
    loser = team_b if winner == team_a else team_a

    return {
        "team_a": team_a,
        "team_b": team_b,
        "team_a_knockout_probability": round(prob_a, 3),
        "team_b_knockout_probability": round(prob_b, 3),
        "predicted_winner": winner,
        "predicted_loser": loser,
    }


def apply_knockout_override(match_id, predicted_winner):
    return st.session_state.knockout_overrides.get(match_id, predicted_winner)


def simulate_match(match):
    prediction = predict_knockout_match(match["team_a"], match["team_b"])

    winner = apply_knockout_override(
        match["match_id"],
        prediction["predicted_winner"]
    )

    loser = match["team_b"] if winner == match["team_a"] else match["team_a"]

    prediction["predicted_winner"] = winner
    prediction["predicted_loser"] = loser
    prediction["match_id"] = match["match_id"]
    prediction["round"] = match["round"]

    return prediction


def simulate_knockout(qualified):
    all_results = []

    r32 = build_round_of_32(qualified)
    r32_results = [simulate_match(match) for match in r32]
    all_results.extend(r32_results)

    r32_winners = {
        result["match_id"]: result["predicted_winner"]
        for result in r32_results
    }

    r16 = [
        {"round": "Round of 16", "match_id": "M89", "team_a": r32_winners.get("M73"), "team_b": r32_winners.get("M75")},
        {"round": "Round of 16", "match_id": "M90", "team_a": r32_winners.get("M74"), "team_b": r32_winners.get("M77")},
        {"round": "Round of 16", "match_id": "M91", "team_a": r32_winners.get("M76"), "team_b": r32_winners.get("M78")},
        {"round": "Round of 16", "match_id": "M92", "team_a": r32_winners.get("M79"), "team_b": r32_winners.get("M80")},
        {"round": "Round of 16", "match_id": "M93", "team_a": r32_winners.get("M83"), "team_b": r32_winners.get("M84")},
        {"round": "Round of 16", "match_id": "M94", "team_a": r32_winners.get("M81"), "team_b": r32_winners.get("M82")},
        {"round": "Round of 16", "match_id": "M95", "team_a": r32_winners.get("M86"), "team_b": r32_winners.get("M88")},
        {"round": "Round of 16", "match_id": "M96", "team_a": r32_winners.get("M85"), "team_b": r32_winners.get("M87")},
    ]

    r16 = [
        match for match in r16
        if match["team_a"] is not None and match["team_b"] is not None
    ]

    r16_results = [simulate_match(match) for match in r16]
    all_results.extend(r16_results)

    r16_winners = {
        result["match_id"]: result["predicted_winner"]
        for result in r16_results
    }

    qf = [
        {"round": "Quarter-final", "match_id": "M97", "team_a": r16_winners.get("M89"), "team_b": r16_winners.get("M90")},
        {"round": "Quarter-final", "match_id": "M98", "team_a": r16_winners.get("M93"), "team_b": r16_winners.get("M94")},
        {"round": "Quarter-final", "match_id": "M99", "team_a": r16_winners.get("M91"), "team_b": r16_winners.get("M92")},
        {"round": "Quarter-final", "match_id": "M100", "team_a": r16_winners.get("M95"), "team_b": r16_winners.get("M96")},
    ]

    qf = [
        match for match in qf
        if match["team_a"] is not None and match["team_b"] is not None
    ]

    qf_results = [simulate_match(match) for match in qf]
    all_results.extend(qf_results)

    qf_winners = {
        result["match_id"]: result["predicted_winner"]
        for result in qf_results
    }

    sf = [
        {"round": "Semi-final", "match_id": "M101", "team_a": qf_winners.get("M97"), "team_b": qf_winners.get("M98")},
        {"round": "Semi-final", "match_id": "M102", "team_a": qf_winners.get("M99"), "team_b": qf_winners.get("M100")},
    ]

    sf = [
        match for match in sf
        if match["team_a"] is not None and match["team_b"] is not None
    ]

    sf_results = [simulate_match(match) for match in sf]
    all_results.extend(sf_results)

    sf_winners = {
        result["match_id"]: result["predicted_winner"]
        for result in sf_results
    }

    sf_losers = {
        result["match_id"]: result["predicted_loser"]
        for result in sf_results
    }

    third_results = []
    final_results = []

    if "M101" in sf_winners and "M102" in sf_winners:
        third_match = {
            "round": "Third-place Match",
            "match_id": "M103",
            "team_a": sf_losers["M101"],
            "team_b": sf_losers["M102"],
        }

        final_match = {
            "round": "Final",
            "match_id": "M104",
            "team_a": sf_winners["M101"],
            "team_b": sf_winners["M102"],
        }

        third_results = [simulate_match(third_match)]
        final_results = [simulate_match(final_match)]

    all_results.extend(third_results)
    all_results.extend(final_results)

    knockout_df = pd.DataFrame(all_results)

    standings = {
        "champion": final_results[0]["predicted_winner"] if final_results else "-",
        "runner_up": final_results[0]["predicted_loser"] if final_results else "-",
        "third_place": third_results[0]["predicted_winner"] if third_results else "-",
        "fourth_place": third_results[0]["predicted_loser"] if third_results else "-",
    }

    return knockout_df, standings


# ============================================================
# Main calculations
# ============================================================

st.session_state.state = refresh_effective_results(st.session_state.state)

group_tables = calculate_group_tables(st.session_state.state)
qualified_32 = calculate_qualified_32(group_tables)
knockout_df, standings = simulate_knockout(qualified_32)


# ============================================================
# Dashboard
# ============================================================

col1, col2, col3, col4 = st.columns(4)

col1.metric("Champion", standings["champion"])
col2.metric("Runner-up", standings["runner_up"])
col3.metric("Third Place", standings["third_place"])
col4.metric("Fourth Place", standings["fourth_place"])

if TEAM_STRENGTH_FILE is None:
    st.warning(
        "Team strength file was not found. Knockout predictions are using a basic fallback."
    )

st.divider()


tab1, tab2, tab3, tab4 = st.tabs([
    "Group Stage Editor",
    "Live Group Tables",
    "Knockout Bracket",
    "Export",
])


# ============================================================
# Tab 1: Group Stage Editor
# ============================================================

with tab1:
    st.header("Group Stage Result Editor")

    if st.button("Reset All Group Matches to Model Prediction"):
        st.session_state.state = original_state.copy()
        st.session_state.knockout_overrides = {}
        st.rerun()

    groups = list(st.session_state.state["group"].dropna().unique())

    selected_group = st.selectbox("Select group", groups)

    group_matches = (
        st.session_state.state[
            st.session_state.state["group"] == selected_group
        ]
        .sort_values(["matchday", "match_id"])
    )

    for _, match in group_matches.iterrows():
        with st.container(border=True):
            match_id = match["match_id"]
            team_a = match["team_a"]
            team_b = match["team_b"]

            st.subheader(f"{match_id}: {team_a} vs {team_b}")

            st.caption(
                f"Model prediction: {int(match['model_team_a_score'])}-{int(match['model_team_b_score'])} | "
                f"{team_a}: {round(match['model_team_a_win_probability'] * 100)}%, "
                f"Draw: {round(match['model_draw_probability'] * 100)}%, "
                f"{team_b}: {round(match['model_team_b_win_probability'] * 100)}%"
            )

            status_options = {
                "Use Model Prediction": "predicted",
                "Enter Actual Result": "actual_entered",
                "Manual What-if Result": "manual_override",
            }

            current_status = match["match_status"]
            values = list(status_options.values())

            current_index = values.index(current_status) if current_status in values else 0

            selected_status_label = st.radio(
                "Result mode",
                list(status_options.keys()),
                index=current_index,
                horizontal=True,
                key=f"status_{match_id}",
            )

            selected_status = status_options[selected_status_label]

            c1, c2, c3 = st.columns([1, 1, 1])

            with c1:
                score_a = st.number_input(
                    f"{team_a} score",
                    min_value=0,
                    max_value=20,
                    value=int(match["effective_team_a_score"]),
                    key=f"score_a_{match_id}",
                )

            with c2:
                score_b = st.number_input(
                    f"{team_b} score",
                    min_value=0,
                    max_value=20,
                    value=int(match["effective_team_b_score"]),
                    key=f"score_b_{match_id}",
                )

            with c3:
                if st.button("Update Match", key=f"update_{match_id}"):
                    mask = st.session_state.state["match_id"] == match_id

                    if selected_status == "actual_entered":
                        st.session_state.state.loc[mask, "actual_team_a_score"] = score_a
                        st.session_state.state.loc[mask, "actual_team_b_score"] = score_b
                        st.session_state.state.loc[mask, "match_status"] = "actual_entered"

                    elif selected_status == "manual_override":
                        st.session_state.state.loc[mask, "manual_team_a_score"] = score_a
                        st.session_state.state.loc[mask, "manual_team_b_score"] = score_b
                        st.session_state.state.loc[mask, "match_status"] = "manual_override"

                    else:
                        st.session_state.state.loc[mask, "actual_team_a_score"] = np.nan
                        st.session_state.state.loc[mask, "actual_team_b_score"] = np.nan
                        st.session_state.state.loc[mask, "manual_team_a_score"] = np.nan
                        st.session_state.state.loc[mask, "manual_team_b_score"] = np.nan
                        st.session_state.state.loc[mask, "match_status"] = "predicted"

                    st.session_state.knockout_overrides = {}
                    st.rerun()

            st.write(
                f"Effective result used: **{team_a} "
                f"{int(match['effective_team_a_score'])} - "
                f"{int(match['effective_team_b_score'])} {team_b}** "
                f"({match['effective_source']})"
            )


# ============================================================
# Tab 2: Group Tables
# ============================================================

with tab2:
    st.header("Live Group Tables")

    for group in list(group_tables["group"].unique()):
        st.subheader(group)

        display_table = group_tables[
            group_tables["group"] == group
        ][[
            "group_position",
            "team",
            "played",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "goal_difference",
            "points",
        ]]

        st.dataframe(
            display_table,
            use_container_width=True,
            hide_index=True
        )

    st.header("Current Round of 32 Qualifiers")

    qualified_display = qualified_32[[
        "group",
        "group_position",
        "team",
        "points",
        "goal_difference",
        "goals_for",
        "qualification_type",
    ]]

    st.dataframe(
        qualified_display,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# Tab 3: Knockout Bracket
# ============================================================

with tab3:
    st.header("Knockout Bracket")

    if st.button("Reset Knockout Overrides"):
        st.session_state.knockout_overrides = {}
        st.rerun()

    round_order = [
        "Round of 32",
        "Round of 16",
        "Quarter-final",
        "Semi-final",
        "Third-place Match",
        "Final",
    ]

    for round_name in round_order:
        round_df = knockout_df[knockout_df["round"] == round_name]

        if len(round_df) == 0:
            continue

        st.subheader(round_name)

        for _, match in round_df.iterrows():
            with st.container(border=True):
                match_id = match["match_id"]
                team_a = match["team_a"]
                team_b = match["team_b"]

                st.write(f"**{match_id}: {team_a} vs {team_b}**")

                prob_a = round(match["team_a_knockout_probability"] * 100)
                prob_b = round(match["team_b_knockout_probability"] * 100)

                st.caption(
                    f"Knockout probability: {team_a} {prob_a}% | {team_b} {prob_b}%"
                )

                options = [team_a, team_b]

                selected_winner = match["predicted_winner"]
                selected_index = 0 if selected_winner == team_a else 1

                user_choice = st.radio(
                    "Select winner",
                    options,
                    index=selected_index,
                    horizontal=True,
                    key=f"ko_{match_id}",
                )

                if user_choice != selected_winner:
                    st.session_state.knockout_overrides[match_id] = user_choice
                    st.rerun()

                st.write(f"Winner: **{selected_winner}**")


# ============================================================
# Tab 4: Export
# ============================================================

with tab4:
    st.header("Export Current Simulation")

    export = {
        "group_match_state": st.session_state.state.to_dict(orient="records"),
        "group_tables": group_tables.to_dict(orient="records"),
        "qualified_32": qualified_32.to_dict(orient="records"),
        "knockout": knockout_df.to_dict(orient="records"),
        "final_standings": standings,
        "knockout_overrides": st.session_state.knockout_overrides,
    }

    st.download_button(
        "Download Full Simulation JSON",
        data=json.dumps(export, indent=4),
        file_name="world_cup_2026_full_simulation.json",
        mime="application/json",
    )

    st.download_button(
        "Download Group Tables CSV",
        data=group_tables.to_csv(index=False),
        file_name="world_cup_2026_group_tables.csv",
        mime="text/csv",
    )

    st.download_button(
        "Download Knockout CSV",
        data=knockout_df.to_csv(index=False),
        file_name="world_cup_2026_knockout.csv",
        mime="text/csv",
    )


st.divider()

st.caption(
    "Result priority: actual result > manual what-if result > model prediction. "
    "Changing group-stage scores regenerates the group tables, qualifiers, and knockout bracket."
)
