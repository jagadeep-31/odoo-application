import streamlit as st
import xmlrpc.client
import re
from collections import Counter
import spacy
import sys
import subprocess

# ============ SpaCy model loading with fallback =============
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

# ============ Configuration =============
ODOO_URL = "https://sba.info.solutions.pvt"  # Replace with your actual Odoo URL base (without trailing slash)
ODOO_DB = "sba_info_pvt"  # Your correct Odoo DB name
PROJECT_MANAGER = "Sadeesh"
CATEGORY_OPTIONS = ["R&D", "Client Projects", "Internal Development"]

# Map displayed names to Odoo login emails/usernames (replace with your actual users)
ASSIGNEES = {
    "Jagadeep": "jagadeep@example.com",
    "Sri Hari": "srihari@example.com",
    "Hari": "hari@example.com",
    "Ajith Kumar": "ajith.kumar@example.com",
    "Nithiyan": "nithiyan@example.com"
}

# ============ CSS for better UI styling (customize as needed) ============
st.markdown("""
<style>
/* Your preferred CSS styling here */
.streamlit-expander div[data-testid="stExpanderHeader"] {
    font-size: 1.3rem;
    font-weight: 700;
    color: #008CBA;
}
.task-card {
    background: #ffffff;
    padding: 15px;
    border-radius: 15px;
    margin-bottom: 10px;
    border-left: 7px solid #00BFFF;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    transition: box-shadow 0.3s ease;
}
.task-card:hover {
    box-shadow: 0 8px 20px rgba(0,0,0,0.2);
}
</style>
""", unsafe_allow_html=True)

# ============ Helper Functions ============

def odoo_connect():
    login = st.session_state.get("odoo_login")
    password = st.session_state.get("odoo_pass")
    if not login or not password:
        st.info("Please enter your Odoo credentials above to proceed.")
        st.stop()
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        uid = common.authenticate(ODOO_DB, login, password, {})
        if not uid:
            st.error("❌ Authentication with Odoo failed. Please check credentials.")
            st.stop()
        return uid, models
    except Exception as e:
        st.error(f"❌ Error connecting to Odoo: {e}")
        st.stop()

def get_user_id(login):
    uid, models = odoo_connect()
    pw = st.session_state.get("odoo_pass")
    user_ids = models.execute_kw(ODOO_DB, uid, pw,
                                 'res.users', 'search',
                                 [[['login', '=', login]]])
    return user_ids[0] if user_ids else None

def get_stage_id(name):
    uid, models = odoo_connect()
    pw = st.session_state.get("odoo_pass")
    stage_ids = models.execute_kw(ODOO_DB, uid, pw,
                                 'project.project', 'search',
                                 [[['name', '=', name]]])
    return stage_ids[0] if stage_ids else None

def get_or_create_tag(name, color=1):
    uid, models = odoo_connect()
    pw = st.session_state.get("odoo_pass")
    cleaned = name.strip().replace(",", "")
    tag_ids = models.execute_kw(ODOO_DB, uid, pw,
                                'project.tags', 'search',
                                [[['name', '=', cleaned]]])
    if tag_ids:
        return tag_ids[0]
    return models.execute_kw(ODOO_DB, uid, pw,
                            'project.tags', 'create',
                            [{"name": cleaned, "color": color}])

def text_to_html(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"([📋🔧✅🎯🏅])\s*<b>(.+?)</b>", r"<h4>\1 \2</h4>", text)
    text = re.sub(r"([📋🔧✅🎯🏅])\s*([A-Z ]+)", r"<h4>\1 \2</h4>", text)
    return text.replace("\n", "<br>")

def suggest_tags(text, n=5):
    doc = nlp(text.lower())
    nouns = [token.lemma_ for token in doc if token.pos_ in {'NOUN','PROPN'} and not token.is_stop]
    freq = Counter(nouns)
    tags = [k.capitalize() for k,_ in freq.most_common(n)]
    return list(dict.fromkeys(tags))

