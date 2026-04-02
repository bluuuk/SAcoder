import streamlit as st
from pymongo import MongoClient
import db
from SAcoding import (
    CodingLabels,
    CodingTree,
)

if not st.secrets.get("mongo"):
    st.error("Missing `mongo` configuration in Streamlit secrets. Add a `[mongo]` section before running the app.")
    st.stop()
      
DATABASE=st.secrets["mongo"].get("database","dataset")
COLLECTION=st.secrets["mongo"].get("collection","advices")

@st.cache_resource
def get_collection():
    try:
        client = MongoClient(st.secrets["mongo"]["uri"])
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        return None
    try:
        return client[DATABASE][COLLECTION]
    except Exception as e:
        st.error(f"Failed to access MongoDB collection: {e}")
        return None

collection = get_collection()

"""
Coding tree according to <https://academic.oup.com/cybersecurity/article/9/1/tyad013/7217003> 
"""

st.set_page_config(page_title="SAcoding Tool", layout="centered")
st.title("🔐 Security Advice Coding")

if "username" not in st.session_state:
    st.session_state.username = None
if "current" not in st.session_state:
    st.session_state.current = CodingTree
if "path" not in st.session_state:
    st.session_state.path = []
if "current_advice" not in st.session_state:
    st.session_state.current_advice = None

def reset(do_rerun : bool = True):
    st.session_state.current = CodingTree
    st.session_state.path = []
    if do_rerun:
        st.rerun()

def load_next_advice():
    if collection is None or st.session_state.username is None:
        st.session_state.current_advice = None
        return
    st.session_state.current_advice = db.get_next_advice(collection, st.session_state.username)

def go_back():
    if st.session_state.path:
        previous_node, _ = st.session_state.path.pop()
        st.session_state.current = previous_node

def handle_answer(ans : bool):
    current_node = st.session_state.current
    answer_label = "Yes" if ans else "No"
    st.session_state.path.append((current_node, answer_label))
    st.session_state.current = current_node.next_step(ans)

def login():
    st.info("Welcome! Please select your username to continue.")
    username = st.selectbox("Username", options=["C0", "C1"])
    if st.button("Start Coding", type="primary"):
        st.session_state.username = username
        reset()

def save_result():
    advice_doc = st.session_state.current_advice
    if advice_doc is None or collection is None:
        st.error("No advice item is loaded.")
        return

    tag = st.session_state.current
    saved = db.submit_tag(
        collection,
        advice_doc["_id"],
        st.session_state.username,
        tag.label,
    )

    if not saved:
        st.error("Saving failed. The item may already be tagged or unavailable.")
        return

    st.toast(f"Saved classification {CodingLabels[tag.label]}", icon="💾")
    load_next_advice()
    reset(False)
    

# ---- UI RENDERING ---- #

if st.session_state.username is None:
    login()
else:
    if st.session_state.current_advice is None:
        load_next_advice()

    st.sidebar.write(
        f"Logged in as: **{st.session_state.username}**"
    )
    if collection is not None and st.session_state.username is not None:
        st.sidebar.write(
            f"Remaining items: **{db.remaining_tags(collection, st.session_state.username)}**"
        )
    if st.sidebar.button("Logout"):
        st.session_state.username = None
        st.session_state.current_advice = None
        reset()

    if st.session_state.current_advice is None:
        st.success("No remaining advice items :)")
    else:
        st.markdown("## Advice Item")
        advice_text = st.session_state.current_advice
        if advice_text:
            st.info(advice_text["advice"])
        else:
            st.error("Loaded item, but no advice text field was found.")

        step = st.session_state.current
        question = step.question()

        if question is not None:
            # Display the help text ABOVE the question
            st.subheader(f"{question.code}: {question.text}")
            st.markdown(f"**💡Questions description💡**\n\n*{question.help_text}*\n\n*Hint*: Use the keyboard shortcuts left, right and down arrow. By saving a document with `enter` later, you will write it to the database and WON'T see it again!")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.button("No", shortcut="left",on_click=handle_answer, args=(False,))
            with col2:
                st.button("Back", shortcut="up",on_click=go_back)
            with col3:
                st.button("Yes ",shortcut="right",on_click=handle_answer, args=(True,))

        else:
            st.success(f"➡️ Classified as: **{step.label}** ({step.classification_label()})")
            st.markdown("### 🧭 Decision Path")
            
            for path_item in step.decision_path(st.session_state.path):
                question_text, answer = path_item.rsplit(" -> ", 1)
                st.write(f"{question_text} -> **{answer}**")

            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.button("💾 Save Result", shortcut="enter", on_click=save_result)
            with col_res2:
                st.button("🔄 Reset",on_click=reset,args=(False,))
