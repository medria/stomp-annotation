import json
import base64
import re
from pathlib import Path

import streamlit as st


# =========================================================
# SETTINGS
# =========================================================

ARTICLE_FOLDER = Path("article_files")
ANNOTATION_FOLDER = Path("annotations")
SYSTEM_PROMPT_FILE = Path("system_prompt.txt")
ANNOTATION_GUIDE_PDF = Path("STOMP_annotation_guide.pdf")
KNOWN_YES_FILE = Path("AllSubsampleYes.txt")

# Number of articles assigned to each annotator.
# Change this to 20 if you prefer 20 articles per annotator.
NUMBER_OF_BATCHES = 10

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

def show_pdf(pdf_path, height=700):
    """Display a local PDF inside the Streamlit page and provide a download button."""
    if not pdf_path.exists():
        st.warning(
            f"{pdf_path.name} was not found. Please add it to the same GitHub "
            "repository as this app."
        )
        return

    pdf_bytes = pdf_path.read_bytes()
    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    st.markdown(
        f"""
        <iframe
            src="data:application/pdf;base64,{base64_pdf}"
            width="100%"
            height="{height}"
            type="application/pdf">
        </iframe>
        """,
        unsafe_allow_html=True,
    )

    st.download_button(
        "⬇ Download STOMP Annotation Guide (PDF)",
        data=pdf_bytes,
        file_name=pdf_path.name,
        mime="application/pdf",
        use_container_width=True,
    )


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


def load_known_yes_ids():
    """
    Read known Common Space = Yes article IDs from AllSubsampleYes.txt.
    Example line: 2016-06:7438
    """
    yes_ids = set()

    if not KNOWN_YES_FILE.exists():
        return yes_ids

    for line in KNOWN_YES_FILE.read_text(
        encoding="utf-8",
        errors="replace"
    ).splitlines():

        if ":" not in line:
            continue

        _, values = line.split(":", 1)
        values = values.strip()

        if not values:
            continue

        for value in values.split(","):
            value = value.strip()
            if value:
                yes_ids.add(value)

    return yes_ids


def make_representative_batches(article_paths, number_of_batches):
    """
    Create fixed batches with a similar proportion of known-Yes articles
    in every batch.

    The remaining articles form a mixed pool that may include Maybe and No.
    Articles are distributed round-robin so each batch also contains IDs
    from across the full article range.
    """
    known_yes_ids = load_known_yes_ids()

    yes_paths = []
    other_paths = []

    for path in article_paths:
        if path.stem in known_yes_ids:
            yes_paths.append(path)
        else:
            other_paths.append(path)

    yes_paths = sorted(yes_paths, key=natural_sort_key)
    other_paths = sorted(other_paths, key=natural_sort_key)

    batches = [[] for _ in range(number_of_batches)]

    # Spread known Yes articles evenly across batches.
    for i, path in enumerate(yes_paths):
        batches[i % number_of_batches].append(path)

    # Spread the remaining mixed Maybe/No pool evenly across batches.
    # Offset the starting batch to avoid the same ordering pattern.
    offset = len(yes_paths) % number_of_batches

    for i, path in enumerate(other_paths):
        batches[(i + offset) % number_of_batches].append(path)

    # Keep each batch in natural article-ID order for easier navigation.
    for batch in batches:
        batch.sort(key=natural_sort_key)

    return batches, known_yes_ids


def annotation_file_path(annotator, familiarity, batch_id):
    """
    Temporary server-side file for one annotator + one batch.

    Examples:
    annotations/matt_1_B01.jsonl
    annotations/andy_3_B07.jsonl
    """

    clean_name = safe_annotator_name(annotator)

    return (
        ANNOTATION_FOLDER
        / f"{clean_name}_{familiarity}_{batch_id}.jsonl"
    )


