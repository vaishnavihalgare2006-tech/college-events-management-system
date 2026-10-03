from datetime import date
from functools import wraps

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Event, Registration


student_bp = Blueprint(
    "student",
    __name__,
    url_prefix="/student",
)


def student_required(view):
    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role != "student":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


@student_bp.route("/home")
@student_required
def home():
    registrations = (
        Registration.query
        .filter_by(
            student_id=current_user.id,
            status="registered",
        )
        .all()
    )

    registered_count = len(registrations)

    upcoming_query = (
        Event.query
        .join(
            Registration,
            Registration.event_id == Event.id,
        )
        .filter(
            Registration.student_id == current_user.id,
            Registration.status == "registered",
            Event.status == "published",
            Event.event_date >= date.today(),
        )
        .order_by(
            Event.event_date.asc(),
            Event.start_time.asc(),
        )
    )

    upcoming_count = upcoming_query.count()
    upcoming_events = upcoming_query.limit(6).all()

    attended_count = sum(
        1
        for r in registrations
        if r.attendance and r.attendance.present
    )

    if registered_count > 0:
        calc_pct = (attended_count / registered_count) * 100
        attendance_percentage = int(calc_pct) if calc_pct.is_integer() else round(calc_pct, 1)
    else:
        attendance_percentage = 0

    registered_categories = sorted({
        r.event.category
        for r in registrations
        if r.event and r.event.category
    })

    return render_template(
        "student/home.html",
        user=current_user,
        registered_count=registered_count,
        upcoming_events=upcoming_events,
        upcoming_count=upcoming_count,
        attended_count=attended_count,
        attendance_percentage=attendance_percentage,
        registered_categories=registered_categories,
    )


@student_bp.route("/events")
@student_required
def events():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    query = Event.query.filter(
        Event.status == "published"
    )

    if search:
        query = query.filter(
            Event.title.ilike(f"%{search}%")
        )

    if category:
        query = query.filter(
            Event.category == category
        )

    events = (
        query
        .order_by(
            Event.event_date.asc(),
            Event.start_time.asc(),
        )
        .all()
    )

    categories = (
        Event.query
        .filter(
            Event.status == "published"
        )
        .with_entities(Event.category)
        .distinct()
        .order_by(Event.category.asc())
        .all()
    )

    categories = [
        item[0]
        for item in categories
        if item[0]
    ]

    registered_event_ids = {
        registration.event_id
        for registration in Registration.query.filter_by(
            student_id=current_user.id,
            status="registered",
        ).all()
    }

    return render_template(
        "student/events.html",
        user=current_user,
        events=events,
        categories=categories,
        search=search,
        selected_category=category,
        registered_event_ids=registered_event_ids,
    )


@student_bp.route("/events/<int:event_id>")
@student_required
def event_detail(event_id):
    event = (
        Event.query
        .filter_by(
            id=event_id,
            status="published",
        )
        .first_or_404()
    )

    is_registered = (
        Registration.query
        .filter_by(
            event_id=event.id,
            student_id=current_user.id,
            status="registered",
        )
        .first()
        is not None
    )

    registered_count = (
        Registration.query
        .filter_by(
            event_id=event.id,
            status="registered",
        )
        .count()
    )

    remaining_seats = max(0, event.capacity - registered_count)
    is_full = remaining_seats <= 0

    return render_template(
        "student/event_detail.html",
        user=current_user,
        event=event,
        is_registered=is_registered,
        registered_count=registered_count,
        remaining_seats=remaining_seats,
        is_full=is_full,
    )


@student_bp.route("/events/<int:event_id>/register", methods=["POST"])
@student_required
def register_event(event_id):
    event = (
        Event.query
        .filter_by(
            id=event_id,
            status="published",
        )
        .first_or_404()
    )

    existing_registration = (
        Registration.query
        .filter_by(
            event_id=event.id,
            student_id=current_user.id,
        )
        .first()
    )

    if existing_registration and existing_registration.status == "registered":
        flash(
            "You are already registered for this event.",
            "warning",
        )
        return redirect(
            url_for(
                "student.event_detail",
                event_id=event.id,
            )
        )

    registered_count = (
        Registration.query
        .filter_by(
            event_id=event.id,
            status="registered",
        )
        .count()
    )

    if registered_count >= event.capacity:
        flash(
            "Registration closed. This event has reached full capacity.",
            "danger",
        )
        return redirect(
            url_for(
                "student.event_detail",
                event_id=event.id,
            )
        )

    if existing_registration:
        existing_registration.status = "registered"
    else:
        new_registration = Registration(
            student_id=current_user.id,
            event_id=event.id,
            status="registered",
        )
        db.session.add(new_registration)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(
            "You are already registered for this event.",
            "warning",
        )
        return redirect(
            url_for(
                "student.event_detail",
                event_id=event.id,
            )
        )

    flash(
        "Registration successful! You are now registered for this event.",
        "success",
    )
    return redirect(
        url_for(
            "student.event_detail",
            event_id=event.id,
        )
    )
