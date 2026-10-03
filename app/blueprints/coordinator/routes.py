from datetime import datetime

from functools import wraps

import csv
import io

from flask import Response

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
)

from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Attendance, Event, Registration


coordinator_bp = Blueprint(
    "coordinator",
    __name__,
    url_prefix="/coordinator"
)


def coordinator_required(view_function):

    @wraps(view_function)
    @login_required
    def wrapped_view(*args, **kwargs):

        if current_user.role not in [
            "coordinator",
            "admin"
        ]:

            flash(
                "You do not have permission to access the college dashboard.",
                "danger"
            )

            return redirect(
                url_for("student.home")
            )

        return view_function(*args, **kwargs)

    return wrapped_view


# =========================================================
# COORDINATOR DASHBOARD
# =========================================================

@coordinator_bp.route("/dashboard")
@coordinator_required
def dashboard():

    total_events = Event.query.filter_by(
        coordinator_id=current_user.id
    ).count()


    published_events = Event.query.filter_by(
        coordinator_id=current_user.id,
        status="published"
    ).count()


    draft_events = Event.query.filter_by(
        coordinator_id=current_user.id,
        status="draft"
    ).count()


    total_registrations = (
        Registration.query
        .join(
            Event,
            Registration.event_id == Event.id
        )
        .filter(
            Event.coordinator_id == current_user.id,
            Registration.status == "registered"
        )
        .count()
    )


    recent_events = (
        Event.query
        .filter_by(
            coordinator_id=current_user.id
        )
        .order_by(
            Event.event_date.desc(),
            Event.start_time.desc()
        )
        .limit(5)
        .all()
    )


    return render_template(
        "coordinator/dashboard.html",

        user=current_user,

        total_events=total_events,

        published_events=published_events,

        draft_events=draft_events,

        total_registrations=total_registrations,

        recent_events=recent_events
    )


@coordinator_bp.route("/registrations")
@coordinator_required
def registrations():

    if current_user.role == "admin":
        events = (
            Event.query
            .order_by(
                Event.event_date.asc(),
                Event.start_time.asc()
            )
            .all()
        )
    else:
        events = (
            Event.query
            .filter_by(
                coordinator_id=current_user.id
            )
            .order_by(
                Event.event_date.asc(),
                Event.start_time.asc()
            )
            .all()
        )

    event_ids = [event.id for event in events]

    registrations_by_event = {}

    if event_ids:
        registrations = (
            Registration.query
            .options(
                joinedload(Registration.attendance),
                joinedload(Registration.student)
            )
            .filter(
                Registration.event_id.in_(event_ids),
                Registration.status == "registered"
            )
            .order_by(
                Registration.registered_at.desc()
            )
            .all()
        )

        for registration in registrations:
            registrations_by_event.setdefault(
                registration.event_id,
                []
            ).append(registration)

    event_registration_groups = [
        {
            "event": event,
            "registrations": registrations_by_event.get(event.id, [])
        }
        for event in events
    ]

    all_registrations = [
        reg
        for group in event_registration_groups
        for reg in group["registrations"]
    ]

    total_registrations = len(all_registrations)

    present_count = sum(
        1
        for reg in all_registrations
        if reg.attendance
        and reg.attendance.present
    )

    absent_count = sum(
        1
        for reg in all_registrations
        if reg.attendance
        and not reg.attendance.present
    )

    pending_count = (
        total_registrations - present_count - absent_count
    )

    return render_template(
        "coordinator/registrations.html",
        user=current_user,
        event_registration_groups=event_registration_groups,
        total_events=len(events),
        total_registrations=total_registrations,
        present_count=present_count,
        absent_count=absent_count,
        pending_count=pending_count
    )


