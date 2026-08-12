import json
import re
from pathlib import Path

import streamlit as st


# =========================================================
# SETTINGS
# =========================================================

ARTICLE_FOLDER = Path("article_files")
ANNOTATION_FOLDER = Path("annotations")
SYSTEM_PROMPT_FILE = Path("system_prompt.txt")

# Number of articles assigned to each annotator.
# Change this to 20 if you prefer 20 articles per annotator.
ARTICLES_PER_ANNOTATOR = 30

ANNOTATION_FOLDER.mkdir(exist_ok=True)

st.set_page_config(
    page_title="STOMP Human Annotation",
    page_icon="📝",
    layout="wide"
)


# =========================================================
# QUESTIONS
# =========================================================

Q2_TEXT = (
    "If Q1 is Yes or Maybe, quote the specific common space(s) identified."
)


# =========================================================
# FUNCTIONS
# =========================================================

def natural_sort_key(path):
    """Sort filenames numerically where possible."""
    numbers = re.findall(r"\d+", path.stem)

    if numbers:
        return int(numbers[0])

    return path.stem


def load_article(file_path):
    """
    Reads files formatted like:

    ID: 8449
    Headline: Example headline

    Article Text:
    Full article text...
    """

    raw_text = file_path.read_text(
        encoding="utf-8",
        errors="replace"
    )

    article_id = file_path.stem
    headline = ""
    article_text = ""

    lines = raw_text.splitlines()
    article_start = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.lower().startswith("id:"):
            article_id = stripped.split(":", 1)[1].strip()

        elif stripped.lower().startswith("headline:"):
            headline = stripped.split(":", 1)[1].strip()

        elif stripped.lower().startswith("title:"):
            headline = stripped.split(":", 1)[1].strip()

        elif stripped.lower().startswith("article text:"):
            article_start = i + 1
            break

    if article_start is not None:
        article_text = "\n".join(
            lines[article_start:]
        ).strip()
    else:
        article_text = raw_text.strip()

    return {
        "articleid": str(article_id),
        "headline": headline,
        "article_text": article_text
    }


def empty_annotation(article_id):
    """Create a blank annotation for one article."""
    return {
        "articleid": str(article_id),
        "q1": None,
        "q2": [],
        "notes": ""
    }


