import streamlit as st
from pymongo import MongoClient
import db

DATABASE="dataset"
COLLECTION="advices"


@st.cache_resource
def init_connection():
    """Initialize connection to MongoDB using st.secrets."""
    try:
        # Expected format in .streamlit/secrets.toml:
        # [mongo]
        # uri = "mongodb+srv://..."
        return MongoClient(st.secrets["mongo"]["uri"])
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        return None

mongo = init_connection()

@st.cache_resource
def get_collection():
    """Resolve the configured MongoDB collection."""
    if mongo is None:
        return None
    try:
        return mongo[DATABASE][COLLECTION]
    except Exception as e:
        st.error(f"Failed to access MongoDB collection: {e}")
        return None

collection = get_collection()

class Tree:
    def __init__(self,label : str, yes = None, no = None):
        self.label = label
        self.yes = yes
        self.no = no
    
    def is_leaf(self) -> bool:
        return self.yes is None and self.no is None

Q8 = Tree(label="Q8",       no=Tree("P5"), yes=Tree("P4"))    
Q7 = Tree(label="Q7",       yes=Tree("P6"), no=Q8)    
Q6 = Tree(label="Q6",       no=Tree("P3"), yes=Q7)   
Q5 = Tree(label="Q5",       no=Tree("P1"), yes=Q6)  
Q10 = Tree(label="Q10",     yes=Tree("N"), no=Tree("T'"))  
Q9 = Tree(label="Q9",       yes=Tree("P2"), no=Q10)  
Q4 = Tree(label="Q4",       yes=Q5, no=Q9)  
Q3 = Tree(label="Q3",       yes=Tree("T"), no=Q4)  
Q2 = Tree(label="Q2",       no=Tree("M2"), yes=Q3)  
SAcoding = Tree(label="Q1", no=Tree("M1"), yes=Q2)  

st.set_page_config(page_title="SAcoding Tool", layout="centered")
st.title("🔐 Security Advice Coding")

# ---- STATE ---- #
if "username" not in st.session_state:
    st.session_state.username = None
if "path" not in st.session_state:
    st.session_state.path = [SAcoding]
if "answers" not in st.session_state:
    st.session_state.answers = [] # Added to track Yes/No history properly
if "current_advice" not in st.session_state:
    st.session_state.current_advice = None

# ---- LOGIC ---- #


def clear_decision_path():
    st.session_state.path = [SAcoding]
    st.session_state.answers = []

def load_next_advice():
    if collection is None or st.session_state.username is None:
        st.session_state.current_advice = None
        return
    st.session_state.current_advice = db.get_next_advice(collection, st.session_state.username)

def go_back():
    if len(st.session_state.path) > 1:
        st.session_state.path.pop()
        if st.session_state.answers:
            st.session_state.answers.pop()
    st.rerun()

def reset_tool():
    clear_decision_path()
    st.rerun()

def handle_answer(ans_bool):
    last = st.session_state.path[-1]
    st.session_state.answers.append("Yes" if ans_bool else "No") # Track the text of the answer
    if ans_bool:
        st.session_state.path.append(last.yes)
    else:
        st.session_state.path.append(last.no)

def login():
    st.info("Welcome! Please select your username to continue.")
    username = st.selectbox("Username", options=["C0", "C1"])
    if st.button("Start Coding", type="primary"):
        st.session_state.username = username
        clear_decision_path()
        load_next_advice()
        st.rerun()


def get_advice_text(advice_doc):
    if not advice_doc:
        return None

    for key in ("advice", "text", "content", "body", "sentence"):
        value = advice_doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def save_result():
    advice_doc = st.session_state.current_advice
    if advice_doc is None or collection is None:
        st.error("No advice item is loaded.")
        return

    classification = st.session_state.path[-1].label
    saved = db.submit_tag(
        collection,
        advice_doc["_id"],
        st.session_state.username,
        classification,
    )

    if not saved:
        st.error("Saving failed. The item may already be tagged or unavailable.")
        return

    st.toast(f"Saved classification {classification}", icon="💾")
    clear_decision_path()
    load_next_advice()
    st.rerun()

# ---- DATA ---- #