@coordinator_bp.route("/registrations/<int:event_id>/csv")
@coordinator_required
def registrations_csv(event_id):

    event = Event.query.filter_by(
        id=event_id,
        coordinator_id=current_user.id
    ).first_or_404()

    registrations = (
        Registration.query
        .filter(
            Registration.event_id == event.id,
            Registration.status == "registered"
        )
        .order_by(
            Registration.registered_at.asc()
        )
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Student Name",
        "Email",
        "Department",
        "Registered At",
        "Attendance"
    ])

    for registration in registrations:
        if registration.attendance is None:
            attendance = "Pending"
        elif registration.attendance.present:
            attendance = "Present"
        else:
            attendance = "Absent"

        writer.writerow([
            registration.student.name,
            registration.student.email,
            registration.student.department or "Not provided",
            registration.registered_at.strftime("%d %b %Y, %I:%M %p"),
            attendance
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                f"attachment; filename=event_{event.id}_registrations.csv"
            )
        }
    )


def _get_report_events():

    selected_event_id = request.args.get(
        "event_id",
        ""
    ).strip()

    try:
        selected_event_id = int(selected_event_id) if selected_event_id else None
    except ValueError:
        selected_event_id = None

    selected_category = request.args.get(
        "category",
        ""
    ).strip()

    events_query = Event.query.filter_by(
        coordinator_id=current_user.id
    )

    if selected_event_id is not None:
        events_query = events_query.filter(
            Event.id == selected_event_id
        )

    if selected_category:
        events_query = events_query.filter(
            Event.category == selected_category
        )

    events = (
        events_query
        .order_by(
            Event.event_date.asc(),
            Event.start_time.asc()
        )
        .all()
    )

    categories = [
        category
        for category, in (
            Event.query
            .filter(
                Event.coordinator_id == current_user.id,
                Event.category.isnot(None)
            )
            .with_entities(Event.category)
            .distinct()
            .order_by(Event.category.asc())
            .all()
        )
        if category
    ]

    return events, categories, selected_event_id, selected_category


def _build_event_reports(events):

    event_ids = [event.id for event in events]
    registrations_by_event = {}

    if event_ids:
        registrations = (
            Registration.query
            .options(
                joinedload(Registration.attendance),
                joinedload(Registration.student)
            )
            .filter(
                Registration.event_id.in_(event_ids),
                Registration.status == "registered"
            )
            .all()
        )

        for registration in registrations:
            registrations_by_event.setdefault(
                registration.event_id,
                []
            ).append(registration)

    event_reports = []

    for event in events:
        registrations = registrations_by_event.get(event.id, [])
        present = sum(
            1
            for registration in registrations
            if registration.attendance
            and registration.attendance.present
        )
        absent = sum(
            1
            for registration in registrations
            if registration.attendance
            and not registration.attendance.present
        )
        pending = len(registrations) - present - absent
        registered = len(registrations)
        attendance_percentage = (
            round((present / registered) * 100, 1)
            if registered
            else 0
        )

        event_reports.append({
            "event": event,
            "registered": registered,
            "present": present,
            "absent": absent,
            "pending": pending,
            "attendance_percentage": attendance_percentage,
            "available_seats": max(0, event.capacity - registered)
        })

    return event_reports


@coordinator_bp.route("/reports")
@coordinator_required
def reports():

    (
        events,
        categories,
        selected_event_id,
        selected_category
    ) = _get_report_events()

    event_reports = _build_event_reports(events)
    total_registrations = sum(
        report["registered"]
        for report in event_reports
    )
    total_attended = sum(
        report["present"]
        for report in event_reports
    )
    overall_attendance = (
        round((total_attended / total_registrations) * 100, 1)
        if total_registrations
        else 0
    )
    total_capacity = sum(
        report["event"].capacity
        for report in event_reports
    )
    total_available_seats = sum(
        report["available_seats"]
        for report in event_reports
    )

    return render_template(
        "coordinator/reports.html",
        user=current_user,
        event_reports=event_reports,
        categories=categories,
        selected_event_id=selected_event_id,
        selected_category=selected_category,
        total_events=len(event_reports),
        total_registrations=total_registrations,
        total_attended=total_attended,
        overall_attendance=overall_attendance,
        total_capacity=total_capacity,
        total_available_seats=total_available_seats
    )


