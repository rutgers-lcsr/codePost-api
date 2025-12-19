
import requests
import time
import sys
import os

API_URL = os.environ.get("API_URL", "http://localhost:8001")
USERNAME = "admin"
PASSWORD = "admin_password"

def log(msg):
    print(f"[Verify] {msg}")

def wait_for_api():
    url = f"{API_URL}/health-check"
    log(f"Waiting for API at {url}...")
    for i in range(30):
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                log("API is up!")
                return True
        except:
            pass
        time.sleep(2)
    log("API timed out")
    return False

def get_admin_session():
    session = requests.Session()
    resp = session.post(f"{API_URL}/token-auth/", json={
        "username": USERNAME,
        "password": PASSWORD
    })
    if resp.status_code != 200:
        log(f"Admin Login failed: {resp.text[:200]}")
        return None
    token = resp.json().get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session

def create_org_and_course(session):
    resp = session.post(f"{API_URL}/organizations/", json={"name": "Test Org", "shortname": "TO"})
    if resp.status_code == 201:
        org_id = resp.json()['id']
    else:
        # Maybe it exists (run reset logic ideally, but assuming fresh env)
        log("Org creation failed (might exist), trying to fetch...")
        # Since DB is wiped on fresh docker up, this shouldn't happen usually
        return None, None

    resp = session.post(f"{API_URL}/courses/", json={
        "name": "CS101", "period": "S25", "organization": org_id
    })
    if resp.status_code == 201:
        return org_id, resp.json()['id']
    return org_id, None

def verify_language_flow(session, course_id, lang_config):
    """
    lang_config = {
        "name": "Python Test",
        "lang_id": "python-3.12",
        "filename": "main.py",
        "code": "print('Hello Python')",
        "expected": "Hello Python"
    }
    """
    lang_name = lang_config['name']
    log(f"--- Starting verification for {lang_name} ---")

    # 1. Create Assignment
    resp = session.post(f"{API_URL}/assignments/", json={
        "name": f"Assignment {lang_name}",
        "course": course_id,
        "points": 100
    })
    if resp.status_code != 201:
        log(f"Create Assignment failed: {resp.text}")
        return None
    assign_id = resp.json()['id']

    # 2. Create Environment
    resp = session.post(f"{API_URL}/autograder/environments/", json={
        "assignment": assign_id,
        "language": lang_config['lang_id'],
        "requirements": "",
        "auto_detect": False
    })
    if resp.status_code not in [200, 201]:
        log(f"Create Env failed: {resp.text}")
        return None
    
    # 3. Create Student & Submission
    # Create unique student
    student_email = f"student_{lang_name.lower().replace(' ', '')}@example.com"
    resp = session.post(f"{API_URL}/users/", json={
        "username": student_email,
        "email": student_email,
        "first_name": "S",
        "last_name": "L",
        "password": "password",
        "graderCourses": [],
        "superGraderCourses": [],
        "courseadminCourses": [],
        "leaderSections": [],
        "studentCourses": [],
        "student_sections": [],
        "canCreateCourses": False,
        "canModifyRosters": False,
        "showProductTips": True,
        "api_token": None,
        "organization": None
    })
    if resp.status_code == 201:
        student_id = resp.json()['id']
        session.patch(f"{API_URL}/courses/{course_id}/addToRoster/", json={"students": [student_email]})
    else:
        log(f"Student creation failed (maybe exists): {resp.text}")
        # Proceed assuming exists?
        
    resp = session.post(f"{API_URL}/submissions/", json={"assignment": assign_id, "students": [student_email]})
    if resp.status_code != 201:
        log(f"Submission failed: {resp.text}")
        return None
    sub_id = resp.json()['id']

    # 4. Upload File
    resp = session.post(f"{API_URL}/submissionFiles/", json={
        "submission": sub_id,
        "name": lang_config['filename'],
        "extension": lang_config['filename'].split('.')[-1],
        "data": lang_config['code'],
        "mode": "r"
    })
    if resp.status_code != 201:
        log(f"Upload failed: {resp.text}")
        return None
    file_id = resp.json()['id']

    # 5. Run Autograder
    log(f"Executing {lang_name} code...")
    resp = session.post(f"{API_URL}/autograder/execute/file/", json={"file_id": file_id, "timeout": 30})
    if resp.status_code == 200:
        res = resp.json()
        if lang_config['expected'] in res.get("stdout", ""):
            log(f"SUCCESS: {lang_name} verified!")
            return sub_id
        else:
            log(f"FAILURE: {lang_name} output mismatch.")
            log(f"STDOUT: {res.get('stdout')}")
            log(f"STDERR: {res.get('stderr')}")
            log(f"Full Response: {res}")
            return None
    else:
        log(f"Execution failed: {resp.text}")
        return None

