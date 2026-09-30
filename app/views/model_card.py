import streamlit as st

from components import model_meta
from core.config import ROOT


def render():
    meta = model_meta()
    m = meta["loo_cv_metrics"]
    st.title("📄 Model card")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ROC-AUC", m["roc_auc"])
    c2.metric("Precision", m["precision"])
    c3.metric("Recall", m["recall"])
    c4.metric("Training rows", m["n"])
    st.caption(m["validation_method"])
    st.markdown((ROOT / "ml" / "model_card.md").read_text())
