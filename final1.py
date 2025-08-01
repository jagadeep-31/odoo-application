import streamlit as st
import xmlrpc.client
import re
from collections import Counter
import spacy

# ========== MODEL AND CONSTANTS ==========

nlp = spacy.load("en_core_web_sm")

ODOO_URL = "https://sba-info-solutions-pvt-ltd.odoo.com"
ODOO_DB = "sba-info-solutions-pvt-ltd"
PROJECT_MANAGER = "Sadeesh"
CATEGORY_OPTIONS = ["R&D", "Client Projects", "Internal Development"]

ASSIGNEES = {
    "Jagadeep": "jagadeep.k@sbainfo.in",
    "Sri Hari": "srihari.k@sbainfo.in",
    "Hari": "hari.r@sbainfo.in",
    "Ajith Kumar": "ajith.kumar.r@sbainfo.in",
    "Nithiyanandham": "nithiyanandham@sbainfo.in"
}

# ========== CREDENTIALS IN UI ==========

with st.expander("🛡️ Enter Odoo Credentials", expanded=True):
    st.text_input("Odoo Username or Email (login)", key="odoo_login")
    st.text_input("Odoo Password", type="password", key="odoo_pass")

# ========== CSS FOR UI ==========

st.markdown("""
<style>
/* Large CSS block omitted: keep your previously used CSS or paste here */
</style>
""", unsafe_allow_html=True)

# ========== ODOO HELPERS: ALWAYS USE session_state CREDENTIALS ==========

def odoo_connect():
    login = st.session_state.get("odoo_login")
    pw = st.session_state.get("odoo_pass")
    if not login or not pw:
        st.info("Enter your Odoo login and password above to continue.")
        st.stop()
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    uid = common.authenticate(ODOO_DB, login, pw, {})
    if not uid:
        st.error("Odoo authentication failed! Please check your username and password above.")
        st.stop()
    return uid, models

def get_user_id_by_login(login):
    if not login: return None
    uid, models = odoo_connect()
    pw = st.session_state["odoo_pass"]
    user_ids = models.execute_kw(
        ODOO_DB, uid, pw, 'res.users', 'search', [[['login', '=', login]]]
    )
    return user_ids[0] if user_ids else None

def get_stage_id(stage_name):
    uid, models = odoo_connect()
    pw = st.session_state["odoo_pass"]
    stage_ids = models.execute_kw(
        ODOO_DB, uid, pw, 'project.project.stage', 'search', [[['name', '=', stage_name]]]
    )
    return stage_ids[0] if stage_ids else None

def get_or_create_tag(tag_name, color=1):
    uid, models = odoo_connect()
    pw = st.session_state["odoo_pass"]
    tag_name_cleaned = tag_name.replace(",", "").strip()
    tag_ids = models.execute_kw(
        ODOO_DB, uid, pw, 'project.tags', 'search', [[['name', '=', tag_name_cleaned]]]
    )
    if tag_ids:
        return tag_ids[0]
    tag_vals = {'name': tag_name_cleaned, 'color': color}
    tag_id = models.execute_kw(
        ODOO_DB, uid, pw, 'project.tags', 'create', [tag_vals]
    )
    return tag_id

def text_to_html(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'([📋🔧✅🎯🏅])\s*<b>([^<]+)</b>', r'<h4>\1 \2</h4>', text)
    text = re.sub(r'([📋🔧✅🎯🏅])\s*([A-Z ]+)', r'<h4>\1 \2</h4>', text)
    text = text.replace('\n', '<br>')
    return text

def suggest_tags(text, top_n=5):
    doc = nlp(text.lower())
    nouns = [token.lemma_ for token in doc if token.pos_ in ("NOUN", "PROPN") and not token.is_stop]
    counts = Counter(nouns)
    common = [word for word, _ in counts.most_common(top_n)]
    tags = list(dict.fromkeys([tag.capitalize() for tag in common if tag.strip()]))
    return tags