def load_saved_annotations(annotator, familiarity, batch_id):
    """Read existing JSONL annotations for this annotator and batch."""
    path = annotation_file_path(
        annotator,
        familiarity,
        batch_id
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
    batch_id,
    annotations,
    articles
):
    """
    Save annotations as JSONL.

    One article = one line.
    """

    path = annotation_file_path(
        annotator,
        familiarity,
        batch_id
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


with st.expander("🧭 How to annotate — step-by-step", expanded=True):
    st.markdown(
        """
1. Enter your information — Enter your name, select your STOMP familiarity, and choose your assigned batch.
2. Read the article — Read the headline and article carefully. You can copy the text if needed.
3. Read the annotation guide — Read the STOMP Annotation Guide before you begin.
4. Answer the questions — Answer all questions based on the article and the guide.
5. Save and continue — Click Save & Next to move to the next article. Use Previous to review earlier articles.
6. Download your JSONL — Download your file every 5–10 articles and again after finishing your batch.
        """
    )

with st.expander("📘 STOMP Annotation Guide (PDF)", expanded=False):

    st.write(
        "Open the guide below for definitions and examples of common spaces, "
        "common space types, and ownership."
    )

    st.pdf(
        "STOMP_annotation_guide.pdf",
        height=720
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

# Batch is added below after the annotator selects it.
annotator_session_id = (
    f"{clean_annotator}_{familiarity}"
)


# =========================================================
# CHOOSE A FIXED REPRESENTATIVE BATCH
# =========================================================

batches, known_yes_ids = make_representative_batches(
    all_article_paths,
    NUMBER_OF_BATCHES
)

batch_options = list(range(1, NUMBER_OF_BATCHES + 1))

batch_number = st.sidebar.selectbox(
    "Assigned Batch",
    options=batch_options,
    index=None,
    placeholder="Choose your assigned batch",
    format_func=lambda x: f"Batch {x:02d}",
    help=(
        "Please use the batch number assigned to you by the research team. "
        "Each batch contains roughly 20–30 articles with a similar mix of "
        "known Yes articles and the remaining Maybe/No pool."
    )
)

if batch_number is None:
    st.info(
        "Please choose your assigned batch in the sidebar to begin."
    )
    st.stop()

assigned_paths = batches[batch_number - 1]

# Only the selected batch is loaded into this annotator's session.
articles = [
    load_article(path)
    for path in assigned_paths
]

batch_id = f"B{batch_number:02d}"

# This count is for researcher verification only; it is not shown to
# annotators as a list of which specific articles are known Yes.
batch_known_yes_count = sum(
    1 for path in assigned_paths
    if path.stem in known_yes_ids
)

annotator_session_id = f"{clean_annotator}_{familiarity}_{batch_id}"


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
            familiarity,
            batch_id
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
    f"**Assigned batch:** {batch_id} ({len(articles)} articles)"
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

    st.header("Annotation")

    # =====================================================
    # Q1
    # =====================================================

    q1_options = ["Yes", "No", "Maybe"]

    existing_q1 = annotation.get("q1")

    q1_index = (
        q1_options.index(existing_q1)
        if existing_q1 in q1_options
        else 0
    )

    q1 = st.radio(
        "Q1. Is the article about a common space or common spaces?",
        options=q1_options,
        index=q1_index,
        horizontal=True,
        key=f"q1_{article_id}"
    )

    # =====================================================
    # Q2 (Only for Yes or Maybe)
    # =====================================================

    if q1 in ["Yes", "Maybe"]:

        st.markdown("---")

        q2 = st.text_area(
            "Q2. If Q1 is Yes or Maybe, quote the specific common space(s) identified.",
            value=array_to_text(annotation.get("q2", [])),
            height=130,
            placeholder="""Example:
void deck
coffee shop
park""",
            help="Enter one common space per line.",
            key=f"q2_{article_id}"
        )

    else:
        q2 = ""

    # =====================================================
    # Q3 & Q4 (Only for Yes)
    # =====================================================

    common_space_type = annotation.get("common_space_type")
    ownership = annotation.get("ownership")

    if q1 == "Yes":

        st.markdown("---")

        common_space_type_options = [
            "Neighborhood common space",
            "Civic common space",
            "Membership common space",
            "None of these"
        ]

        existing_type = annotation.get("common_space_type")

        type_index = (
            common_space_type_options.index(existing_type)
            if existing_type in common_space_type_options
            else 0
        )

        common_space_type = st.radio(
            "Q3. Is the common space a:",
            options=common_space_type_options,
            index=type_index,
            key=f"common_space_type_{article_id}"
        )

        ownership_options = [
            "Public ownership",
            "Private ownership",
            "Mixed ownership"
        ]

        existing_owner = annotation.get("ownership")

        owner_index = (
            ownership_options.index(existing_owner)
            if existing_owner in ownership_options
            else 0
        )

        ownership = st.radio(
            "Q4. Which of the following best describes the ownership of the common space?",
            options=ownership_options,
            index=owner_index,
            key=f"ownership_{article_id}"
        )

    else:
        common_space_type = None
        ownership = None

    # =====================================================
    # NOTES
    # =====================================================

    st.markdown("---")

    notes = st.text_area(
        "Notes (optional)",
        value=annotation.get("notes", ""),
        height=120,
        placeholder="Add any comments here...",
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
        batch_id,
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
    "Important: Download your JSONL backup every 5–10 articles and before "
    "closing or refreshing the browser. Streamlit Cloud storage is temporary."
)

st.sidebar.download_button(
    f"⬇ Download {download_filename}",
    data=jsonl_output,
    file_name=download_filename,
    mime="application/json",
    use_container_width=True
)