def verify_grading_flow(session, course_id, sub_id):
    log("--- Starting Grading Workflow Verification ---")
    
    # 1. Create Grader
    grader_email = "grader1@example.com"
    resp = session.post(f"{API_URL}/users/", json={
        "username": grader_email,
        "email": grader_email,
        "first_name": "G",
        "last_name": "1",
        "password": "password",
        "graderCourses": [],
        "superGraderCourses": [],
        "courseadminCourses": [],
        "leaderSections": [],
        "studentCourses": [],
        "student_sections": [],
        "canCreateCourses": False,
        "canModifyRosters": False,
        "showProductTips": True,
        "api_token": None,
        "organization": None
    })
    if resp.status_code == 201:
        grader_id = resp.json()['id']
    else:
        # assume existing
        grader_id = -1 # Look up if needed, but for now we skip lookup logic for brevity
        
    # Add to graders
    log("Adding grader to course...")
    resp = session.patch(f"{API_URL}/courses/{course_id}/addToRoster/", json={"graders": [grader_email]})
    if resp.status_code != 200:
        log(f"Add grader failed: {resp.text}")
        return False

    # Login as Grader
    grader_session = requests.Session()
    resp = grader_session.post(f"{API_URL}/token-auth/", json={"username": grader_email, "password": "password"})
    if resp.status_code != 200:
        log("Grader login failed")
        return False
    token = resp.json()['token']
    grader_session.headers.update({"Authorization": f"Bearer {token}"})

    # 2. Claim Submission
    # PATCH /submissions/{id}/ with grader
    # Although typically UI calls 'drawUnassigned', we can just set the grader field directly if allowed
    # Or cleaner: assign the grader via admin first? Let's try grader claiming it directly.
    # Actually, let's use the grader session to patch it.
    log(f"Grader claiming submission {sub_id}...")
    resp = grader_session.patch(f"{API_URL}/submissions/{sub_id}/", json={"grader": grader_id}) # grader_id might be needed from user object
    # Wait, passing "grader": <id> in patch. Need the ID.
    if grader_id == -1:
         # fetch it
         pass 

    # For simplicity, let's use the ADMIN session to assign the grader, then Grader session to grade.
    # Admin finds grader ID
    users_resp = session.get(f"{API_URL}/users/?search={grader_email}").json()
    # Handle pagination
    if isinstance(users_resp, dict) and 'results' in users_resp:
        users = users_resp['results']
    else:
        users = users_resp
        
    if not users:
        log("Could not find grader user")
        return False
    real_grader_id = users[0]['id']
    real_grader_email = users[0]['email']
    
    resp = session.patch(f"{API_URL}/submissions/{sub_id}/", json={"grader": real_grader_email})
    if resp.status_code != 200:
        log(f"Admin assigning grader failed: {resp.text}")
        return False

    # 3. Grade
    log("Grader submitting grade...")
    # Update grade and finalize
    resp = grader_session.patch(f"{API_URL}/submissions/{sub_id}/", json={
        "grade": 95.0,
        "isFinalized": True
    })
    
    if resp.status_code == 200:
        data = resp.json()
        if data['grade'] == 95.0 and data['isFinalized'] == True:
            log("SUCCESS: Submission graded and finalized!")
            return True
        else:
            log(f"FAILURE: Grade mismatch. Data: {data}")
            return False
    else:
        log(f"Grade submission failed: {resp.text}")
        return False


def run_test():
    session = get_admin_session()
    if not session: return False
    
    org_id, course_id = create_org_and_course(session)
    if not course_id: return False
    
    # Configs
    langs = [
        {
            "name": "Python",
            "lang_id": "python-3.12",
            "filename": "main.py",
            "code": "print('Hello Python')",
            "expected": "Hello Python"
        },
        {
            "name": "Java",
            "lang_id": "java",
            "filename": "HelloWorld.java",
            "code": "public class HelloWorld { public static void main(String[] args) { System.out.println('Hello Java'); } }",
            "expected": "Hello Java"
        },
        {
            "name": "C++",
            "lang_id": "c/c++",
            "filename": "main.cpp",
            "code": "#include <iostream>\nint main() { std::cout << \"Hello C++\"; return 0; }",
            "expected": "Hello C++"
        }
    ]
    
    passed_langs = []
    first_sub_id = None
    
    for cfg in langs:
        sub_id = verify_language_flow(session, course_id, cfg)
        if sub_id:
            passed_langs.append(cfg['name'])
            if not first_sub_id: first_sub_id = sub_id
        else:
            log(f"FAILED language: {cfg['name']}")
            # Continue to next language
            
    if len(passed_langs) == len(langs):
        log("All languages verified!")
    else:
        log("Some languages failed.")
        # Do not return False here, continue to grading

    # Verify Grading on the first submission (Python)
    # If python failed, first_sub_id is None. We cannot verify grading.
    if first_sub_id:
        if verify_grading_flow(session, course_id, first_sub_id):
            log("Grading workflow verified!")
        else:
            log("Grading workflow failed")
            return False # Grading essential
    else:
        log("Cannot verify grading as no submission succeeded.")
        return False
        
    return len(passed_langs) == len(langs)

if __name__ == "__main__":
    if not wait_for_api():
        sys.exit(1)
    
    if run_test():
        sys.exit(0)
    else:
        sys.exit(1)