def create_project(project_name, category, description_html):
    uid, models = odoo_connect()
    pw = st.session_state["odoo_pass"]
    stage_id = get_stage_id(category)
    project_vals = {'name': project_name, 'active': True, 'description': description_html}
    if stage_id:
        project_vals['stage_id'] = stage_id
    project_id = models.execute_kw(
        ODOO_DB, uid, pw, 'project.project', 'create', [project_vals])
    return project_id

def create_task(project_id, task_title, task_desc, tag_names, assignee_login=None, parent_id=None):
    uid, models = odoo_connect()
    pw = st.session_state["odoo_pass"]
    tag_ids = []
    for tag in tag_names:
        if tag.strip():
            tag_id = get_or_create_tag(tag.strip())
            if tag_id:
                tag_ids.append(tag_id)
    desc_html = text_to_html(task_desc) if task_desc else ""
    task_vals = {
        "name": task_title,
        "project_id": project_id,
        "description": desc_html,
        "tag_ids": [(6, 0, tag_ids)] if tag_ids else []
    }
    if parent_id:
        task_vals["parent_id"] = parent_id
    if assignee_login:
        assignee_user_id = get_user_id_by_login(assignee_login)
        if assignee_user_id:
            task_vals['user_ids'] = [(6, 0, [assignee_user_id])]
        else:
            st.warning(f"Assignee with login '{assignee_login}' not found in Odoo! This task will be unassigned.")
    task_id = models.execute_kw(ODOO_DB, uid, pw, 'project.task', 'create', [task_vals])
    return task_id

def extract_subtasks_from_description(description):
    lines = description.splitlines()
    subtasks = []
    section_pattern = re.compile(r'\b(subgoals?|sub-tasks?|subtasks?|tasks?)\b', re.IGNORECASE)
    in_section = False
    for line in lines:
        if section_pattern.search(line):
            in_section = True
            continue
        if in_section:
            bullet_match = re.match(r'^[-*•]\s+(.*)', line)
            num_match = re.match(r'^\d+\.\s+(.*)', line)
            if bullet_match:
                subtasks.append(bullet_match.group(1).strip())
            elif num_match:
                subtasks.append(num_match.group(1).strip())
            elif line.strip() == '' or line.startswith('#') or line.startswith('>'):
                continue
            else:
                break
    return subtasks

# =================== UI ===================

st.title("🚀 SBA Sprint Planning Assistant")

with st.container():
    st.markdown('<h3 class="section-header">🚀 Create a New Project</h3>', unsafe_allow_html=True)
    with st.expander("Project Details", expanded=True):
        project_name = st.text_input("Project Name", value="User centric use case")
        project_category = st.selectbox("Project Kanban Column", CATEGORY_OPTIONS)
        project_desc = st.text_area(
            "Project Description (Structured content supported)",
            height=350,
            value="""📋 **USER STORY:**
As a Business Analyst (BA) at SBA, I want to understand how our internal automation tools can be adapted for new workflows...

🔧 **SYSTEM STORY:**
As an engineer, I need to produce a technical design...

✅ **ACCEPTANCE CRITERIA:**
A formal design document is delivered on time...

🎯 **SUBGOALS / TASKS:**
- Analyze the script...
- Research CP4BA capabilities...
""")
        if st.button("🆕 Create Project", key="create_project_btn"):
            description_html = text_to_html(project_desc)
            project_id = create_project(project_name, project_category, description_html)
            st.session_state['project_id'] = project_id
            st.session_state['project_name'] = project_name
            st.session_state['project_category'] = project_category
            st.session_state['structured_desc'] = project_desc
            st.success(f"✅ Project '{project_name}' created in '{project_category}' column.")

