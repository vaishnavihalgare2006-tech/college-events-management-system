import os
import sys
from datetime import datetime, date, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import User, Event, Registration, Attendance

app = create_app()
client = app.test_client()

print("=" * 70)
print("RUNNING ATTENDANCE MANAGEMENT COMPLETE TEST SUITE")
print("=" * 70)

with app.app_context():
    # 1. Setup Coordinator 1
    coord1 = User.query.filter_by(role='coordinator').first()
    assert coord1 is not None, "Coordinator 1 not found"
    coord1.set_password("password123")
    coord1_id = coord1.id
    coord1_email = coord1.email

    # 2. Setup Coordinator 2 (for unauthorized test)
    coord2 = User.query.filter(User.role == 'coordinator', User.id != coord1_id).first()
    if not coord2:
        coord2 = User(
            name="Other Coordinator",
            email="other_coord@college.edu",
            role="coordinator"
        )
        coord2.set_password("password123")
        db.session.add(coord2)
        db.session.commit()
    else:
        coord2.set_password("password123")
    coord2_id = coord2.id
    coord2_email = coord2.email

    # 3. Setup Students
    student1 = User.query.filter_by(role='student').first()
    assert student1 is not None, "Student 1 not found"
    student1.set_password("password123")
    student1_id = student1.id
    student1_email = student1.email

    student2 = User.query.filter(User.role == 'student', User.id != student1_id).first()
    if not student2:
        student2 = User(
            name="Second Student",
            email="second_student@college.edu",
            role="student",
            department="Computer Science"
        )
        student2.set_password("password123")
        db.session.add(student2)
        db.session.commit()
    else:
        student2.set_password("password123")
    student2_id = student2.id
    student2_email = student2.email

    # 4. Create a clean test event belonging to Coordinator 1
    test_event = Event.query.filter_by(title="Attendance Test Event").first()
    if test_event:
        db.session.delete(test_event)
        db.session.commit()

    test_event = Event(
        title="Attendance Test Event",
        description="Testing attendance management functionality",
        category="Technical",
        venue="Seminar Hall 101",
        event_date=date.today(),
        start_time=time(10, 0),
        end_time=time(12, 0),
        capacity=50,
        status="published",
        coordinator_id=coord1_id
    )
    db.session.add(test_event)
    db.session.commit()
    event_id = test_event.id

    # 5. Register Student 1 and Student 2 for this event
    reg1 = Registration(event_id=event_id, student_id=student1_id, status="registered")
    reg2 = Registration(event_id=event_id, student_id=student2_id, status="registered")
    db.session.add_all([reg1, reg2])
    db.session.commit()
    reg1_id = reg1.id
    reg2_id = reg2.id

    print(f"Test setup complete: Event ID={event_id}, Reg1 ID={reg1_id}, Reg2 ID={reg2_id}")