def extract_subtasks(text):
    lines = text.splitlines()
    subtasks = []
    found_section = False
    pattern = re.compile(r"\b(subgoals?|subtasks?|tasks?)\b", re.I)
    for line in lines:
        if not found_section and pattern.search(line):
            found_section = True
            continue
        if found_section:
            m = re.match(r"^\s*[-*•]\s+(.*)", line)
            if m:
                subtasks.append(m.group(1).strip())
            elif line.strip() == "" or line.startswith("#") or line.startswith(">"):
                continue
            else:
                break
    return subtasks

def create_project(name, category, desc_html):
    uid, models = odoo_connect()
    pw = st.session_state.get("odoo_pass")
    stage_id = get_stage_id(category)
    vals = {"name": name, "active": True, "description": desc_html}
    if stage_id:
        vals["stage_id"] = stage_id
    return models.execute_kw(ODOO_DB, uid, pw,
                             'project.project', 'create',
                             [vals])

def create_task(project_id, title, desc, tags, assignee_login=None, parent_id=None):
    uid, models = odoo_connect()
    pw = st.session_state.get("odoo_pass")
    tag_ids = []
    for tag in tags:
        tid = get_or_create_tag(tag)
        if tid:
            tag_ids.append(tid)
    vals = {
        "name": title,
        "project_id": project_id,
        "description": text_to_html(desc) if desc else "",
    }
    if tag_ids:
        vals["tag_ids"] = [(6, 0, tag_ids)]
    if parent_id:
        vals["parent_id"] = parent_id
    if assignee_login:
        uid_assignee = get_user_id(assignee_login)
        if uid_assignee:
            vals["user_ids"] = [(6, 0, [uid_assignee])]
        else:
            st.warning(f"Assignee '{assignee_login}' not found, task will be unassigned.")
    return models.execute_kw(ODOO_DB, uid, pw,
                             'project.task', 'create', [vals])

# ============ UI Layout ============

st.title("🚀 SBA Sprint Planning Assistant")

# Odoo credentials input
with st.expander("🛡️ Enter Odoo Credentials", expanded=True):
    st.text_input("Odoo Username (login)", key="odoo_login")
    st.text_input("Odoo Password", type="password", key="odoo_pass")

if "odoo_login" not in st.session_state or not st.session_state.odoo_login or \
   "odoo_pass" not in st.session_state or not st.session_state.odoo_pass:
    st.info("Please enter your Odoo credentials above to proceed.")
    st.stop()

# Project creation section
with st.container():
    st.markdown('<h3 class="section-header">🚀 Create New Project</h3>', unsafe_allow_html=True)
    with st.expander("Project Details", expanded=True):
        proj_name = st.text_input("Project Name", value="User Centric Project")
        proj_cat = st.selectbox("Project Category", options=CATEGORY_OPTIONS)
        proj_desc = st.text_area("Project Description (Markdown supported)", height=300, value=(
            "📋 **User Story:**\nAs a business analyst...\n\n"
            "🔧 **System Story:**\nTechnical design and implementation...\n\n"
            "✅ **Acceptance Criteria:**\nCriteria for acceptance...\n\n"
            "🎯 **Subgoals / Tasks:**\n- Task 1\n- Task 2\n"
        ))
        if st.button("Create Project"):
            html_desc = text_to_html(proj_desc)
            new_proj_id = create_project(proj_name, proj_cat, html_desc)
            st.session_state.project_id = new_proj_id
            st.session_state.project_name = proj_name
            st.success(f"Project '{proj_name}' created!")

