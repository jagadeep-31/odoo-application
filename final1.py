



import streamlit as st
import xmlrpc.client
import re


# CATEGORIES & ASSIGNEES (these don't change!)
PROJECT_MANAGER = "Sadeesh"
CATEGORY_OPTIONS = ["R&D", "Client Projects", "Internal Development"]
ASSIGNEES = {
    "Jagadeep": "jagadeep.k@sbainfo.in",
    "Sri Hari": "srihari.k@sbainfo.in",
    "Hari": "hari.r@sbainfo.in",
    "Ajith Kumar": "ajithkumar.r@sbainfo.in",
    "Nithiyanandham": "nithiyanandham@sbainfo.in"
}
ODOO_URL = "https://sba-info-solutions-pvt-ltd.odoo.com"
ODOO_DB = "sba-info-solutions-pvt-ltd"


# --- UI for dynamic Odoo login! ---
with st.expander("🛡️ Enter Odoo Credentials", expanded=True):
    st.text_input("Odoo Username or Email (login)", key="odoo_login")
    st.text_input("Odoo Password", type="password", key="odoo_pass")


# --- Style ---
st.markdown(""" 
<style>
.section-header {
    color: #0263e0;
    font-weight: 600;
}
.task-card {
    background: #f2f7ff;
    padding: 10px 12px;
    margin: 8px 0px;
    border-radius: 6px;
    box-shadow: 0 0 8px #d9e2ff88;
    font-family: Arial, sans-serif;
}
</style>
""", unsafe_allow_html=True)


# --- Odoo helpers ---
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
    if not login:
        return None
    uid, models = odoo_connect()
    user_ids = models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'res.users', 'search', [[['login', '=', login]]]
    )
    return user_ids[0] if user_ids else None


def get_stage_id(stage_name):
    uid, models = odoo_connect()
    stage_ids = models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'project.project.stage', 'search', [[['name', '=', stage_name]]]
    )
    return stage_ids[0] if stage_ids else None


def get_or_create_tag(tag_name, color=1):
    uid, models = odoo_connect()
    tag_clean = tag_name.replace(",", "").strip()
    tag_ids = models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'project.tags', 'search', [[['name', '=', tag_clean]]]
    )
    if tag_ids:
        return tag_ids[0]
    tag_vals = {'name': tag_clean, 'color': color}
    return models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'project.tags', 'create', [tag_vals]
    )


def text_to_html(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'([📋🔧✅🎯🏅])\s*<b>([^<]+)</b>', r'<h4>\1 \2</h4>', text)
    text = re.sub(r'([📋🔧✅🎯🏅])\s*([A-Z ]+)', r'<h4>\1 \2</h4>', text)
    return text.replace('\n', '<br>')


def create_project(name, stage, desc_html):
    uid, models = odoo_connect()
    stage_id = get_stage_id(stage)
    vals = {'name': name, 'active': True, 'description': desc_html}
    if stage_id:
        vals['stage_id'] = stage_id
    return models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'project.project', 'create', [vals]
    )


def create_task(proj_id, title, desc, tags, assignee_logins=None, parent_id=None):
    uid, models = odoo_connect()
    tag_ids = [get_or_create_tag(t) for t in tags if t]
    vals = {
        "name": title,
        "project_id": proj_id,
        "description": text_to_html(desc) if desc else "",
        "tag_ids": [(6, 0, tag_ids)] if tag_ids else []
    }
    if parent_id:
        vals["parent_id"] = parent_id
    if assignee_logins:
        user_ids = []
        for login in assignee_logins:
            uid_user = get_user_id_by_login(login)
            if uid_user:
                user_ids.append(uid_user)
            else:
                st.warning(f"Assignee '{login}' not found; task will be unassigned.")
        if user_ids:
            vals["user_ids"] = [(6, 0, user_ids)]
    return models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'project.task', 'create', [vals]
    )


def delete_task(task_id):
    uid, models = odoo_connect()
    try:
        models.execute_kw(
            ODOO_DB, uid, st.session_state["odoo_pass"],
            'project.task', 'unlink', [[task_id]]
        )
        return True
    except Exception as e:
        st.error(f'Error deleting task: {e}')
        return False


def delete_project(project_id):
    uid, models = odoo_connect()
    try:
        models.execute_kw(
            ODOO_DB, uid, st.session_state["odoo_pass"],
            'project.project', 'unlink', [[project_id]]
        )
        return True
    except Exception as e:
        st.error(f'Error deleting project: {e}')
        return False


# --- Streamlit UI ---
st.title("🚀 SBA Sprint Planning Assistant")


with st.container():
    st.markdown('<h3 class="section-header">🚀 Create a New Project</h3>', unsafe_allow_html=True)
    with st.expander("Project Details", expanded=True):
        proj_name = st.text_input("Project Name", "User centric use case")
        proj_stage = st.selectbox("Project Kanban Column", CATEGORY_OPTIONS)
        proj_desc = st.text_area(
            "Project Description (Structured content supported)",
            height=350,
            value="""📋 **USER STORY:**...
🔧 **SYSTEM STORY:**...
✅ **ACCEPTANCE CRITERIA:**...
🎯 **SUBGOALS / TASKS:**..."""
        )
        if st.button("🆕 Create Project"):
            html = text_to_html(proj_desc)
            pid = create_project(proj_name, proj_stage, html)
            st.session_state.update({
                'project_id': pid,
                'project_name': proj_name
            })
            st.success(f"✅ Project '{proj_name}' created.")