@coordinator_bp.route("/reports/csv")
@coordinator_required
def reports_csv():

    events, _, _, _ = _get_report_events()
    event_reports = _build_event_reports(events)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Event Name",
        "Category",
        "Date",
        "Venue",
        "Capacity",
        "Registrations",
        "Present",
        "Absent",
        "Pending",
        "Attendance %"
    ])

    for report in event_reports:
        event = report["event"]
        writer.writerow([
            event.title,
            event.category,
            event.event_date.strftime("%d %b %Y"),
            event.venue,
            event.capacity,
            report["registered"],
            report["present"],
            report["absent"],
            report["pending"],
            f"{report['attendance_percentage']}%"
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=event_reports.csv"
        }
    )


# =========================================================
# CREATE EVENT
# =========================================================

@coordinator_bp.route(
    "/events/create",
    methods=["GET", "POST"]
)
@coordinator_required
def create_event():


    if request.method == "POST":


        # -------------------------------------------------
        # BASIC INFORMATION
        # -------------------------------------------------

        title = request.form.get(
            "title",
            ""
        ).strip()


        description = request.form.get(
            "description",
            ""
        ).strip()


        category = request.form.get(
            "category",
            ""
        ).strip()


        venue = request.form.get(
            "venue",
            ""
        ).strip()


        event_date = request.form.get(
            "event_date",
            ""
        ).strip()


        capacity = request.form.get(
            "capacity",
            ""
        ).strip()


        status = request.form.get(
            "status",
            "draft"
        ).strip()


        # -------------------------------------------------
        # START TIME
        # -------------------------------------------------

        start_hour = request.form.get(
            "start_hour",
            ""
        ).strip()


        start_minute = request.form.get(
            "start_minute",
            ""
        ).strip()


        start_period = request.form.get(
            "start_period",
            ""
        ).strip()


        # -------------------------------------------------
        # END TIME
        # -------------------------------------------------

        end_hour = request.form.get(
            "end_hour",
            ""
        ).strip()


        end_minute = request.form.get(
            "end_minute",
            ""
        ).strip()


        end_period = request.form.get(
            "end_period",
            ""
        ).strip()


        # -------------------------------------------------
        # REQUIRED FIELD VALIDATION
        # -------------------------------------------------

        if not title:

            flash(
                "Event title is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        if not category:

            flash(
                "Event category is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        if not venue:

            flash(
                "Event venue is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        if not event_date:

            flash(
                "Event date is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        if not capacity:

            flash(
                "Event capacity is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # TIME REQUIRED VALIDATION
        # -------------------------------------------------

        if not (
            start_hour
            and start_minute
            and start_period
        ):

            flash(
                "Complete start time is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        if not (
            end_hour
            and end_minute
            and end_period
        ):

            flash(
                "Complete end time is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # VALIDATE AM / PM
        # -------------------------------------------------

        if start_period not in [
            "AM",
            "PM"
        ]:

            flash(
                "Invalid start time period.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        if end_period not in [
            "AM",
            "PM"
        ]:

            flash(
                "Invalid end time period.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # DATE CONVERSION
        # -------------------------------------------------

        try:

            parsed_date = datetime.strptime(
                event_date,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            flash(
                "Invalid event date.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # TIME CONVERSION
        # -------------------------------------------------

        try:

            start_time_string = (
                f"{start_hour}:"
                f"{start_minute} "
                f"{start_period}"
            )


            end_time_string = (
                f"{end_hour}:"
                f"{end_minute} "
                f"{end_period}"
            )


            parsed_start_time = datetime.strptime(
                start_time_string,
                "%I:%M %p"
            ).time()


            parsed_end_time = datetime.strptime(
                end_time_string,
                "%I:%M %p"
            ).time()


        except ValueError:

            flash(
                "Invalid time selected.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # END TIME MUST BE AFTER START TIME
        # -------------------------------------------------

        if parsed_end_time <= parsed_start_time:

            flash(
                "End time must be later than start time.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # CAPACITY CONVERSION
        # -------------------------------------------------

        try:

            parsed_capacity = int(
                capacity
            )

        except ValueError:

            flash(
                "Capacity must be a valid number.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        if parsed_capacity <= 0:

            flash(
                "Capacity must be greater than 0.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # STATUS VALIDATION
        # -------------------------------------------------

        if status not in [
            "draft",
            "published"
        ]:

            status = "draft"


        # -------------------------------------------------
        # CREATE EVENT OBJECT
        # -------------------------------------------------

        event = Event(

            title=title,

            description=(
                description
                if description
                else None
            ),

            category=category,

            venue=venue,

            event_date=parsed_date,

            start_time=parsed_start_time,

            end_time=parsed_end_time,

            capacity=parsed_capacity,

            status=status,

            coordinator_id=current_user.id

        )


        # -------------------------------------------------
        # SAVE TO SQLITE DATABASE
        # -------------------------------------------------

        try:

            db.session.add(event)

            db.session.commit()


        except Exception:

            db.session.rollback()

            flash(
                "Unable to create event. Please try again.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.create_event"
                )
            )


        # -------------------------------------------------
        # SUCCESS
        # -------------------------------------------------

        flash(
            "Event created successfully.",
            "success"
        )


        return redirect(
            url_for(
                "coordinator.dashboard"
            )
        )


    # -----------------------------------------------------
    # GET REQUEST
    # -----------------------------------------------------

    return render_template(
        "coordinator/create_event.html",
        user=current_user
    )
# =========================================================
# MANAGE EVENTS
# =========================================================

@coordinator_bp.route("/events")
@coordinator_required
def manage_events():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()


    # -----------------------------------------------------
    # BASE QUERY
    # -----------------------------------------------------

    query = Event.query.filter_by(
        coordinator_id=current_user.id
    )


    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if search:

        query = query.filter(
            Event.title.ilike(
                f"%{search}%"
            )
        )


    # -----------------------------------------------------
    # CATEGORY FILTER
    # -----------------------------------------------------

    if category:

        query = query.filter(
            Event.category == category
        )


    # -----------------------------------------------------
    # STATUS FILTER
    # -----------------------------------------------------

    if status in [
        "draft",
        "published"
    ]:

        query = query.filter(
            Event.status == status
        )


    # -----------------------------------------------------
    # GET EVENTS
    # -----------------------------------------------------

    events = (
        query
        .order_by(
            Event.event_date.asc(),
            Event.start_time.asc()
        )
        .all()
    )


    # -----------------------------------------------------
    # CATEGORY LIST
    # -----------------------------------------------------

    category_rows = (
        Event.query
        .filter_by(
            coordinator_id=current_user.id
        )
        .with_entities(
            Event.category
        )
        .distinct()
        .order_by(
            Event.category.asc()
        )
        .all()
    )


    categories = [
        row[0]
        for row in category_rows
        if row[0]
    ]


    return render_template(
        "coordinator/manage_events.html",

        user=current_user,

        events=events,

        categories=categories,

        search=search,

        selected_category=category,

        selected_status=status
    )


# =========================================================
# EDIT EVENT
# =========================================================

@coordinator_bp.route(
    "/events/<int:event_id>/edit",
    methods=["GET", "POST"]
)
@coordinator_required
def edit_event(event_id):

    event = Event.query.filter_by(
        id=event_id,
        coordinator_id=current_user.id
    ).first_or_404()


    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        venue = request.form.get(
            "venue",
            ""
        ).strip()

        event_date = request.form.get(
            "event_date",
            ""
        ).strip()

        capacity = request.form.get(
            "capacity",
            ""
        ).strip()

        start_hour = request.form.get(
            "start_hour",
            ""
        ).strip()

        start_minute = request.form.get(
            "start_minute",
            ""
        ).strip()

        start_period = request.form.get(
            "start_period",
            ""
        ).strip()

        end_hour = request.form.get(
            "end_hour",
            ""
        ).strip()

        end_minute = request.form.get(
            "end_minute",
            ""
        ).strip()

        end_period = request.form.get(
            "end_period",
            ""
        ).strip()

        status = request.form.get(
            "status",
            "draft"
        ).strip()


        # -------------------------------------------------
        # REQUIRED VALIDATION
        # -------------------------------------------------

        if not title:

            flash(
                "Event title is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if not category:

            flash(
                "Event category is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if not venue:

            flash(
                "Event venue is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if not event_date:

            flash(
                "Event date is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if not capacity:

            flash(
                "Event capacity is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if not (
            start_hour
            and start_minute
            and start_period
        ):

            flash(
                "Complete start time is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if not (
            end_hour
            and end_minute
            and end_period
        ):

            flash(
                "Complete end time is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        # -------------------------------------------------
        # DATE
        # -------------------------------------------------

        try:

            parsed_date = datetime.strptime(
                event_date,
                "%Y-%m-%d"
            ).date()

        except ValueError:

            flash(
                "Invalid event date.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        # -------------------------------------------------
        # TIME
        # -------------------------------------------------

        try:

            start_time_string = (
                f"{start_hour}:"
                f"{start_minute} "
                f"{start_period}"
            )

            end_time_string = (
                f"{end_hour}:"
                f"{end_minute} "
                f"{end_period}"
            )

            parsed_start_time = datetime.strptime(
                start_time_string,
                "%I:%M %p"
            ).time()

            parsed_end_time = datetime.strptime(
                end_time_string,
                "%I:%M %p"
            ).time()

        except ValueError:

            flash(
                "Invalid time selected.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if parsed_end_time <= parsed_start_time:

            flash(
                "End time must be later than start time.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        # -------------------------------------------------
        # CAPACITY
        # -------------------------------------------------

        try:

            parsed_capacity = int(
                capacity
            )

        except ValueError:

            flash(
                "Capacity must be a valid number.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        if parsed_capacity <= 0:

            flash(
                "Capacity must be greater than 0.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        # -------------------------------------------------
        # CAPACITY CANNOT BE LESS THAN REGISTRATIONS
        # -------------------------------------------------

        registered_count = Registration.query.filter_by(
            event_id=event.id,
            status="registered"
        ).count()


        if parsed_capacity < registered_count:

            flash(
                f"Capacity cannot be less than the "
                f"current registration count ({registered_count}).",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        # -------------------------------------------------
        # STATUS
        # -------------------------------------------------

        if status not in [
            "draft",
            "published"
        ]:

            status = "draft"


        # -------------------------------------------------
        # UPDATE EVENT
        # -------------------------------------------------

        event.title = title

        event.description = (
            description
            if description
            else None
        )

        event.category = category

        event.venue = venue

        event.event_date = parsed_date

        event.start_time = parsed_start_time

        event.end_time = parsed_end_time

        event.capacity = parsed_capacity

        event.status = status


        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            flash(
                "Unable to update event.",
                "danger"
            )

            return redirect(
                url_for(
                    "coordinator.edit_event",
                    event_id=event.id
                )
            )


        flash(
            "Event updated successfully.",
            "success"
        )


        return redirect(
            url_for(
                "coordinator.manage_events"
            )
        )


    return render_template(
        "coordinator/edit_event.html",
        user=current_user,
        event=event
    )


# =========================================================
# TOGGLE PUBLISH / DRAFT
# =========================================================

@coordinator_bp.route(
    "/events/<int:event_id>/toggle-status",
    methods=["POST"]
)
@coordinator_required
def toggle_event_status(event_id):

    event = Event.query.filter_by(
        id=event_id,
        coordinator_id=current_user.id
    ).first_or_404()


    if event.status == "published":

        event.status = "draft"

        message = "Event moved to draft."

    else:

        event.status = "published"

        message = "Event published successfully."


    db.session.commit()


    flash(
        message,
        "success"
    )


    return redirect(
        url_for(
            "coordinator.manage_events"
        )
    )


# =========================================================
# DELETE EVENT
# =========================================================

@coordinator_bp.route(
    "/events/<int:event_id>/delete",
    methods=["POST"]
)
@coordinator_required
def delete_event(event_id):

    event = Event.query.filter_by(
        id=event_id,
        coordinator_id=current_user.id
    ).first_or_404()


    registered_count = Registration.query.filter_by(
        event_id=event.id,
        status="registered"
    ).count()


    if registered_count > 0:

        flash(
            "This event cannot be deleted because students are registered for it.",
            "danger"
        )

        return redirect(
            url_for(
                "coordinator.manage_events"
            )
        )


    db.session.delete(event)

    db.session.commit()


    flash(
        "Event deleted successfully.",
        "success"
    )


    return redirect(
        url_for(
            "coordinator.manage_events"
        )
    )


# =========================================================
# EVENT REGISTRATIONS
# =========================================================

@coordinator_bp.route("/events/<int:event_id>/registrations")
@coordinator_required
def event_registrations(event_id):

    if current_user.role == "admin":
        event = Event.query.filter_by(
            id=event_id
        ).first_or_404()
    else:
        event = Event.query.filter_by(
            id=event_id,
            coordinator_id=current_user.id
        ).first_or_404()

    registrations = (
        Registration.query
        .options(
            joinedload(Registration.attendance),
            joinedload(Registration.student)
        )
        .filter(
            Registration.event_id == event.id,
            Registration.status == "registered"
        )
        .order_by(
            Registration.registered_at.desc()
        )
        .all()
    )

    total_registrations = len(registrations)

    present_count = sum(
        1
        for registration in registrations
        if registration.attendance
        and registration.attendance.present
    )

    absent_count = sum(
        1
        for registration in registrations
        if registration.attendance
        and not registration.attendance.present
    )

    pending_count = (
        total_registrations - present_count - absent_count
    )

    return render_template(
        "coordinator/event_registrations.html",
        user=current_user,
        event=event,
        registrations=registrations,
        total_registrations=total_registrations,
        present_count=present_count,
        absent_count=absent_count,
        pending_count=pending_count
    )


# =========================================================
# ATTENDANCE MANAGEMENT
# =========================================================

@coordinator_bp.route(
    "/events/<int:event_id>/registrations/<int:registration_id>/attendance",
    methods=["POST"]
)
@coordinator_required
def mark_attendance(event_id, registration_id):

    if current_user.role == "admin":
        event = Event.query.filter_by(
            id=event_id
        ).first()
    else:
        event = Event.query.filter_by(
            id=event_id,
            coordinator_id=current_user.id
        ).first()

    if not event:
        flash(
            "You are not authorized to manage attendance for this event.",
            "danger"
        )
        return redirect(
            url_for("coordinator.manage_events")
        )

    registration = Registration.query.filter_by(
        id=registration_id,
        event_id=event.id,
        status="registered"
    ).first()

    if not registration:
        flash(
            "Registration not found for this event.",
            "danger"
        )
        return redirect(
            url_for(
                "coordinator.event_registrations",
                event_id=event.id
            )
        )

    status_val = request.form.get("status", "").strip().lower()

    if status_val in ["present", "true", "1"]:
        is_present = True
    elif status_val in ["absent", "false", "0"]:
        is_present = False
    else:
        flash(
            "Invalid attendance status provided.",
            "warning"
        )
        return redirect(
            url_for(
                "coordinator.event_registrations",
                event_id=event.id
            )
        )

    attendance = Attendance.query.filter_by(
        registration_id=registration.id
    ).first()

    if attendance is None:
        attendance = Attendance(
            registration_id=registration.id,
            present=is_present,
            marked_by=current_user.id,
            marked_at=datetime.utcnow()
        )
        db.session.add(attendance)
    else:
        attendance.present = is_present
        attendance.marked_by = current_user.id
        attendance.marked_at = datetime.utcnow()

    try:
        db.session.commit()
        student_name = (
            registration.student.name
            if registration.student
            else "Student"
        )
        status_label = "Present" if is_present else "Absent"
        flash(
            f"Attendance marked as {status_label} for {student_name}.",
            "success"
        )
    except Exception:
        db.session.rollback()
        flash(
            "An error occurred while saving attendance. Please try again.",
            "danger"
        )

    next_url = request.form.get("next")
    if next_url and next_url.startswith("/coordinator/"):
        return redirect(next_url)

    return redirect(
        url_for(
            "coordinator.event_registrations",
            event_id=event.id
        )
    )
