import streamlit as st
import xmlrpc.client
import re
from collections import Counter
import spacy

# Load spaCy English model (will download at runtime if missing - see below)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")


# Constants - fixed values
ODOO_URL = "https://sba.info-solutions-pvt.odoo.com"
ODOO_DB = "sba.info-solutions-pvt"  # Make sure this is your actual DB name
PROJECT_MANAGER = "Sadeesh"
CATEGORY_OPTIONS = ["R&D", "Client Projects", "Internal Development"]

# Assignees mapped from display name to Odoo login/email (update to your actual values!)
ASSIGNEES = {
    "Jagadeep": "jagadeep@example.com",
    "Sri Hari": "srihari@example.com",
    "Hari": "hari@example.com",
    "Ajith Kumar": "ajithkumar@example.com",
    "Nithiyan": "nithiyan@example.com"
}

# ---------------------- Streamlit UI ----------------------------

st.title("🚀 SBA Sprint Planning Assistant")

# Credentials input (do not assign st.session_state keys manually)
with st.expander("🔒 Enter your Odoo Credentials", expanded=True):
    st.text_input("Odoo Login (email)", key="odoo_login")
    st.text_input("Odoo Password", type="password", key="odoo_pass")

# Halt if credentials are missing
if ("odoo_login" not in st.session_state or not st.session_state["odoo_login"] or
        "odoo_pass" not in st.session_state or not st.session_state["odoo_pass"]):
    st.info("Please enter your Odoo login credentials above to proceed.")
    st.stop()

# ---------------------- Odoo Connection Helpers ----------------

def odoo_connect():
    uid = None
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        uid = common.authenticate(ODOO_DB, st.session_state["odoo_login"], st.session_state["odoo_pass"], {})
        if not uid:
            st.error("❌ Authentication failed! Check your Odoo credentials.")
            st.stop()
    except Exception as e:
        st.error(f"❌ Connection or authentication error: {e}")
        st.stop()
    return uid, models

def get_user_id(login):
    uid, models = odoo_connect()
    try:
        user_ids = models.execute_kw(
            ODOO_DB, uid, st.session_state["odoo_pass"],
            'res.users', 'search', [[['login', '=', login]]]
        )
        return user_ids[0] if user_ids else None
    except Exception as e:
        st.error(f"Error fetching user ID for login '{login}': {e}")
        return None

def get_stage_id(stage_name):
    uid, models = odoo_connect()
    try:
        stage_ids = models.execute_kw(
            ODOO_DB, uid, st.session_state["odoo_pass"],
            'project.project', 'search', [[['name', '=', stage_name]]]
        )
        return stage_ids[0] if stage_ids else None
    except Exception as e:
        st.error(f"Error fetching stage ID for '{stage_name}': {e}")
        return None

def get_or_create_tag(tag_name, color=1):
    uid, models = odoo_connect()
    try:
        tag_name_clean = tag_name.strip().replace(",", "")
        tag_ids = models.execute_kw(
            ODOO_DB, uid, st.session_state["odoo_pass"],
            'project.tags', 'search', [[['name', '=', tag_name_clean]]]
        )
        if tag_ids:
            return tag_ids[0]
        else:
            new_id = models.execute_kw(
                ODOO_DB, uid, st.session_state["odoo_pass"],
                'project.tags', 'create', [{'name': tag_name_clean, 'color': color}]
            )
            return new_id
    except Exception as e:
        st.error(f"Error creating tag '{tag_name}': {e}")
        return None


# ------------ Text & Metadata Processors ----------------

def text_to_html(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'([📋🔧✅🎯🏅])\s*<b>(.+?)</b>', r'<h4>\1 \2</h4>', text)
    text = re.sub(r'([📋🔧✅🎯🏅])\s*([A-Z ]+)', r'<h4>\1 \2</h4>', text)
    return text.replace("\n", "<br>")

def suggest_tags(text, top_n=5):
    doc = nlp(text.lower())
    nouns = [token.lemma_ for token in doc if token.pos_ in ["NOUN", "PROPN"] and not token.is_stop]
    freq = Counter(nouns)
    tags = [k.capitalize() for k,v in freq.most_common(top_n)]
    return list(dict.fromkeys(tags))

def extract_subtasks(description):
    lines = description.splitlines()
    subtasks = []
    stage = False
    pattern = re.compile(r'\b(subgoals?|subtasks?|tasks?)\b', re.I)
    for line in lines:
        if not stage and pattern.search(line):
            stage = True
            continue
        if stage:
            m = re.match(r'^\s*[-*•]\s+(.*)', line)
            if m:
                subtasks.append(m.group(1).strip())
            elif line.strip() == '' or line.startswith("#") or line.startswith(">"):
                continue
            else:
                break
    return subtasks


# ----------------- Project and Task CRUD -------------------

def create_project(name, category, description_html):
    uid, models = odoo_connect()
    stage_id = get_stage_id(category)
    project_data = {
        "name": name,
        "active": True,
        "description": description_html,
    }
    if stage_id:
        project_data["stage_id"] = stage_id
    try:
        project_id = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"], 'project.project', 'create', [project_data])
        return project_id
    except Exception as e:
        st.error(f"Failed to create project: {e}")
        return None

