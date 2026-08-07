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

ANNOTATION_FOLDER.mkdir(exist_ok=True)

st.set_page_config(
    page_title="STOMP Human Annotation",
    page_icon="📝",
    layout="wide"
)


# =========================================================
# QUESTIONS
# =========================================================

QUESTIONS = {
    2: "If Q1 is Yes or Maybe, quote the specific common space(s) identified.",
    3: "If Q1 is Yes or Maybe, quote the stated town(s), neighborhood(s), or area(s) of the common space.",
    4: "If Q1 is Yes or Maybe, quote the most specific information about the location of the common space.",
    5: "If Q1 is Yes or Maybe, quote laws, rules, guidelines, or social norms alleged to have been violated.",
    6: "If Q5 is not empty, quote who allegedly committed the violation(s).",
    7: "If Q6 is not empty, quote adjectives or adjectival phrases used for the person(s) identified in Q6.",
    8: "If Q5 is not empty, quote the date(s) and/or time(s) of the alleged violation.",
    9: "If Q5 is not empty, quote any sanctions mentioned in connection with the violation.",
    10: "If Q5 is not empty, quote organizations, groups, institutions, authorities, or officials related to the violation.",
    11: "If Q1 is No, quote the most specific location of the event described in the article.",
    12: "If Q1 is No, quote laws, rules, guidelines, or social norms alleged to have been violated.",
    13: "If Q12 is not empty, quote who allegedly committed the violation.",
    14: "If Q13 is not empty, quote adjectives or adjectival phrases used for the person(s) identified in Q13.",
    15: "If Q12 is not empty, quote the date(s) and/or time(s) of the violation.",
    16: "If Q12 is not empty, quote sanctions mentioned in connection with the violation.",
    17: "If Q12 is not empty, quote organizations, groups, institutions, authorities, or officials related to the violation.",
    18: "Quote references to any forms of surveillance or monitoring mentioned in the article.",
    19: "Quote references to separate STOMP articles mentioned in the article."
}


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

    # If "Article Text:" exists
    if article_start is not None:
        article_text = "\n".join(
            lines[article_start:]
        ).strip()

    # Fallback if article format is different
    else:
        article_text = raw_text.strip()

    return {
        "articleid": str(article_id),
        "headline": headline,
        "article_text": article_text
    }


def empty_annotation(article_id):
    """Create blank annotation matching class.jsonl format."""

    result = {
        "articleid": str(article_id),
        "q1_reasoning": "",
        "q1": None
    }

    for number in range(2, 20):
        result[f"q{number}"] = []

    return result


def text_to_array(text):
    """
    One quotation per line becomes one item in the JSON array.
    """

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
    """
    Makes the annotator name safe for filenames.
    """

    name = name.strip()

    name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        name
    )

    return name


def annotation_file_path(annotator):
    """
    Example:
    annotations/Andy_class.jsonl
    """

    clean_name = safe_annotator_name(
        annotator
    )

    return (
        ANNOTATION_FOLDER
        / f"{clean_name}_class.jsonl"
    )


def load_saved_annotations(annotator):
    """
    Read existing JSONL annotations for this annotator.
    """

    path = annotation_file_path(
        annotator
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
    annotations,
    articles
):
    """
    Save annotations as JSONL.

    One article = one line.
    """

    path = annotation_file_path(
        annotator
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as file:

        # Preserve article order
        for article in articles:

            article_id = str(
                article["articleid"]
            )

            if article_id not in annotations:
                continue

            item = annotations[
                article_id
            ]

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


articles = [
    load_article(path)
    for path in article_paths
]


# =========================================================
# PAGE TITLE
# =========================================================

st.title("STOMP Human Annotation")

st.caption(
    "Human annotation interface for STOMP articles"
)


# =========================================================
# ANNOTATOR NAME
# =========================================================

annotator_name = st.sidebar.text_input(
    "Annotator Name",
    placeholder="Example: Andy"
)


if not annotator_name.strip():

    st.info(
        "Please enter your annotator name in the sidebar to begin."
    )

    st.stop()


clean_annotator = safe_annotator_name(
    annotator_name
)


# =========================================================
# INITIALIZE ANNOTATOR SESSION
# =========================================================

session_name_key = "current_annotator"


# If a different annotator enters their name
if (
    session_name_key
    not in st.session_state
    or st.session_state[
        session_name_key
    ] != clean_annotator
):

    st.session_state[
        session_name_key
    ] = clean_annotator

    st.session_state.article_index = 0

    st.session_state.annotations = (
        load_saved_annotations(
            annotator_name
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


# Create blank annotation if none exists
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
    for item
    in st.session_state.annotations.values()
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


    # Article text inside a scrollable-looking text box
    st.text_area(
        "Article Text",
        value=article[
            "article_text"
        ],
        height=750,
        disabled=True,
        key=f"article_text_{article_id}"
    )


# =========================================================
# RIGHT SIDE: ANNOTATION
# =========================================================

with annotation_column:

    st.header(
        "Annotation"
    )

    st.caption(
        "For Q2–Q19, enter one exact quotation per line. "
        "Leave the field blank if there is no applicable quotation."
    )


    q1_reasoning = st.text_area(
        "Q1 Reasoning",
        value=annotation.get(
            "q1_reasoning",
            ""
        ),
        height=120,
        help=(
            "Write one or two sentences explaining "
            "why you selected Y, N, or ?."
        ),
        key=f"reasoning_{article_id}"
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


    responses = {}


    for number in range(2, 20):

        existing_array = annotation.get(
            f"q{number}",
            []
        )

        responses[number] = st.text_area(
            f"Q{number}. {QUESTIONS[number]}",
            value=array_to_text(
                existing_array
            ),
            height=95,
            placeholder=(
                "One exact quotation per line"
            ),
            key=f"q{number}_{article_id}"
        )


# =========================================================
# SAVE CURRENT ARTICLE
# =========================================================

def save_current_annotation():

    new_annotation = {
        "articleid": article_id,
        "q1_reasoning": (
            q1_reasoning.strip()
        ),
        "q1": q1
    }


    for number in range(2, 20):

        new_annotation[
            f"q{number}"
        ] = text_to_array(
            responses[number]
        )


    st.session_state.annotations[
        article_id
    ] = new_annotation


    save_all_annotations(
        annotator_name,
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
    f"{clean_annotator}_class.jsonl"
)


st.sidebar.download_button(
    "⬇ Download class.jsonl",
    data=jsonl_output,
    file_name=download_filename,
    mime="application/json",
    use_container_width=True
)