def text_to_array(text):
    """One quotation per line becomes one item in the JSON array."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def array_to_text(values):
    """Convert JSON array back into textarea text."""
    if not values:
        return ""

    return "\n".join(values)


def safe_annotator_name(name):
    """Make the annotator name safe for filenames."""
    name = name.strip()

    name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        name
    )

    return name


def stable_annotator_offset(annotator, total_articles):
    """
    Create a stable starting position for each annotator.
    This avoids loading all articles into one annotator session and
    gives different annotators different article batches.
    """
    import hashlib

    clean_name = safe_annotator_name(annotator).lower()
    digest = hashlib.sha256(clean_name.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % total_articles


def annotation_file_path(annotator, familiarity):
    """
    Examples:
    annotations/matt_1.jsonl
    annotations/andy_3.jsonl
    """

    clean_name = safe_annotator_name(annotator)

    return (
        ANNOTATION_FOLDER
        / f"{clean_name}_{familiarity}.jsonl"
    )


def load_saved_annotations(annotator, familiarity):
    """Read existing JSONL annotations for this annotator."""
    path = annotation_file_path(
        annotator,
        familiarity
    )

    saved = {}

    if not path.exists():
        return saved

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)

                article_id = str(
                    item["articleid"]
                )

                saved[article_id] = item

            except Exception:
                continue

    return saved


def save_all_annotations(
    annotator,
    familiarity,
    annotations,
    articles
):
    """
    Save annotations as JSONL.

    One article = one line.
    """

    path = annotation_file_path(
        annotator,
        familiarity
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as file:

        for article in articles:
            article_id = str(
                article["articleid"]
            )

            if article_id not in annotations:
                continue

            item = annotations[article_id]

            # Only save articles that have Q1 answered
            if item.get("q1") not in {
                "Y",
                "N",
                "?"
            }:
                continue

            file.write(
                json.dumps(
                    item,
                    ensure_ascii=False
                )
                + "\n"
            )


# =========================================================
# LOAD ARTICLES
# =========================================================

if not ARTICLE_FOLDER.exists():
    st.error(
        "The article_files folder was not found."
    )
    st.stop()


article_paths = sorted(
    list(ARTICLE_FOLDER.glob("*.txt")),
    key=natural_sort_key
)


if not article_paths:
    st.error(
        "No .txt article files were found inside article_files."
    )
    st.stop()


# Keep the full list as paths first. We will load only the batch assigned
# to the current annotator after they enter their name.
all_article_paths = article_paths


# =========================================================
# PAGE TITLE
# =========================================================

st.title("STOMP Human Annotation")

st.caption(
    "Human annotation interface for STOMP articles"
)


# =========================================================
# ANNOTATOR INFORMATION
# =========================================================

st.sidebar.subheader(
    "Annotator Information"
)

annotator_name = st.sidebar.text_input(
    "Annotator Name",
    placeholder="Example: Matt"
)

familiarity = st.sidebar.radio(
    "How familiar are you with STOMP?",
    options=[1, 2, 3],
    format_func=lambda x: {
        1: "1 — Not familiar",
        2: "2 — Moderately familiar",
        3: "3 — Familiar"
    }[x],
    index=None
)


if not annotator_name.strip():
    st.info(
        "Please enter your annotator name in the sidebar to begin."
    )
    st.stop()


if familiarity is None:
    st.info(
        "Please select your familiarity with STOMP in the sidebar to begin."
    )
    st.stop()


clean_annotator = safe_annotator_name(
    annotator_name
)

annotator_session_id = (
    f"{clean_annotator}_{familiarity}"
)


# =========================================================
# ASSIGN A SMALL, STABLE ARTICLE BATCH TO THIS ANNOTATOR
# =========================================================

batch_size = min(ARTICLES_PER_ANNOTATOR, len(all_article_paths))
start = stable_annotator_offset(annotator_name, len(all_article_paths))

# Wrap around if the batch reaches the end of the article list.
assigned_paths = [
    all_article_paths[(start + i) % len(all_article_paths)]
    for i in range(batch_size)
]

# Only these 20/30 article files are read for this annotator.
articles = [
    load_article(path)
    for path in assigned_paths
]

batch_id = f"B{start + 1}"


# =========================================================
# INITIALIZE ANNOTATOR SESSION
# =========================================================

session_name_key = "current_annotator"


if (
    session_name_key not in st.session_state
    or st.session_state[session_name_key] != annotator_session_id
):
    st.session_state[
        session_name_key
    ] = annotator_session_id

    st.session_state.article_index = 0

    st.session_state.annotations = (
        load_saved_annotations(
            annotator_name,
            familiarity
        )
    )


if "article_index" not in st.session_state:
    st.session_state.article_index = 0


if "annotations" not in st.session_state:
    st.session_state.annotations = {}


# =========================================================
# GUIDELINES
# =========================================================

with st.sidebar.expander(
    "📖 Full Annotation Guidelines"
):
    if SYSTEM_PROMPT_FILE.exists():
        prompt_text = (
            SYSTEM_PROMPT_FILE
            .read_text(
                encoding="utf-8"
            )
        )

        st.text(prompt_text)

    else:
        st.warning(
            "system_prompt.txt was not found."
        )


# =========================================================
# CURRENT ARTICLE
# =========================================================

index = st.session_state.article_index

article = articles[index]

article_id = str(
    article["articleid"]
)


if article_id not in st.session_state.annotations:
    st.session_state.annotations[
        article_id
    ] = empty_annotation(
        article_id
    )


annotation = (
    st.session_state.annotations[
        article_id
    ]
)


# =========================================================
# SIDEBAR PROGRESS
# =========================================================

completed = sum(
    1
    for item in st.session_state.annotations.values()
    if item.get("q1") in {
        "Y",
        "N",
        "?"
    }
)


st.sidebar.markdown("---")

st.sidebar.write(
    f"**Annotator:** {annotator_name}"
)

st.sidebar.write(
    f"**STOMP familiarity:** {familiarity}"
)

st.sidebar.write(
    f"**Assigned batch:** {batch_id}"
)

st.sidebar.write(
    f"**Completed:** {completed} / {len(articles)}"
)

st.sidebar.progress(
    completed / len(articles)
)


# =========================================================
# ARTICLE POSITION
# =========================================================

st.write(
    f"### Article {index + 1} of {len(articles)}"
)

st.caption(
    f"Article ID: {article_id}"
)


# =========================================================
# TWO COLUMN LAYOUT
# =========================================================

article_column, annotation_column = (
    st.columns(
        [1.15, 1],
        gap="large"
    )
)


# =========================================================
# LEFT SIDE: ARTICLE
# =========================================================

with article_column:

    if article["headline"]:
        st.header(
            article["headline"]
        )
    else:
        st.header(
            f"Article {article_id}"
        )

    st.markdown("---")

    # Selectable/copyable article text with high-contrast dark text.
    # st.text_area(..., disabled=True) can appear light grey in some themes.
    import html

    safe_article_text = html.escape(article["article_text"]).replace("\n", "<br>")

    st.markdown(
        f"""
        <div style="
            height: 750px;
            overflow-y: auto;
            padding: 18px;
            border: 1px solid rgba(128,128,128,0.35);
            border-radius: 8px;
            background: white;
            color: #111111;
            font-size: 16px;
            line-height: 1.6;
            white-space: normal;
            user-select: text;
            -webkit-user-select: text;
        ">
            {safe_article_text}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.caption("Tip: You can select and copy text directly from the article above.")


