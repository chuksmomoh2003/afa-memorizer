from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "afa_cards.csv"

st.set_page_config(
    page_title="Afa Memorizer",
    page_icon="🧠",
    layout="wide",
)


@st.cache_data
def load_cards() -> pd.DataFrame:
    if not DATA_PATH.exists():
        st.error(f"Could not find {DATA_PATH}. Run the extractor or restore data/afa_cards.csv.")
        st.stop()

    df = pd.read_csv(DATA_PATH).fillna("")
    expected = {"card_id", "chapter", "combination", "igbo_meanings", "english_meanings"}
    missing = expected - set(df.columns)
    if missing:
        st.error(f"The CSV is missing these required columns: {', '.join(sorted(missing))}")
        st.stop()
    return df


def load_progress() -> Dict[str, Any]:
    """Return progress stored privately in the current Streamlit browser session."""
    if "afa_progress" not in st.session_state:
        st.session_state["afa_progress"] = {}
    return st.session_state["afa_progress"]


def save_progress(progress: Dict[str, Any]) -> None:
    """Save progress in Streamlit Session State for the current user session."""
    st.session_state["afa_progress"] = progress


def validate_progress_backup(value: Any) -> Dict[str, Any]:
    """Validate a downloaded progress backup before restoring it."""
    if not isinstance(value, dict):
        raise ValueError("The progress backup must contain a JSON object.")

    cleaned: Dict[str, Any] = {}
    allowed_fields = {
        "box",
        "correct",
        "wrong",
        "seen",
        "due",
        "last_seen",
        "last_grade",
    }

    for card_id, card_info in value.items():
        if not isinstance(card_id, str) or not isinstance(card_info, dict):
            continue
        cleaned[card_id] = {
            key: card_info[key]
            for key in allowed_fields
            if key in card_info
        }

    return cleaned


def default_card_progress() -> Dict[str, Any]:
    return {
        "box": 1,
        "correct": 0,
        "wrong": 0,
        "seen": 0,
        "due": datetime.now().date().isoformat(),
        "last_seen": "",
        "last_grade": "",
    }


def is_due(card_id: str, progress: Dict[str, Any]) -> bool:
    info = progress.get(card_id, default_card_progress())
    try:
        due_date = datetime.fromisoformat(info.get("due", datetime.now().date().isoformat())).date()
    except ValueError:
        due_date = datetime.now().date()
    return due_date <= datetime.now().date()


def grade_card(card_id: str, grade: str, progress: Dict[str, Any]) -> Dict[str, Any]:
    info = progress.get(card_id, default_card_progress())
    box = int(info.get("box", 1))

    # Simple Leitner-style spaced repetition schedule.
    # The better the grade, the farther into the future the card is scheduled.
    if grade == "Again":
        box = max(1, box - 1)
        days = 0
        info["wrong"] = int(info.get("wrong", 0)) + 1
    elif grade == "Hard":
        box = max(1, box)
        days = 1
        info["wrong"] = int(info.get("wrong", 0)) + 1
    elif grade == "Good":
        box = min(6, box + 1)
        days_by_box = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14, 6: 30}
        days = days_by_box.get(box, 7)
        info["correct"] = int(info.get("correct", 0)) + 1
    elif grade == "Easy":
        box = min(6, box + 2)
        days_by_box = {1: 2, 2: 4, 3: 7, 4: 14, 5: 30, 6: 60}
        days = days_by_box.get(box, 14)
        info["correct"] = int(info.get("correct", 0)) + 1
    else:
        days = 0

    info["box"] = box
    info["seen"] = int(info.get("seen", 0)) + 1
    info["due"] = (datetime.now().date() + timedelta(days=days)).isoformat()
    info["last_seen"] = datetime.now().isoformat(timespec="seconds")
    info["last_grade"] = grade
    progress[card_id] = info
    save_progress(progress)
    return progress