# Task creation
if "project_id" in st.session_state:
    st.markdown(f"### Add Tasks to Project: {st.session_state.project_name}")

    with st.form("task_form"):
        task_title = st.text_input("Task Title", key="task_title_input")
        task_desc = st.text_area("Task Description (Markdown supported)", key="task_desc_input")
        suggested_tags = suggest_tags(task_desc)
        tags = st.multiselect("Tags", options=suggested_tags, default=suggested_tags, help="Select or add tags")
        manual_tag = st.text_input("Add additional tag", key="manual_tag_input")

        assignee_name = st.selectbox("Assign To:", options=list(ASSIGNEES.keys()))
        assignee_login = ASSIGNEES[assignee_name]

        # Suggested subtasks from description
        extracted_subtasks = extract_subtasks(task_desc)
        st.write("Suggested subtasks:")
        selected_subtasks = st.multiselect("Select subtasks to add:", options=extracted_subtasks, default=extracted_subtasks)

        # Manual subtasks input
        manual_subtasks_text = st.text_area("Add manual subtasks (one per line):", key="manual_subtasks_text")

        submitted = st.form_submit_button("Add Task")

    if submitted:
        full_tags = tags.copy()
        if manual_tag and manual_tag.strip() and manual_tag.strip() not in full_tags:
            full_tags.append(manual_tag.strip())
        if not task_title.strip():
            st.warning("Please enter a valid task title.")
        elif not assignee_login:
            st.warning("Please select an assignee.")
        else:
            task_id = create_task(st.session_state.project_id, task_title.strip(), task_desc.strip(), full_tags, assignee_login)
            if task_id:
                st.success(f"Task '{task_title}' added with assignee '{assignee_name}'!")
                # Add subtasks as child tasks
                count_subtasks = 0
                for stask in selected_subtasks:
                    create_task(st.session_state.project_id, stask, "", [], None, parent_id=task_id)
                    count_subtasks += 1
                manual_lines = [line.strip() for line in manual_subtasks_text.splitlines() if line.strip()]
                for mtask in manual_lines:
                    create_task(st.session_state.project_id, mtask, "", [], None, parent_id=task_id)
                    count_subtasks += 1
                if count_subtasks > 0:
                    st.success(f"Added {count_subtasks} subtasks.")
                st.experimental_rerun()

# Show existing tasks
if "project_id" in st.session_state:
    uid, models = odoo_connect()
    pw = st.session_state.odoo_pass
    try:
        all_tasks = models.execute_kw(
            ODOO_DB, uid, pw,
            "project.task", "search_read",
            [[["project_id", "=", st.session_state.project_id]]],
            {"fields": ["id", "name", "description", "tag_ids", "user_ids", "parent_id"]}
        )
    except Exception as e:
        st.error(f"Could not fetch tasks: {e}")
        all_tasks = []

    if not all_tasks:
        st.info("No tasks found yet for this project.")
    else:
        st.markdown("### Project Tasks")
        task_dict = {t["id"]: t for t in all_tasks}
        roots = [t for t in all_tasks if not t.get("parent_id")]  # Top-level tasks

        for task in roots:
            tags = []
            if task["tag_ids"]:
                try:
                    tag_objs = models.execute_kw(ODOO_DB, uid, pw, "project.tags", "read", [task["tag_ids"]], {"fields": ["name"]})
                    tags = [tag["name"] for tag in tag_objs]
                except:
                    pass
            users = []
            if task["user_ids"]:
                try:
                    user_objs = models.execute_kw(ODOO_DB, uid, pw, "res.users", "read", [task["user_ids"]], {"fields": ["name"]})
                    users = [user["name"] for user in user_objs]
                except:
                    pass
            assignees_str = ", ".join(users) if users else "Unassigned"
            tags_str = ", ".join(tags) if tags else "-"
            st.markdown(f"**{task['name']}**  \n_Assigned to:_ {assignees_str}  \n_Tags:_ {tags_str}")

            # Show subtasks indented
            children = [task_dict[cid] for cid in task_dict if task_dict[cid].get("parent_id") and task_dict[cid]["parent_id"][0] == task["id"]]
            for child in children:
                st.markdown(f" - {child['name']}")

    if st.button("Start New Project"):
        for k in list(st.session_state.keys()):
            if k not in ["odoo_login", "odoo_pass"]:
                del st.session_state[k]
        st.experimental_rerun()
