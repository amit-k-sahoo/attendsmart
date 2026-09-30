import streamlit as st

from auth_state import current_user
from chatbot.engine import ChatEngine
from chatbot.identity import identity_from_user
from core.config import settings

STUDENT_PROMPTS = ["What's my attendance risk?", "Why am I flagged?", "What should I do?",
                   "Talk to my advisor"]
STAFF_PROMPTS = ["Who's at risk?", "How is Suyash Jain doing?", "Why is Abhijit Wagh flagged?",
                 "How does the prediction work?"]


def _engine(user):
    eng = st.session_state.get("chat_engine")
    if eng is None or eng.identity.get("user_id") != user.id:
        eng = ChatEngine(identity_from_user(user))
        st.session_state.chat_engine = eng
        st.session_state.chat_history = []
    return eng


def _ask(engine, text):
    st.session_state.chat_history.append({"role": "user", "text": text})
    res = engine.handle(text)
    meta = f"{res['source']} · intent `{res['intent']}`"
    if res.get("confidence") is not None:
        meta += f" · confidence {res['confidence']:.2f}"
    st.session_state.chat_history.append({"role": "assistant", "text": res["text"], "meta": meta})


def render():
    user = current_user()
    engine = _engine(user)

    st.title("💬 Assistant")
    if settings.dialogflow_enabled:
        st.caption(f"Powered by **Dialogflow ES** (project `{settings.dialogflow_project_id}`) "
                   "with AttendSmart webhook fulfillment.")
    else:
        st.caption("Running the **local intent engine** — set `DIALOGFLOW_PROJECT_ID` to route "
                   "through Dialogflow ES. Same intents, same answers, same access rules.")

    history = st.session_state.chat_history
    if not history:
        with st.chat_message("assistant"):
            st.markdown(f"Hi {user.full_name.split()[0]}! Ask me about attendance risk, why "
                        "someone was flagged, or what to do next.")
        prompts = STAFF_PROMPTS if user.is_staff else STUDENT_PROMPTS
        cols = st.columns(len(prompts))
        for col, p in zip(cols, prompts):
            if col.button(p, use_container_width=True):
                _ask(engine, p)
                st.rerun()

    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["text"])
            if turn.get("meta"):
                st.caption(turn["meta"])

    if prompt := st.chat_input("Ask AttendSmart…"):
        _ask(engine, prompt)
        st.rerun()

    if history and st.button("Clear conversation"):
        st.session_state.pop("chat_engine", None)
        st.rerun()
