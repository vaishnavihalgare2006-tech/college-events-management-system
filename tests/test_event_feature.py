import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import User, Event, Registration

app = create_app()
client = app.test_client()

with app.app_context():
    student = User.query.filter_by(role='student').first()
    assert student is not None, "No student found"
    student.set_password('password123')
    student_id = student.id
    student_email = student.email
    Registration.query.filter_by(student_id=student_id, event_id=1).delete()
    db.session.commit()

with client:
    # 1. Login student
    login_res = client.post('/auth/login', data={'email': student_email, 'password': 'password123'}, follow_redirects=True)
    print("Login status:", login_res.status_code)

    # 2. Test /student/events works
    res_events = client.get('/student/events')
    print("GET /student/events status:", res_events.status_code)
    assert res_events.status_code == 200, f"Expected 200, got {res_events.status_code}"
    assert b"Discover Events" in res_events.data
    assert b"Tech Symposium 2026" in res_events.data
    print("PASS: /student/events works and displays published events")

    # 3. Test GET /student/events/1
    res_detail = client.get('/student/events/1')
    print("GET /student/events/1 status:", res_detail.status_code)
    assert res_detail.status_code == 200, f"Expected 200, got {res_detail.status_code}"
    assert b"Tech Symposium 2026" in res_detail.data
    assert b"Register for Event" in res_detail.data
    assert b"Prof. Coordinator" in res_detail.data
    print("PASS: GET /student/events/1 displays event details, coordinator, and register button")

    # 4. Test POST /student/events/1/register
    res_reg = client.post('/student/events/1/register', follow_redirects=False)
    print("POST /student/events/1/register status:", res_reg.status_code, "Redirect Location:", res_reg.headers.get("Location"))
    assert res_reg.status_code == 302
    assert "/student/events/1" in res_reg.headers.get("Location")

    with app.app_context():
        db_reg = Registration.query.filter_by(student_id=student_id, event_id=1).first()
        assert db_reg is not None, "Registration record was not created in database!"
        assert db_reg.status == "registered"
    print("PASS: Registration record created in database with status=registered")

    # 5. Test GET /student/events/1 after registration
    res_detail_after = client.get('/student/events/1')
    assert res_detail_after.status_code == 200
    assert b"You are registered" in res_detail_after.data
    print("PASS: Event details correctly shows registered state (You are registered)")

    # 6. Test duplicate registration prevention
    res_dup = client.post('/student/events/1/register', follow_redirects=True)
    assert b"already registered" in res_dup.data
    print("PASS: Duplicate registration blocked with warning message")

    # 7. Test full event registration prevention
    res_full_detail = client.get('/student/events/2')
    assert res_full_detail.status_code == 200
    assert b"Event is full" in res_full_detail.data
    print("PASS: Full event displays 'Event is full'")

    res_full_post = client.post('/student/events/2/register', follow_redirects=True)
    assert b"full capacity" in res_full_post.data
    print("PASS: Full event registration blocked with danger message")

    # 8. Test unpublished / draft event returns 404
    res_draft = client.get('/student/events/3')
    assert res_draft.status_code == 404
    res_draft_post = client.post('/student/events/3/register')
    assert res_draft_post.status_code == 404
    print("PASS: Draft event returns 404 for GET and POST")

    # 9. Test invalid event ID returns 404
    res_invalid = client.get('/student/events/9999')
    assert res_invalid.status_code == 404
    res_invalid_post = client.post('/student/events/9999/register')
    assert res_invalid_post.status_code == 404
    print("PASS: Invalid event ID returns 404 for GET and POST")

print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
