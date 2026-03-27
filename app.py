import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="SAcoding Tool", layout="centered")

st.title("🔐 Security Advice Coding (SAcoding)")

# ---- STATE ---- #
if "step" not in st.session_state:
    st.session_state.step = "Q1"

if "history" not in st.session_state:
    st.session_state.history = []

if "path" not in st.session_state:
    st.session_state.path = []

# ---- LOGIC ---- #

def go_to(next_step, answer=None):
    st.session_state.history.append(st.session_state.step)
    if answer:
        st.session_state.path.append((st.session_state.step, answer))
    st.session_state.step = next_step
    st.rerun()

def go_back():
    if st.session_state.history:
        st.session_state.step = st.session_state.history.pop()
        if st.session_state.path:
            st.session_state.path.pop()
        st.rerun()

def reset_tool():
    st.session_state.step = "Q1"
    st.session_state.history = []
    st.session_state.path = []
    st.rerun()

def handle_answer(ans):
    step = st.session_state.step
    if step == "Q1": go_to("M1" if ans == "No" else "Q2", ans)
    elif step == "Q2": go_to("M2" if ans == "No" else "Q3", ans)
    elif step == "Q3": go_to("Q9" if ans == "Yes" else "Q4", ans)
    elif step == "Q4": go_to("T" if ans == "No" else "Q5", ans)
    elif step == "Q5": go_to("P1" if ans == "No" else "Q6", ans)
    elif step == "Q6": go_to("P3" if ans == "No" else "Q7", ans)
    elif step == "Q7": go_to("P6" if ans == "Yes" else "Q8", ans)
    elif step == "Q8": go_to("P4" if ans == "Yes" else "P5", ans)
    elif step == "Q9": go_to("P2" if ans == "Yes" else "Q10", ans)
    elif step == "Q10": go_to("N" if ans == "Yes" else "T", ans)

# ---- DATA ---- #

questions = {
    "Q1": "Is the item conveyed in unambiguous language and relatively focused?",
    "Q2": "Is it arguably helpful for security?",
    "Q3": "Is it focused more on a desired outcome than how to achieve it?",
    "Q4": "Does it suggest a technique, mechanism, software tool, or specific rule?",
    "Q5": "Does it describe or imply steps or explicit actions to take?",
    "Q6": "Is it viable to accomplish with reasonable resources?",
    "Q7": "Is it intended that the end-user carry out this item?",
    "Q8": "Is it intended that a security expert carry out this item?",
    "Q9": "Is it a general policy, general practice, or general procedure?",
    "Q10": "Is it a broad approach or security property?",
}

labels = {
    "M1": "Unclear or Unfocused", "M2": "Not Security Related", "T": "Outcome",
    "P1": "Incompletely Specified Practice", "P2": "General Policy/Approach",
    "P3": "Infeasible Practice", "P4": "Security Expert Practice",
    "P5": "IT Specialist Practice", "P6": "End-User Practice", "N": "Principle",
}

# ---- UI RENDERING ---- #

step = st.session_state.step

if step in questions:
    st.subheader(f"{step}: {questions[step]}")

    col1, col2, col3 = st.columns(3)

    with col1:
        # Native shortcut for Yes
        if st.button("⬅️ Yes", shortcut="y"):
            handle_answer("Yes")

    with col2:
        # Native shortcut for No
        if st.button("No ➡️", shortcut="n"):
            handle_answer("No")
            
    with col3:
        # Native shortcut for Back
        if st.button("⬆️ Back", shortcut="b"):
            go_back()

    st.info("Shortcuts: [Y] for Yes | [N] for No | [B] for Back")

else:
    st.success(f"➡️ Classified as: {step} ({labels[step]})")

    col_res1, col_res2 = st.columns(2)
    
    with col_res1:
        # THE REQUESTED SAVE SHORTCUT
        if st.button("💾 Save Result", shortcut="ctrl+s"):
            st.toast("Logic for saving would trigger here!", icon="💾")

    with col_res2:
        if st.button("🔄 Reset", shortcut="r"):
            reset_tool()

    st.markdown("### 🧭 Decision Path")
    for q, a in st.session_state.path:
        st.write(f"**{q}:** {a}")