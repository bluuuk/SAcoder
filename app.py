import streamlit as st
from pymongo import MongoClient
import db
from SAcoding import (
    CodingAction,
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
if "both_tag" not in st.session_state:
    st.session_state.both_tag = None
if "current_advice" not in st.session_state:
    st.session_state.current_advice = None

def reset(do_rerun : bool = True):
    st.session_state.current = CodingTree
    st.session_state.path = []
    st.session_state.both_tag = None
    if do_rerun:
        st.rerun()

def load_next_advice():
    if collection is None or st.session_state.username is None:
        st.session_state.current_advice = None
        return
    st.session_state.current_advice = db.get_next_advice(collection, st.session_state.username)

def go_back():
    if st.session_state.path:
        previous_node, action = st.session_state.path.pop()
        if action == CodingAction.BOTH:
            st.session_state.both_tag = None
        st.session_state.current = previous_node

def handle_action(action: CodingAction):
    current_node = st.session_state.current
    if action == CodingAction.BOTH:
        both_tag, _ = current_node.both_transition()
        st.session_state.both_tag = both_tag.label
    st.session_state.path.append((current_node, action))
    st.session_state.current = current_node.next_step(action)

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

    tag1 = st.session_state.current.label
    tag2 = st.session_state.both_tag

    saved = db.submit_tag(
        collection,
        advice_doc["_id"],
        st.session_state.username,
        tag1,
        tag2,
    )

    if not saved:
        st.error("Saving failed. The item may already be tagged or unavailable.")
        return

    saved_labels = [CodingLabels[tag1]]
    if tag2 is not None:
        saved_labels.append(CodingLabels[tag2])

    st.toast(f"Saved classification {' + '.join(saved_labels)}", icon="💾")
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

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.button("No", shortcut="left", on_click=handle_action, args=(CodingAction.NO,))
            with col2:
                st.button("Back", shortcut="down", on_click=go_back)
            with col3:
                st.button(
                    "Both",
                    shortcut="up",
                    on_click=handle_action,
                    args=(CodingAction.BOTH,),
                    disabled=st.session_state.both_tag is not None or not step.supports_both(),
                )
            with col4:
                st.button("Yes ", shortcut="right", on_click=handle_action, args=(CodingAction.YES,))

        else:
            st.success(f"➡️ Classified as: **{step.label}** ({step.classification_label()})")
            st.markdown("### 🧭 Decision Path")

            if st.session_state.both_tag is not None:
                st.markdown(
                    f"**Tag 1: {st.session_state.both_tag} ({CodingLabels[st.session_state.both_tag]})**"
                )
                st.markdown(
                    f"**Tag 2: {step.label} ({step.classification_label()})**"
                )

            for node, action in st.session_state.path:
                st.write(f"{node.question_text} -> **{action.value}**")

            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.button("💾 Save Result", shortcut="enter", on_click=save_result)
            with col_res2:
                st.button("🔄 Reset",on_click=reset,args=(False,))