if 'project_id' in st.session_state:
    st.markdown(f'<h3 class="section-header">🗂️ Add Tasks to Project: {st.session_state["project_name"]}</h3>', unsafe_allow_html=True)
    st.markdown(f"**Project Manager:** {PROJECT_MANAGER}")

    with st.form("add_task_form"):
        task_title = st.text_input("Task Title", key="task_title_input")
        task_desc = st.text_area("Task Description (Optional, supports Markdown-like headings)", key="task_desc_input")
        suggested_tags = suggest_tags(task_desc)
        tags = st.multiselect("Tags for Task (suggested & editable)", options=suggested_tags, default=suggested_tags, help="Select suggested tags or type to add your own")
        manual_tag = st.text_input("Add an additional tag", key="manual_tag_input")
        selected_display_name = st.selectbox("Assign Task To (required)", list(ASSIGNEES.keys()), index=0)
        assignee_login = ASSIGNEES[selected_display_name]

        extracted_subtasks = extract_subtasks_from_description(task_desc)
        st.write("**Suggested Subtasks (select to add):**")
        selected_subtasks = st.multiselect(
            "Pick subtasks", options=extracted_subtasks, default=extracted_subtasks, key="selected_subtasks"
        )
        st.write("_Or add additional subtasks manually (one per line):_")
        manual_subtasks_text = st.text_area("Manual Subtasks", key="manual_subtasks_text")

        submitted = st.form_submit_button("➕ Add Task")
        if submitted:
            all_tags = list(tags)
            if manual_tag and manual_tag.strip() and manual_tag.strip() not in all_tags:
                all_tags.append(manual_tag.strip())
            if not task_title.strip():
                st.warning("⚠️ Please enter a task title.")
            elif not assignee_login:
                st.warning("Please select an assignee!")
            else:
                new_task_id = create_task(
                    st.session_state['project_id'],
                    task_title.strip(),
                    task_desc.strip(),
                    all_tags,
                    assignee_login
                )
                display_assignee = selected_display_name
                st.success(f"✅ Task '{task_title}' assigned to '{display_assignee}'. (Odoo Task ID: {new_task_id})")
                subtask_count = 0
                for subtask in selected_subtasks:
                    create_task(st.session_state['project_id'], subtask.strip(), "", [], None, parent_id=new_task_id)
                    subtask_count += 1
                manual_lines = [line.strip() for line in manual_subtasks_text.splitlines() if line.strip()]
                for manual_subtask in manual_lines:
                    create_task(st.session_state['project_id'], manual_subtask, "", [], None, parent_id=new_task_id)
                    subtask_count += 1
                if subtask_count:
                    st.success(f"🪄 {subtask_count} subtasks created and linked to this task.")
                st.rerun()

    st.markdown("### 📝 Current Tasks")
    uid, models = odoo_connect()
    task_objs = models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'project.task', 'search_read',
        [[['project_id', '=', st.session_state['project_id']]]],
        {'fields': ['id', 'name', 'description', 'tag_ids', 'user_ids', 'parent_id']}
    )
    if not task_objs:
        st.info("ℹ️ No tasks yet.")
    else:
        for task in task_objs:
            if task.get('parent_id'):
                continue
            tags = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"], 'project.tags', 'read', [task.get('tag_ids', [])], {'fields': ['name']}) if task.get('tag_ids') else []
            tag_names = ", ".join([tag['name'] for tag in tags]) if tags else "-"
            users = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"], 'res.users', 'read', [task.get('user_ids', [])], {'fields': ['name']}) if task.get('user_ids') else []
            assignee_names = ", ".join([user['name'] for user in users]) if users else "Unassigned"
            st.markdown(
                f"""<div class="task-card">
                    <strong style="font-size:1.15rem;">{task['name']}</strong><br>
                    <small style="color: #555;">Tags: {tag_names}</small><br>
                    <small style="color: #555;">Assignee: {assignee_names}</small>
                </div>""", unsafe_allow_html=True)
            children = [t for t in task_objs if t.get("parent_id") and t["parent_id"][0] == task["id"]]
            for sub in children:
                st.markdown(
                    f"""<div class="task-card" style="margin-left:30px;background:#eaf9fd;">
                    <strong>Subtask: {sub['name']}</strong>
                    </div>""", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 4])
    if col2.button("🔄 Start a New Project", key="reset_project_btn"):
        keys_to_delete = [
            'project_id', 'project_name', 'project_category', 'structured_desc',
            'task_title_input', 'task_desc_input', 'manual_tag_input',
            'selected_subtasks', 'manual_subtasks_text'
        ]
        for key in keys_to_delete:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
else:
    st.info("ℹ️ Create a project above to add tasks.")