def get_filtered_cards(df: pd.DataFrame, chapter: str, due_only: bool, weak_only: bool, progress: Dict[str, Any]) -> pd.DataFrame:
    filtered = df.copy()

    if chapter != "All chapters":
        filtered = filtered[filtered["chapter"] == chapter]

    if due_only:
        due_ids = [cid for cid in filtered["card_id"].tolist() if is_due(cid, progress)]
        filtered = filtered[filtered["card_id"].isin(due_ids)]

    if weak_only:
        weak_ids = []
        for cid in filtered["card_id"].tolist():
            info = progress.get(cid, default_card_progress())
            wrong = int(info.get("wrong", 0))
            correct = int(info.get("correct", 0))
            box = int(info.get("box", 1))
            if wrong > correct or box <= 2:
                weak_ids.append(cid)
        filtered = filtered[filtered["card_id"].isin(weak_ids)]

    return filtered.reset_index(drop=True)


def choose_card(filtered: pd.DataFrame, progress: Dict[str, Any]) -> Dict[str, Any] | None:
    if filtered.empty:
        return None

    # Weight cards so unseen/weak cards appear more often.
    weights = []
    for _, row in filtered.iterrows():
        info = progress.get(row["card_id"], default_card_progress())
        seen = int(info.get("seen", 0))
        box = int(info.get("box", 1))
        wrong = int(info.get("wrong", 0))
        correct = int(info.get("correct", 0))
        weight = 10 + max(0, wrong - correct) * 4 + max(0, 6 - box) * 2 - min(seen, 5)
        weights.append(max(1, weight))

    index = random.choices(range(len(filtered)), weights=weights, k=1)[0]
    return filtered.iloc[index].to_dict()


def prompt_and_answer(row: Dict[str, Any], direction: str) -> Tuple[str, str, str]:
    combo = row["combination"]
    igbo = row["igbo_meanings"]
    english = row["english_meanings"]

    if direction == "Combination → English":
        return combo, english, "Recall the English meaning(s)."
    if direction == "Combination → Igbo":
        return combo, igbo, "Recall the Igbo meaning(s)."
    if direction == "Combination → Both meanings":
        return combo, f"Igbo: {igbo}\n\nEnglish: {english}", "Recall both Igbo and English meanings."
    if direction == "English → Combination":
        return english, combo, "Identify the Afa combination."
    if direction == "Igbo → Combination":
        return igbo, combo, "Identify the Afa combination."

    return combo, f"Igbo: {igbo}\n\nEnglish: {english}", "Recall the meaning(s)."


def reset_current_card() -> None:
    st.session_state.pop("current_card_id", None)
    st.session_state.pop("show_answer", None)
    st.session_state.pop("mcq_options", None)
    st.session_state.pop("mcq_correct", None)
    st.session_state.pop("typed_answer", None)


def get_current_card(filtered: pd.DataFrame, progress: Dict[str, Any]) -> Dict[str, Any] | None:
    if "current_card_id" in st.session_state:
        current = filtered[filtered["card_id"] == st.session_state.current_card_id]
        if not current.empty:
            return current.iloc[0].to_dict()

    row = choose_card(filtered, progress)
    if row is not None:
        st.session_state.current_card_id = row["card_id"]
    return row


def progress_summary(df: pd.DataFrame, progress: Dict[str, Any]) -> Dict[str, int]:
    total = len(df)
    studied = sum(1 for cid in df["card_id"].tolist() if progress.get(cid, {}).get("seen", 0))
    due = sum(1 for cid in df["card_id"].tolist() if is_due(cid, progress))
    mastered = sum(1 for cid in df["card_id"].tolist() if int(progress.get(cid, {}).get("box", 1)) >= 5)
    weak = sum(
        1
        for cid in df["card_id"].tolist()
        if int(progress.get(cid, {}).get("wrong", 0)) > int(progress.get(cid, {}).get("correct", 0))
    )
    return {"total": total, "studied": studied, "due": due, "mastered": mastered, "weak": weak}


def show_grade_buttons(card_id: str, progress: Dict[str, Any]) -> None:
    st.caption("Rate how well you remembered this card:")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Again", use_container_width=True):
            grade_card(card_id, "Again", progress)
            reset_current_card()
            st.rerun()
    with col2:
        if st.button("Hard", use_container_width=True):
            grade_card(card_id, "Hard", progress)
            reset_current_card()
            st.rerun()
    with col3:
        if st.button("Good", use_container_width=True):
            grade_card(card_id, "Good", progress)
            reset_current_card()
            st.rerun()
    with col4:
        if st.button("Easy", use_container_width=True):
            grade_card(card_id, "Easy", progress)
            reset_current_card()
            st.rerun()


