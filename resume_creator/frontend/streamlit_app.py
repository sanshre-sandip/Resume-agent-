import os
import json
import requests
import pandas as pd
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8001")

st.set_page_config(page_title="AI Resume Creator", page_icon="📄", layout="wide")


def api_get(path: str, **kwargs):
    return requests.get(f"{API_BASE}{path}", timeout=120, **kwargs)


def api_post(path: str, payload: dict):
    return requests.post(f"{API_BASE}{path}", json=payload, timeout=600)


def fetch_templates() -> list[str]:
    try:
        r = api_get("/api/templates")
        if r.ok:
            return [t["name"] for t in r.json()] or ["modern", "professional", "simple"]
    except requests.RequestException:
        pass
    return ["modern", "professional", "simple"]


with st.sidebar:
    st.title("📄 AI Resume Creator")
    st.caption(f"Backend: {API_BASE}")
    try:
        health = api_get("/health")
        if health.ok:
            st.success("Backend online")
        else:
            st.error(f"Backend error: {health.status_code}")
    except requests.RequestException:
        st.error("Backend unreachable. Start FastAPI on port 8000.")
    templates = fetch_templates()

tab_create, tab_research, tab_history = st.tabs(["Create Resume", "Job Research", "History"])


with tab_create:
    st.subheader("Build your resume")

    with st.expander("Personal Information", expanded=True):
        c1, c2, c3 = st.columns(3)
        full_name = c1.text_input("Full name", "Jane Doe")
        email = c2.text_input("Email", "jane.doe@example.com")
        phone = c3.text_input("Phone", "+1 555 000 1234")
        c4, c5, c6 = st.columns(3)
        linkedin = c4.text_input("LinkedIn URL", "")
        github = c5.text_input("GitHub URL", "")
        portfolio = c6.text_input("Portfolio URL", "")
        address = st.text_input("Address", "")

    c1, c2 = st.columns(2)
    target_role = c1.text_input("Target role", "Software Engineer")
    template_name = c2.selectbox("Template", templates)

    skills_raw = st.text_input("Skills (comma separated)", "Python, FastAPI, SQL, Docker")

    st.markdown("**Education**")
    education_df = st.data_editor(
        pd.DataFrame([{"degree": "B.Sc. Computer Science", "institution": "State University", "graduation_year": "2020"}]),
        num_rows="dynamic",
        use_container_width=True,
        key="education",
    )

    st.markdown("**Experience**")
    experience_df = st.data_editor(
        pd.DataFrame([{ "company": "Acme Corp", "role": "Backend Developer", "duration": "2021-2024", "description": "Built scalable APIs serving millions of requests."}]),
        num_rows="dynamic",
        use_container_width=True,
        key="experience",
    )

    st.markdown("**Projects**")
    projects_df = st.data_editor(
        pd.DataFrame([{ "name": "Resume Agent", "technologies": "Python, LangGraph", "description": "AI-powered resume generator.", "github_link": ""}]),
        num_rows="dynamic",
        use_container_width=True,
        key="projects",
    )

    st.markdown("**Certificates**")
    certificates_df = st.data_editor(
        pd.DataFrame([{ "name": "", "issuer": "", "date": ""}]),
        num_rows="dynamic",
        use_container_width=True,
        key="certificates",
    )

    def _clean_records(df: pd.DataFrame, required: list[str]) -> list[dict]:
        records = df.fillna("").to_dict(orient="records")
        out = []
        for rec in records:
            rec = {k: ("" if v is None else str(v)).strip() for k, v in rec.items()}
            if all(rec.get(k) for k in required):
                out.append(rec)
        return out

    if st.button("Generate Resume", type="primary"):
        payload = {
            "user_profile": {
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "address": address or None,
                "linkedin": linkedin or None,
                "github": github or None,
                "portfolio": portfolio or None,
            },
            "education": _clean_records(education_df, ["degree", "institution", "graduation_year"]),
            "experience": _clean_records(experience_df, ["company", "role", "duration", "description"]),
            "projects": _clean_records(projects_df, ["name", "technologies", "description"]),
            "certificates": _clean_records(certificates_df, ["name", "issuer", "date"]),
            "skills": [s.strip() for s in skills_raw.split(",") if s.strip()],
            "target_role": target_role,
            "template_name": template_name,
        }
        with st.spinner("Running AI workflow (research → optimize → structure → render → export)..."):
            try:
                r = api_post("/api/resume/create", payload)
            except requests.RequestException as exc:
                st.error(f"Request failed: {exc}")
                r = None

        if r is not None:
            if r.status_code in (200, 201):
                data = r.json()
                st.success(f"Resume generated (id: {data['id']})")
                st.session_state["last_resume"] = data
            else:
                try:
                    detail = r.json().get("detail")
                except Exception:
                    detail = r.text
                st.error(f"Failed ({r.status_code}): {detail}")

    data = st.session_state.get("last_resume")
    if data:
        st.divider()
        st.subheader("Result")
        rid = data["id"]
        col_a, col_b = st.columns(2)

        pdf_ok = data.get("pdf_path") and data["pdf_path"] != "#pending"
        docx_ok = data.get("docx_path") and data["docx_path"] != "#pending"

        if pdf_ok:
            try:
                pdf_resp = api_get(f"/api/resume/{rid}/pdf")
                if pdf_resp.ok:
                    col_a.download_button("Download PDF", pdf_resp.content, file_name=f"resume_{rid}.pdf", mime="application/pdf")
            except requests.RequestException:
                pass
        else:
            col_a.info("PDF not generated (pdflatex/TeX Live not installed). LaTeX source is available below.")

        if docx_ok:
            try:
                docx_resp = api_get(f"/api/resume/{rid}/docx")
                if docx_resp.ok:
                    col_b.download_button("Download DOCX", docx_resp.content, file_name=f"resume_{rid}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            except requests.RequestException:
                pass

        if data.get("latex_content"):
            st.download_button("Download LaTeX (.tex)", data["latex_content"], file_name=f"resume_{rid}.tex", mime="text/x-tex")
            with st.expander("LaTeX source"):
                st.code(data["latex_content"], language="latex")

        if data.get("structured_data"):
            with st.expander("Structured data (JSON)"):
                st.json(data["structured_data"])


with tab_research:
    st.subheader("Research a target role")
    role = st.text_input("Role", "Data Scientist", key="research_role")
    if st.button("Run research"):
        with st.spinner("Researching..."):
            try:
                r = api_get(f"/api/research/{role}")
                if r.ok:
                    rd = r.json()
                    st.caption("Cached" if rd.get("cached") else "Freshly generated")
                    cols = st.columns(2)
                    cols[0].markdown("**Skills**")
                    cols[0].write(rd.get("skills", []))
                    cols[1].markdown("**Keywords**")
                    cols[1].write(rd.get("keywords", []))
                    cols2 = st.columns(2)
                    cols2[0].markdown("**Requirements**")
                    cols2[0].write(rd.get("requirements", []))
                    cols2[1].markdown("**Trending technologies**")
                    cols2[1].write(rd.get("trending_technologies", []))
                else:
                    st.error(f"Research failed ({r.status_code})")
            except requests.RequestException as exc:
                st.error(f"Request failed: {exc}")


with tab_history:
    st.subheader("Resume history")
    if st.button("Refresh history"):
        st.session_state.pop("history", None)
    if "history" not in st.session_state:
        try:
            r = api_get("/api/history")
            st.session_state["history"] = r.json() if r.ok else []
        except requests.RequestException:
            st.session_state["history"] = []
    rows = st.session_state.get("history", [])
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No resumes yet.")