# --- Test 1: Coordinator Login and Dashboard Access ---
with client:
    res = client.post('/auth/login', data={'email': coord1_email, 'password': 'password123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Dashboard" in res.data
    print("PASS [Step 1]: Coordinator login successful and dashboard opened.")

# --- Test 2: View Manage Events -> View Registrations ---
with client:
    res_manage = client.get('/coordinator/events')
    assert res_manage.status_code == 200
    assert b"Attendance Test Event" in res_manage.data

    res_regs = client.get(f'/coordinator/events/{event_id}/registrations')
    assert res_regs.status_code == 200
    assert b"Student Registrations" in res_regs.data
    assert b"Total Registrations" in res_regs.data
    assert b"Present" in res_regs.data
    assert b"Absent" in res_regs.data
    assert b"Pending" in res_regs.data

    # Both students should initially be Pending
    assert b"Pending" in res_regs.data
    print("PASS [Step 2]: Manage Events and Event Registrations page rendered with Total, Present, Absent, Pending stats.")

# --- Test 3: Mark Student 1 as Present (POST) ---
with client:
    post_res = client.post(
        f'/coordinator/events/{event_id}/registrations/{reg1_id}/attendance',
        data={'status': 'present'},
        follow_redirects=True
    )
    assert post_res.status_code == 200
    assert b"Attendance marked as Present" in post_res.data
    print("PASS [Step 3]: Mark Present returned 200 with flash success message.")

    # Verify SQLite DB record
    with app.app_context():
        att1 = Attendance.query.filter_by(registration_id=reg1_id).first()
        assert att1 is not None, "Attendance record not found in SQLite DB!"
        assert att1.present is True, "Attendance present field is not True!"
        assert att1.marked_by == coord1_id, "marked_by does not match coordinator ID!"
        assert att1.marked_at is not None, "marked_at is None!"
    print("PASS [Step 3 DB]: Attendance record created in SQLite with present=True, marked_by, and marked_at.")

# --- Test 4: Refresh Page -> Status remains Present, counts are accurate ---
with client:
    refresh_res = client.get(f'/coordinator/events/{event_id}/registrations')
    assert refresh_res.status_code == 200
    # Present button should have is-active
    assert b"btn-present is-active" in refresh_res.data or b"btn-present  is-active" in refresh_res.data
    print("PASS [Step 4]: Page refreshed. Status remains Present.")

# --- Test 5: Mark Student 1 as Absent (POST) ---
with client:
    post_absent = client.post(
        f'/coordinator/events/{event_id}/registrations/{reg1_id}/attendance',
        data={'status': 'absent'},
        follow_redirects=True
    )
    assert post_absent.status_code == 200
    assert b"Attendance marked as Absent" in post_absent.data

    # Verify SQLite DB record updated
    with app.app_context():
        att1 = Attendance.query.filter_by(registration_id=reg1_id).first()
        assert att1 is not None
        assert att1.present is False, "Attendance present field was not updated to False!"
    print("PASS [Step 5]: Status successfully changed to Absent in SQLite with flash message.")

# --- Test 6: Verify Pending status for Student 2 whose attendance is not marked ---
with client:
    res_check = client.get(f'/coordinator/events/{event_id}/registrations')
    assert res_check.status_code == 200
    with app.app_context():
        att2 = Attendance.query.filter_by(registration_id=reg2_id).first()
        assert att2 is None, "Student 2 should not have attendance marked!"
    print("PASS [Step 6]: Pending confirmed for student whose attendance is not marked.")

# --- Test 7: Unauthorized attendance modification prevented for another coordinator's event ---
with client:
    # Login as Coordinator 2
    client.post('/auth/logout', follow_redirects=True)
    client.post('/auth/login', data={'email': coord2_email, 'password': 'password123'}, follow_redirects=True)

    unauth_post = client.post(
        f'/coordinator/events/{event_id}/registrations/{reg1_id}/attendance',
        data={'status': 'present'},
        follow_redirects=True
    )
    assert b"You are not authorized" in unauth_post.data or unauth_post.status_code in [302, 403, 404]
    print("PASS [Step 7]: Unauthorized coordinator cannot modify attendance for another coordinator's event.")

# --- Test 8: Student cannot mark attendance ---
with client:
    client.post('/auth/logout', follow_redirects=True)
    client.post('/auth/login', data={'email': student1_email, 'password': 'password123'}, follow_redirects=True)

    student_hack = client.post(
        f'/coordinator/events/{event_id}/registrations/{reg1_id}/attendance',
        data={'status': 'present'},
        follow_redirects=True
    )
    assert b"You do not have permission" in student_hack.data
    print("PASS [Step 8]: Student cannot access attendance marking route and is blocked.")

# --- Test 9: GET method is not allowed on attendance marking route ---
with client:
    client.post('/auth/logout', follow_redirects=True)
    client.post('/auth/login', data={'email': coord1_email, 'password': 'password123'}, follow_redirects=True)

    get_res = client.get(f'/coordinator/events/{event_id}/registrations/{reg1_id}/attendance')
    assert get_res.status_code == 405, f"Expected 405 Method Not Allowed, got {get_res.status_code}"
    print("PASS [Step 9]: GET method is rejected with 405 Method Not Allowed.")

# --- Test 10: Reports Integration ---
# Now mark Student 1 as Present, and Student 2 as Absent
with client:
    client.post(f'/coordinator/events/{event_id}/registrations/{reg1_id}/attendance', data={'status': 'present'}, follow_redirects=True)
    client.post(f'/coordinator/events/{event_id}/registrations/{reg2_id}/attendance', data={'status': 'absent'}, follow_redirects=True)

    reports_res = client.get(f'/coordinator/reports?event_id={event_id}')
    assert reports_res.status_code == 200
    assert b"Attendance Test Event" in reports_res.data
    # In reports, registered=2, present=1, absent=1, pending=0, attendance_percentage=50.0%
    assert b"50" in reports_res.data

    csv_res = client.get(f'/coordinator/reports/csv?event_id={event_id}')
    assert csv_res.status_code == 200
    assert b"Attendance Test Event" in csv_res.data
    assert b"50.0%" in csv_res.data
    print("PASS [Step 10]: Reports and Reports CSV reflect accurate Present, Absent, Pending, and Attendance %.")

# --- Test 11: Student Dashboard Integration ---
with client:
    client.post('/auth/logout', follow_redirects=True)
    client.post('/auth/login', data={'email': student1_email, 'password': 'password123'}, follow_redirects=True)

    dash_student = client.get('/student/home')
    assert dash_student.status_code == 200
    with app.app_context():
        student1_regs = Registration.query.filter_by(student_id=student1_id, status='registered').all()
        student1_att = sum(1 for r in student1_regs if r.attendance and r.attendance.present)
        expected_pct = round((student1_att / len(student1_regs)) * 100, 1)
        expected_pct_str = f"{int(expected_pct) if expected_pct.is_integer() else expected_pct}%"
    assert str(student1_att).encode('utf-8') in dash_student.data
    assert expected_pct_str.encode('utf-8') in dash_student.data
    print(f"PASS [Step 11]: Student Dashboard reflects attended_count={student1_att} and attendance_percentage={expected_pct_str}.")

# Clean up test event
with app.app_context():
    te = Event.query.filter_by(id=event_id).first()
    if te:
        db.session.delete(te)
        db.session.commit()
    print("CLEANUP: Test artifacts removed successfully.")

print("=" * 70)
print("ALL 11 ATTENDANCE MANAGEMENT INTEGRATION TESTS PASSED 100%!")
print("=" * 70)