def flashcard_view(filtered: pd.DataFrame, progress: Dict[str, Any], direction: str) -> None:
    row = get_current_card(filtered, progress)
    if row is None:
        st.info("No cards match the current filters. Try turning off 'due only' or selecting another chapter.")
        return

    prompt, answer, instruction = prompt_and_answer(row, direction)
    st.subheader(instruction)

    st.markdown(
        f"""
        <div style="border:1px solid #ddd; border-radius:16px; padding:28px; margin:12px 0; font-size:28px; line-height:1.45;">
            <strong>{prompt}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Reveal answer", type="primary", use_container_width=True):
            st.session_state.show_answer = True
    with c2:
        if st.button("Skip / next card", use_container_width=True):
            reset_current_card()
            st.rerun()

    if st.session_state.get("show_answer"):
        st.markdown("### Answer")
        st.markdown(answer.replace("\n", "  \n"))
        st.markdown("---")
        show_grade_buttons(row["card_id"], progress)

    info = progress.get(row["card_id"], default_card_progress())
    st.caption(
        f"Card {row['card_id']} | {row['chapter']} | Box {info.get('box', 1)} | "
        f"Seen {info.get('seen', 0)} time(s) | Due {info.get('due', 'today')}"
    )


def typed_quiz_view(filtered: pd.DataFrame, progress: Dict[str, Any], direction: str) -> None:
    row = get_current_card(filtered, progress)
    if row is None:
        st.info("No cards match the current filters.")
        return

    prompt, answer, instruction = prompt_and_answer(row, direction)
    st.subheader(instruction)
    st.markdown(f"### {prompt}")

    user_answer = st.text_area("Type what you remember before revealing the answer:", key="typed_answer", height=120)

    if st.button("Show correct answer", type="primary"):
        st.session_state.show_answer = True

    if st.session_state.get("show_answer"):
        st.markdown("### Correct answer")
        st.markdown(answer.replace("\n", "  \n"))
        if user_answer:
            st.markdown("### Your answer")
            st.write(user_answer)
        st.markdown("---")
        show_grade_buttons(row["card_id"], progress)


def multiple_choice_view(df: pd.DataFrame, filtered: pd.DataFrame, progress: Dict[str, Any], direction: str) -> None:
    row = get_current_card(filtered, progress)
    if row is None:
        st.info("No cards match the current filters.")
        return

    prompt, answer, instruction = prompt_and_answer(row, direction)
    st.subheader(instruction)
    st.markdown(f"### {prompt}")

    if "mcq_options" not in st.session_state or st.session_state.get("mcq_correct") != answer:
        other_answers = []
        for _, candidate in df.iterrows():
            if candidate["card_id"] == row["card_id"]:
                continue
            _, candidate_answer, _ = prompt_and_answer(candidate.to_dict(), direction)
            if candidate_answer and candidate_answer != answer:
                other_answers.append(candidate_answer)
        distractors = random.sample(other_answers, k=min(3, len(other_answers)))
        options = distractors + [answer]
        random.shuffle(options)
        st.session_state.mcq_options = options
        st.session_state.mcq_correct = answer

    options = ["-- choose an answer --"] + st.session_state.mcq_options
    selected = st.radio("Choose the correct answer:", options, index=0)

    if selected != "-- choose an answer --":
        if selected == answer:
            st.success("Correct.")
            grade = st.selectbox("How did it feel?", ["Good", "Easy", "Hard"], index=0)
        else:
            st.error("Not quite.")
            st.markdown("### Correct answer")
            st.markdown(answer.replace("\n", "  \n"))
            grade = st.selectbox("How should this card be scheduled?", ["Again", "Hard"], index=0)

        if st.button("Save result and continue", type="primary"):
            grade_card(row["card_id"], grade, progress)
            reset_current_card()
            st.rerun()


def search_view(df: pd.DataFrame) -> None:
    st.subheader("Search the Afa corpus")
    query = st.text_input("Search combination, Igbo meaning, or English meaning")
    result = df.copy()
    if query:
        q = query.lower().strip()
        mask = (
            result["combination"].str.lower().str.contains(q, regex=False)
            | result["igbo_meanings"].str.lower().str.contains(q, regex=False)
            | result["english_meanings"].str.lower().str.contains(q, regex=False)
            | result["chapter"].str.lower().str.contains(q, regex=False)
        )
        result = result[mask]

    st.write(f"{len(result)} result(s)")
    st.dataframe(
        result[["chapter", "number_in_chapter", "combination", "igbo_meanings", "english_meanings"]],
        use_container_width=True,
        hide_index=True,
    )


def dashboard_view(df: pd.DataFrame, progress: Dict[str, Any]) -> None:
    st.subheader("Progress dashboard")

    notice = st.session_state.pop("progress_notice", "")
    if notice:
        st.success(notice)

    st.info(
        "Cloud progress is stored in your current browser session. "
        "Download a backup after studying, then restore it when you return."
    )

    summary = progress_summary(df, progress)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total cards", summary["total"])
    c2.metric("Studied", summary["studied"])
    c3.metric("Due today", summary["due"])
    c4.metric("Mastered", summary["mastered"])
    c5.metric("Weak", summary["weak"])

    chapter_rows = []
    for chapter in df["chapter"].unique():
        sub = df[df["chapter"] == chapter]
        s = progress_summary(sub, progress)
        chapter_rows.append({"Chapter": chapter, **s})
    st.dataframe(pd.DataFrame(chapter_rows), use_container_width=True, hide_index=True)

    st.markdown("### Save or restore progress")
    backup_json = json.dumps(progress, indent=2, ensure_ascii=False)

    st.download_button(
        "Download progress backup",
        data=backup_json,
        file_name="afa_progress_backup.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded_backup = st.file_uploader(
        "Restore a progress backup",
        type=["json"],
        help="Choose a progress JSON file previously downloaded from this app.",
    )

    if uploaded_backup is not None:
        if st.button("Restore uploaded progress", type="primary", use_container_width=True):
            try:
                restored_raw = json.loads(uploaded_backup.getvalue().decode("utf-8"))
                restored = validate_progress_backup(restored_raw)
                st.session_state["afa_progress"] = restored
                reset_current_card()
                st.session_state["progress_notice"] = (
                    f"Progress restored for {len(restored)} card(s)."
                )
                st.rerun()
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                st.error(f"Could not restore this backup: {exc}")

    st.markdown("---")
    if st.button("Reset all progress", type="secondary", use_container_width=True):
        st.session_state["afa_progress"] = {}
        reset_current_card()
        st.session_state["progress_notice"] = "Progress has been reset."
        st.rerun()


def main() -> None:
    df = load_cards()
    progress = load_progress()

    st.title("🧠 Afa Memorizer")
    st.caption("Memorize Afa combinations using flashcards, bilingual recall, quizzes, and spaced repetition.")

    with st.sidebar:
        st.header("Practice settings")
        mode = st.radio(
            "Mode",
            ["Flashcards", "Typed quiz", "Multiple choice", "Search", "Dashboard"],
        )

        chapters = ["All chapters"] + list(df["chapter"].unique())
        chapter = st.selectbox("Chapter", chapters)

        direction = st.selectbox(
            "Recall direction",
            [
                "Combination → English",
                "Combination → Igbo",
                "Combination → Both meanings",
                "English → Combination",
                "Igbo → Combination",
            ],
        )

        due_only = st.checkbox("Due cards only", value=False)
        weak_only = st.checkbox("Weak cards only", value=False)

        if st.button("Draw a new card"):
            reset_current_card()
            st.rerun()

        st.markdown("---")
        st.caption("Tip: Start with one chapter and use Combination → Both meanings.")
        st.caption("Cloud edition: use Dashboard to download a progress backup before ending a study session.")

    filtered = get_filtered_cards(df, chapter, due_only, weak_only, progress)

    if mode == "Flashcards":
        flashcard_view(filtered, progress, direction)
    elif mode == "Typed quiz":
        typed_quiz_view(filtered, progress, direction)
    elif mode == "Multiple choice":
        multiple_choice_view(df, filtered, progress, direction)
    elif mode == "Search":
        search_view(df)
    elif mode == "Dashboard":
        dashboard_view(df, progress)


if __name__ == "__main__":
    main()