questions = {
    "Q1":   [
        "Is the item conveyed in unambiguous language and relatively focused?",
        "Does the advice make sense from a language perspective (e.g., it is a sentence that you can read and makes sense), unambiguous (i.e., you can tell what they are trying to convey from a language perspective, not technical), and not multiple items grouped into one piece of advice? Is the advice focused on one topic, whether it is a step to take, an outcome to achieve, or security principle? If the advice seems to have multiple topics being discussed or has multiple outcomes it wants an implementer to reach, this would be considered unfocused."
        ],
    "Q2":   [
        "Is it arguably helpful for security?",
        "Is the advice arguably useful for pursuing security in some way? Does it seem like it will help improve security outcomes rather than processes unrelated to security?"
        ],
    "Q3":   [
        "Is it focused more on a desired outcome than how to achieve it?",
        "Is the advice a high-level outcome rather than some method (or meta-outcome) for how to achieve an outcome? E.g., data is secured in transit would be an outcome because it is a desired goal or state, whereas encrypt data in transit is not because it explains a method for achieving that outcome (in this case, encryption). Encryption may be considered a meta-outcome, as it is not meaningful to the end-user’s ultimate goal of protected data."
        ],
    "Q4":   [
        "Does it suggest a technique, mechanism, software tool, or specific rule?",
        "Is the item a method used in achieving/following the advice? E.g., encryption or replacing a password with black dots are techniques/mechanisms, but secure data or making the password unreadable are not. An example of a specific rule: no hard-coded credentials—this is a rule that is fairly specific as to its goal and would be followed like a practice, but not necessarily with actionable steps."
        ],
    "Q5":   [
        "Does it describe or imply steps or explicit actions to take?",
        "Does the advice suggest actionable technical steps (one or more) that suffice to follow the advice? It has sufficient detail to suggest a step/action to take. Actionable: Involving a known, unambiguous sequence of steps, whose means of execution is generally understood."
        ],
    "Q6":   [
        "Is it viable to accomplish with reasonable resources?",
        "Could the advice item be followed with an acceptable cost?. E.g., the advice would not take years to follow, or have cost out of line with the anticipated benefit."
        ],
    "Q7":   [
        "Is it intended that the end-user carry out this item?",
        "Does the item suggest that the end-user will be responsible for carrying out this practice? Note that end-users first interact with devices after the Creation phase."
        ],
    "Q8":   [
        "Is it intended that a security expert carry out this item?",
        "Does following this advice require an expert understanding of security and security implementation in order to properly follow the advice? Someone following this advice item would have to be an expert in security to be able to understand it and successfully follow it, or be capable of extracting actionable steps from an otherwise non-actionable item based on their experience."
        ],
    "Q9":   [
        "Is it a general policy, general practice, or general procedure?",
        "Is the item a security policy (general rule) to improve security, but is not explicit about what technical means is used? These are less actionable (akin to incompletely specified practicessee definition in Q5), and are not technically explicit. A general policy often has more emphasis on what is (dis)allowed (or may be a general rule closely related to a desired outcome), rather than on how to achieve it."
        ],
    "Q10":  [
        "Is it a broad approach or security property?",
        "Is the item a general way or general strategy, or a property that would improve security? A security property is a characteristic or attribute of a system related to security. E.g., an open design."
        ],
    "Q11":  [
        "Does it relate to a principle in the design?",
        "Some principles relate to the core design phase of the product/system rather than later lifecycle phases."
        ],
}

labels = {
    "M1": "Unclear",
    "M2": "Not Security Related",
    "T": "Outcome",
    "T'": "Outcome",
    "P1": "Incompletely Specified Practice",
    "P2": "General Policy/Approach",
    "P3": "Infeasible Practice",
    "P4": "Security Expert",
    "P5": "IT Specialist",
    "P6": "End-User",
    "N": "Security Principle",
}

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
        reset_tool()
        st.rerun()

    if st.session_state.current_advice is None:
        st.success("No uncoded advice items remain for your alias.")
    else:
        st.markdown("### Advice Item")
        advice_text = st.session_state.current_advice
        if advice_text:
            st.info(advice_text.advice)
        else:
            st.error("Loaded item, but no advice text field was found.")

        step = st.session_state.path[-1]

        if not step.is_leaf():
            # Split the list into question text and help text
            question_text = questions[step.label][0]
            help_text = questions[step.label][1]

            # Display the help text ABOVE the question
            st.subheader(f"{step.label}: {question_text}")
            st.markdown(f"**💡Questions description**\n\n*{help_text}*\n\n*Hint*: Use the keyboard shortcuts left, right and down arrow. By saving a document with `enter` later, you will write it to the database and WON'T see it again!")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.button("No", shortcut="left",on_click=handle_answer, args=(False,))
            with col2:
                st.button("Back", shortcut="up",on_click=go_back)
            with col3:
                st.button("Yes ",shortcut="right",on_click=handle_answer, args=(True,))

        else:
            # Safely get the label, default to "Unknown" if missing from dict
            classification = labels.get(step.label, "Unknown Classification")
            st.success(f"➡️ Classified as: **{step.label}** ({classification})")
            st.markdown("### 🧭 Decision Path")
            # Corrected loop to safely map over the path and the recorded answers
            for i, node in enumerate(st.session_state.path[:-1]):
                ans = st.session_state.answers[i]
                st.write(f"**{node.label}:** {ans}")

            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.button("💾 Save Result", shortcut="enter", on_click=save_result)
            with col_res2:
                st.button("🔄 Reset",on_click=reset_tool)
