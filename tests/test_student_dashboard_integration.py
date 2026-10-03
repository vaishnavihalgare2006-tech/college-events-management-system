import os
import sys
from datetime import date, time, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import User, Event, Registration, Attendance

app = create_app()
client = app.test_client()

print("=" * 60)
print("RUNNING STUDENT DASHBOARD INTEGRATION TEST SUITE")
print("=" * 60)

with app.app_context():
    # Setup test coordinator and student
    coord = User.query.filter_by(role='coordinator').first()
    assert coord is not None, "Coordinator not found in DB"
    coord_id = coord.id
    
    student = User.query.filter_by(role='student').first()
    assert student is not None, "Student not found in DB"
    student_id = student.id
    student_name = student.name
    student_email = student.email
    student.set_password("password123")
    
    # Clean previous test artifacts if any
    test_events = Event.query.filter(Event.title.like("Integration Test Event%")).all()
    for te in test_events:
        db.session.delete(te)
    db.session.commit()

# --- Flow A: Login as student -> Student Dashboard opens -> Student name comes from DB ---
with client:
    login_res = client.post('/auth/login', data={'email': student_email, 'password': 'password123'}, follow_redirects=True)
    assert login_res.status_code == 200
    assert student_name.encode('utf-8') in login_res.data or student_name.split()[0].encode('utf-8') in login_res.data
    
    dash_res = client.get('/student/home')
    assert dash_res.status_code == 200
    assert student_name.encode('utf-8') in dash_res.data
    print("PASS [Flow A]: Login as student -> Dashboard opens -> Student name rendered from DB")

    # Read initial registered count
    with app.app_context():
        initial_reg_count = Registration.query.filter_by(student_id=student_id, status='registered').count()

# --- Flow B: Create/publish an event as coordinator -> Event appears in Student Events ---
with app.app_context():
    tomorrow = date.today() + timedelta(days=2)
    new_event = Event(
        title="Integration Test Event Alfa",
        description="A great integration test event",
        category="Workshops",
        venue="Auditorium Hall B",
        event_date=tomorrow,
        start_time=time(10, 0),
        end_time=time(12, 0),
        capacity=2,
        status="published",
        coordinator_id=coord_id
    )
    db.session.add(new_event)
    db.session.commit()
    event_alfa_id = new_event.id

with client:
    res_events = client.get('/student/events')
    assert res_events.status_code == 200
    assert b"Integration Test Event Alfa" in res_events.data
    print("PASS [Flow B]: Published coordinator event appears in Student Events discovery")

# --- Flow C & D: Student registers for event -> SQLite record -> Dashboard count and upcoming event update ---
with client:
    # Register for Alfa
    reg_post = client.post(f'/student/events/{event_alfa_id}/register', follow_redirects=True)
    assert reg_post.status_code == 200
    assert b"Registration successful" in reg_post.data or b"You are registered" in reg_post.data
    
    with app.app_context():
        db_reg = Registration.query.filter_by(student_id=student_id, event_id=event_alfa_id, status='registered').first()
        assert db_reg is not None, "Registration record not found in database!"
        reg_id = db_reg.id
    print("PASS [Flow C]: Student registers for event -> Registration inserted into SQLite")

    # Check dashboard again
    dash_after = client.get('/student/home')
    assert dash_after.status_code == 200
    assert b"Integration Test Event Alfa" in dash_after.data
    
    with app.app_context():
        new_reg_count = Registration.query.filter_by(student_id=student_id, status='registered').count()
        assert new_reg_count == initial_reg_count + 1
    
    assert str(new_reg_count).encode('utf-8') in dash_after.data
    print("PASS [Flow D]: Dashboard shows upcoming event and updated registered count")

# --- Flow E: Coordinator marks attendance -> Student dashboard attendance count and % update ---
with app.app_context():
    # Mark attendance
    att = Attendance(
        registration_id=reg_id,
        present=True,
        marked_by=coord_id
    )
    db.session.add(att)
    db.session.commit()

with client:
    dash_att = client.get('/student/home')
    assert dash_att.status_code == 200
    with app.app_context():
        active_regs = Registration.query.filter_by(student_id=student_id, status='registered').all()
        att_count = sum(1 for r in active_regs if r.attendance and r.attendance.present)
        pct = round((att_count / len(active_regs)) * 100, 1)
        expected_pct_str = f"{int(pct) if pct.is_integer() else pct}%".encode('utf-8')
    assert str(att_count).encode('utf-8') in dash_att.data
    assert expected_pct_str in dash_att.data
    print(f"PASS [Flow E]: Coordinator marked attendance -> Student dashboard shows attended={att_count} and {expected_pct_str.decode('utf-8')}")

# --- Flow F: Search/filter events -> Results come from database ---
with client:
    search_res = client.get('/student/events?search=Alfa')
    assert search_res.status_code == 200
    assert b"Integration Test Event Alfa" in search_res.data

    no_match_res = client.get('/student/events?search=NonExistentEventXYZ')
    assert no_match_res.status_code == 200
    assert b"No events found" in no_match_res.data

    cat_res = client.get('/student/events?category=Workshops')
    assert cat_res.status_code == 200
    assert b"Integration Test Event Alfa" in cat_res.data
    print("PASS [Flow F]: Search and category filtering query database correctly")

# --- Flow G: Duplicate registration prevented ---
with client:
    dup_res = client.post(f'/student/events/{event_alfa_id}/register', follow_redirects=True)
    assert b"already registered" in dup_res.data
    with app.app_context():
        count_for_event = Registration.query.filter_by(student_id=student_id, event_id=event_alfa_id).count()
        assert count_for_event == 1, "Duplicate registration was created!"
    print("PASS [Flow G]: Duplicate registration for same student and event blocked")

# --- Flow H: Full event registration prevented ---
with app.app_context():
    # Capacity is 2. Let's register another student to fill it.
    other_student = User.query.filter(User.role == 'student', User.id != student_id).first()
    if not other_student:
        other_student = User(name="Other Student", email="other@student.edu", role="student")
        other_student.set_password("pass123")
        db.session.add(other_student)
        db.session.commit()
    
    other_reg = Registration(student_id=other_student.id, event_id=event_alfa_id, status='registered')
    db.session.add(other_reg)
    db.session.commit()
    
    # Create third student who tries to register
    third_student = User.query.filter(User.email == "third@student.edu").first()
    if not third_student:
        third_student = User(name="Third Student", email="third@student.edu", role="student")
        third_student.set_password("pass123")
        db.session.add(third_student)
        db.session.commit()
    third_id = third_student.id
    third_email = third_student.email

with client:
    # Login as third student
    client.post('/auth/login', data={'email': third_email, 'password': 'pass123'}, follow_redirects=True)
    full_detail = client.get(f'/student/events/{event_alfa_id}')
    assert b"Event is full" in full_detail.data
    
    full_post = client.post(f'/student/events/{event_alfa_id}/register', follow_redirects=True)
    assert b"full capacity" in full_post.data
    with app.app_context():
        third_reg = Registration.query.filter_by(student_id=third_id, event_id=event_alfa_id).first()
        assert third_reg is None, "Registration was allowed for full event!"
    print("PASS [Flow H]: Registration blocked when capacity is full")

# Cleanup
with app.app_context():
    test_events = Event.query.filter(Event.title.like("Integration Test Event%")).all()
    for te in test_events:
        db.session.delete(te)
    db.session.commit()
    print("CLEANUP COMPLETED")

print("\n>>> ALL 8 VERIFICATION FLOWS (A - H) PASSED 100% SUCCESSFULLY! <<<")