# =========================================================
# RIGHT SIDE: ANNOTATION
# =========================================================

with annotation_column:

    st.header(
        "Annotation"
    )

    q1_options = [
        "Y",
        "N",
        "?"
    ]

    existing_q1 = annotation.get(
        "q1"
    )

    q1_index = (
        q1_options.index(existing_q1)
        if existing_q1 in q1_options
        else None
    )

    q1 = st.radio(
        "Q1. Is the article about a common space or common spaces?",
        options=q1_options,
        index=q1_index,
        horizontal=True,
        key=f"q1_{article_id}"
    )

    if q1 == "Y":
        st.success(
            "Y = Yes"
        )

    elif q1 == "N":
        st.info(
            "N = No"
        )

    elif q1 == "?":
        st.warning(
            "? = Maybe / Unclear"
        )

    st.markdown("---")

    q2 = st.text_area(
        f"Q2. {Q2_TEXT}",
        value=array_to_text(
            annotation.get(
                "q2",
                []
            )
        ),
        height=130,
        placeholder=(
            "One exact quotation per line"
        ),
        help=(
            "Enter one exact quotation per line. "
            "Leave blank if it is not applicable."
        ),
        key=f"q2_{article_id}"
    )

    st.markdown("---")

    notes = st.text_area(
        "Notes (optional)",
        value=annotation.get(
            "notes",
            ""
        ),
        height=120,
        placeholder=(
            "Add anything else you would like to note about this article."
        ),
        key=f"notes_{article_id}"
    )


# =========================================================
# SAVE CURRENT ARTICLE
# =========================================================

def save_current_annotation():

    new_annotation = {
        "articleid": article_id,
        "q1": q1,
        "q2": text_to_array(q2),
        "notes": notes.strip()
    }

    st.session_state.annotations[
        article_id
    ] = new_annotation

    save_all_annotations(
        annotator_name,
        familiarity,
        st.session_state.annotations,
        articles
    )


# =========================================================
# NAVIGATION BUTTONS
# =========================================================

st.markdown("---")

previous_col, save_col, next_col = (
    st.columns(3)
)


with previous_col:

    if st.button(
        "⬅ Previous",
        use_container_width=True,
        disabled=(index == 0)
    ):
        save_current_annotation()

        st.session_state.article_index -= 1

        st.rerun()


with save_col:

    if st.button(
        "💾 Save",
        use_container_width=True
    ):
        save_current_annotation()

        st.success(
            "Annotation saved successfully."
        )


with next_col:

    button_label = (
        "Save & Finish"
        if index == len(articles) - 1
        else "Save & Next ➡"
    )

    if st.button(
        button_label,
        type="primary",
        use_container_width=True
    ):
        save_current_annotation()

        if index < len(articles) - 1:
            st.session_state.article_index += 1

            st.rerun()

        else:
            st.success(
                "You have reached the final article."
            )


# =========================================================
# EXPORT JSONL
# =========================================================

st.sidebar.markdown("---")

st.sidebar.subheader(
    "Download Results"
)


jsonl_lines = []


for article_item in articles:

    item_id = str(
        article_item[
            "articleid"
        ]
    )

    if item_id not in st.session_state.annotations:
        continue

    saved_item = (
        st.session_state.annotations[
            item_id
        ]
    )

    if saved_item.get("q1") not in {
        "Y",
        "N",
        "?"
    }:
        continue

    jsonl_lines.append(
        json.dumps(
            saved_item,
            ensure_ascii=False
        )
    )


jsonl_output = "\n".join(
    jsonl_lines
)


download_filename = (
    f"{clean_annotator}_{familiarity}_{batch_id}.jsonl"
)


st.sidebar.caption(
    "Please download a backup periodically and before closing the app."
)

st.sidebar.download_button(
    f"⬇ Download {download_filename}",
    data=jsonl_output,
    file_name=download_filename,
    mime="application/json",
    use_container_width=True
)
