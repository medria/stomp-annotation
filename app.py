import streamlit as st


st.title("STOMP Annotation")


st.write("Please read the following article.")


st.subheader("Article 9998")


st.write("""
This is an example of the article content that will be read by the annotator.
Later, the actual article content can be loaded from a CSV file.
""")


answer = st.radio(
    "Does this article discuss a common space?",
    ["Yes", "No", "Unclear"]
)


comment = st.text_area("Reason or notes")


if st.button("Save"):
    st.success("The response has been saved successfully.")
    st.write("Answer:", answer)
    st.write("Notes:", comment)