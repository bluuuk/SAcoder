import streamlit as st
from pymongo import MongoClient
import db
from coding import (
    CodingLabels,
)
from state import CodingAction, CodingSession

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
if "coding_session" not in st.session_state:
    st.session_state.coding_session = CodingSession()
if "current_advice" not in st.session_state:
    st.session_state.current_advice = None

def reset(do_rerun : bool = True):
    st.session_state.coding_session.reset()
    if do_rerun:
        st.rerun()

def load_next_advice():
    if collection is None or st.session_state.username is None:
        st.session_state.current_advice = None
        return
    st.session_state.current_advice = db.get_next_advice(collection, st.session_state.username)

def handle_action(action: CodingAction):
    if st.session_state.coding_session.current.is_leaf():
        return
    try:
        st.session_state.coding_session.answer(action)
    except ValueError as error:
        st.error(str(error))

def login():
    st.markdown("""
    # Usage

    - You will apply the SAcoding methodology to classify *security advice items*.
    - By answering a series of up to 10 questions with `yes` or `no`, you will assign a *tag* to each item.
    - You may select `both` for at most one question per item if you can justify both a `yes` and `no` answer. This means at most two tags can be assigned.
    - You can go back to the previous question at any time. If you go back after selecting `both`, all answers for the current item will be reset.
    - You can use the arrow keys to answer questions more quickly.
    - At the end, press `enter` to save your result. If you misclick or misunderstand an item, you can reset and reclassify it before saving.
    - After saving, the assigned tag(s) cannot be changed.
    """)
    
    st.info("Please select your username to continue.")
    username = st.selectbox("Username", options=["C0", "C1", "C2"])
    if st.button("Start Coding", type="primary"):
        st.session_state.username = username
        reset()
    

def save_result():
    advice_doc = st.session_state.current_advice
    if advice_doc is None or collection is None:
        st.error("No advice item is loaded.")
        return

    tags = st.session_state.coding_session.current_tags()
    tag1 = tags[0] if tags else None
    tag2 = tags[1] if len(tags) > 1 else None

    if tag1 is None:
        st.error("No classification is ready to save.")
        return

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

    saved_labels = [CodingLabels[tag] for tag in tags]

    st.toast(f"Saved classification {' + '.join(saved_labels)}", icon="💾")
    load_next_advice()
    reset(False)
    

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

        session = st.session_state.coding_session
        step = session.current
        if not step.is_leaf():
            question = step.question()
            st.subheader(f"{question.code}: {question.text}")
            st.markdown(f"**💡Questions description💡**\n\n*{question.help_text}*")

            top_left, top_center, top_right = st.columns([1, 1, 1])
            with top_center:
                st.button(
                    "Both",
                    shortcut="up",
                    on_click=handle_action,
                    args=(CodingAction.BOTH,),
                    disabled=not session.can_use_both(),
                )

            middle_left, middle_center, middle_right = st.columns([1, 1, 1])
            with middle_left:
                st.button("No", shortcut="left", on_click=handle_action, args=(CodingAction.NO,))
            with middle_right:
                st.button("Yes ", shortcut="right", on_click=handle_action, args=(CodingAction.YES,))

            bottom_left, bottom_center, bottom_right = st.columns([1, 1, 1])
            with bottom_center:
                st.button(
                    "Back",
                    shortcut="down",
                    on_click=st.session_state.coding_session.go_back,
                    disabled=not session.can_go_back(),
                )

        else:
            for tag in session.current_tags():
                st.success(f"➡️ Classified as: **{tag}** ({CodingLabels[tag]})")

            st.markdown("### 🧭 Decision Path")

            for index, completed_path in enumerate(session.all_decision_paths(), start=1):
                st.markdown(f"**Tag {index}: {completed_path.tag} ({CodingLabels[completed_path.tag]})**")
                for entry in completed_path.path:
                    st.write(f"({entry.node.label}) {entry.node.question_text} -> **{entry.action.value}**")

            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.button("💾 Save Result", shortcut="enter", on_click=save_result)
            with col_res2:
                st.button("🔄 Reset",on_click=reset,args=(False,))