def create_task(project_id, title, desc, tags, assignee_login=None, parent_id=None):
    uid, models = odoo_connect()
    tag_ids = []
    for tag in tags:
        tid = get_or_create_tag(tag)
        if tid:
            tag_ids.append(tid)
    task_data = {
        "name": title,
        "project_id": project_id,
        "description": text_to_html(desc) if desc else "",
    }
    if tag_ids:
        task_data["tag_ids"] = [(6, 0, tag_ids)]
    if parent_id:
        task_data["parent_id"] = parent_id
    if assignee_login:
        user_id = get_user_id(assignee_login)
        if user_id:
            task_data["user_ids"] = [(6, 0, [user_id])]
        else:
            st.warning(f"Assignee '{assignee_login}' not found; task will be unassigned.")
    try:
        task_id = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"], 'project.task', 'create', [task_data])
        return task_id
    except Exception as e:
        st.error(f"Failed to create task: {e}")
        return None


# ------------------- Streamlit UI ---------------------

st.header("Create New Project")

with st.form("project_form"):
    proj_name = st.text_input("Project Name", value="New Project")
    proj_category = st.selectbox("Project Category", options=CATEGORY_OPTIONS)
    proj_desc = st.text_area("Project Description (Markdown)", height=200)
    submitted_proj = st.form_submit_button("Create Project")

if submitted_proj:
    html_desc = text_to_html(proj_desc)
    new_proj_id = create_project(proj_name, proj_category, html_desc)
    if new_proj_id:
        st.session_state["project_id"] = new_proj_id
        st.session_state["project_name"] = proj_name
        st.success(f"Project '{proj_name}' created.")

# Only allow task entry if project created
if "project_id" in st.session_state:
    st.header(f"Add Tasks to Project: {st.session_state['project_name']}")

    with st.form("task_form"):
        task_title = st.text_input("Task Title")
        task_desc = st.text_area("Task Description", height=150)
        suggested_tags = suggest_tags(task_desc)
        task_tags = st.multiselect("Tags", options=suggested_tags, default=suggested_tags)
        manual_tag = st.text_input("Add Additional Tag")
        if manual_tag and manual_tag.strip():
            if manual_tag.strip() not in task_tags:
                task_tags.append(manual_tag.strip())

        selected_assignee = st.selectbox("Assign to", options=list(ASSIGNEES.keys()))
        assignee_login = ASSIGNEES[selected_assignee]

        subtasks_candidates = extract_subtasks(task_desc)
        selected_subtasks = st.multiselect("Pick Subtasks", options=subtasks_candidates, default=subtasks_candidates)
        manual_subtasks_raw = st.text_area("Add Additional Subtasks (one per line)")

        submitted_task = st.form_submit_button("Add Task")
        if submitted_task:
            if not task_title.strip():
                st.warning("Task title is required!")
            else:
                pid = st.session_state["project_id"]
                tid = create_task(pid, task_title, task_desc, task_tags, assignee_login)
                if tid:
                    st.success(f"Task '{task_title}' created.")
                    sub_count = 0
                    # create selected subtasks
                    for stask in selected_subtasks:
                        create_task(pid, stask, "", [], None, parent_id=tid)
                        sub_count += 1
                    # create manual subtasks
                    manual_subtasks = [line.strip() for line in manual_subtasks_raw.splitlines() if line.strip()]
                    for mstask in manual_subtasks:
                        create_task(pid, mstask, "", [], None, parent_id=tid)
                        sub_count += 1
                    if sub_count > 0:
                        st.success(f"{sub_count} subtasks created.")

                    st.experimental_rerun()  # restart app to refresh data

    # Show all tasks and subtasks
    st.subheader("Current Tasks")
    uid, models = odoo_connect()
    try:
        tasks = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"], "project.task", "search_read",
                        [[["project_id", "=", st.session_state["project_id"]]]],
                        {"fields": ["id", "name", "description", "tag_ids", "user_ids", "parent_id"]})
    except Exception as e:
        st.error(f"Failed to fetch tasks: {e}")
        tasks = []

    if not tasks:
        st.info("No tasks found.")
    else:
        # Display tasks in parent-child hierarchy
        top_tasks = [t for t in tasks if not t["parent_id"]]
        id_to_task = {t["id"]: t for t in tasks}
        for task in top_tasks:
            # show main task info
            tag_names = []
            if task["tag_ids"]:
                tags = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"], "project.tags", "read", [task["tag_ids"]], {"fields": ["name"]})
                tag_names = [tag["name"] for tag in tags]
            users = []
            if task["user_ids"]:
                users = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"], "res.users", "read", [task["user_ids"]], {"fields": ["name"]})
            assignees = ", ".join(u["name"] for u in users) if users else "Unassigned"
            st.markdown(f"**{task['name']}** - Assigned to: {assignees} - Tags: {', '.join(tag_names) if tag_names else '-'}")
            # show subtasks
            subtasks = [t for t in tasks if t.get("parent_id") and t["parent_id"][0] == task["id"]]
            for sub in subtasks:
                st.markdown(f"  - {sub['name']}")

    if st.button("Start New Project"):
        st.session_state.clear()
        st.experimental_rerun()