if 'project_id' in st.session_state:
    # Delete project button with confirmation checkbox
    delete_col, main_col = st.columns([0.15, 0.85])
    with delete_col:
        confirm_delete = st.checkbox("Confirm delete project", key="confirm_delete_project")
        if st.button("🗑️ Delete Project", key="del_project"):
            if confirm_delete:
                if delete_project(st.session_state['project_id']):
                    st.success(f"Project '{st.session_state['project_name']}' deleted.")
                    st.session_state.pop('project_id', None)
                    st.session_state.pop('project_name', None)
                    st.rerun()
            else:
                st.warning("Please check the confirmation box to delete the project.")
    with main_col:
        st.markdown(f'<h3 class="section-header">🗂️ Add Tasks to Project: {st.session_state["project_name"]}</h3>', unsafe_allow_html=True)
    
    st.markdown(f"**Project Manager:** {PROJECT_MANAGER}")

    with st.form("task_form"):
        title = st.text_input("Task Title")
        desc = st.text_area("Task Description (Optional)")
        tags_input = st.text_input("Tags (comma-separated)")
        tags = [t.strip() for t in tags_input.split(",") if t.strip()]
        assignees_selected = st.multiselect("Assign Task To (one or more)", list(ASSIGNEES.keys()))
        assignee_logins = [ASSIGNEES[name] for name in assignees_selected]
        additional_subtasks = st.text_area("Add Subtasks Manually (one per line)")
        submitted = st.form_submit_button("➕ Add Task")

        if submitted:
            if not title:
                st.warning("⚠️ Please enter a task title.")
            else:
                task_id = create_task(
                    st.session_state['project_id'],
                    title, desc, tags, assignee_logins
                )
                st.success(f"✅ Task '{title}' created (ID: {task_id}).")
                count = 0
                for line in additional_subtasks.splitlines():
                    sub = line.strip()
                    if sub:
                        create_task(st.session_state['project_id'], sub, "", [], None, parent_id=task_id)
                        count += 1
                if count:
                    st.success(f"🪄 {count} subtasks created.")
                st.rerun()

    st.markdown("### 📝 Current Tasks")
    uid, models = odoo_connect()
    tasks = models.execute_kw(
        ODOO_DB, uid, st.session_state["odoo_pass"],
        'project.task', 'search_read',
        [[['project_id', '=', st.session_state['project_id']]]],
        {'fields': ['id','name','tag_ids','user_ids','parent_id']}
    )
    if not tasks:
        st.info("ℹ️ No tasks yet.")
    else:
        for t in tasks:
            # Skip subtasks here, they are handled under their parent task
            if t.get('parent_id'):
                continue
            tag_objs = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"],
                                         'project.tags','read',[t['tag_ids']],{'fields':['name']}) if t['tag_ids'] else []
            tag_names = ", ".join([o['name'] for o in tag_objs]) or "-"
            user_objs = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"],
                                         'res.users','read',[t['user_ids']],{'fields':['name']}) if t['user_ids'] else []
            assignees = ", ".join([u['name'] for u in user_objs]) or "Unassigned"

            delete_col, main_col = st.columns([0.12, 0.88])
            with delete_col:
                if st.button(f"🗑️", key=f"del_{t['id']}"):
                    if delete_task(t['id']):
                        st.success(f"Task '{t['name']}' deleted.")
                        st.rerun()
            with main_col:
                st.markdown(
                    f"<div class='task-card'><strong>{t['name']}</strong><br>"
                    f"<small>Tags: {tag_names}</small><br>"
                    f"<small>Assignee(s): {assignees}</small></div>",
                    unsafe_allow_html=True
                )

            # Display subtasks with delete buttons
            for sub in [x for x in tasks if x.get('parent_id') and x['parent_id'][0] == t['id']]:
                sub_tag_objs = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"],
                                            'project.tags','read',[sub['tag_ids']],{'fields':['name']}) if sub['tag_ids'] else []
                sub_tag_names = ", ".join([o['name'] for o in sub_tag_objs]) or "-"
                sub_user_objs = models.execute_kw(ODOO_DB, uid, st.session_state["odoo_pass"],
                                            'res.users','read',[sub['user_ids']],{'fields':['name']}) if sub['user_ids'] else []
                sub_assignees = ", ".join([u['name'] for u in sub_user_objs]) or "Unassigned"

                del_col, main_sub_col = st.columns([0.12, 0.88])
                with del_col:
                    if st.button(f"🗑️", key=f"del_sub_{sub['id']}"):
                        if delete_task(sub['id']):
                            st.success(f"Subtask '{sub['name']}' deleted.")
                            st.experimental_rerun()
                with main_sub_col:
                    st.markdown(
                        f"<div class='task-card' style='margin-left:30px;background:#eaf9fd;'>"
                        f"<strong>Subtask: {sub['name']}</strong><br>"
                        f"<small>Tags: {sub_tag_names}</small><br>"
                        f"<small>Assignee(s): {sub_assignees}</small></div>",
                        unsafe_allow_html=True
                    )

    col1, col2 = st.columns([1,4])
    if col2.button("🔄 Start a New Project"):
        # Clear project info from session
        for key in ['project_id','project_name']:
            st.session_state.pop(key, None)
        st.rerun()
else:
    st.info("ℹ️ Create a project above to add tasks.")


