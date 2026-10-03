from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(120),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="student",
    )

    department = db.Column(
        db.String(120),
        nullable=True,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    events = db.relationship(
        "Event",
        back_populates="coordinator",
        foreign_keys="Event.coordinator_id",
    )

    registrations = db.relationship(
        "Registration",
        back_populates="student",
        foreign_keys="Registration.student_id",
    )

    marked_attendance = db.relationship(
        "Attendance",
        back_populates="marker",
        foreign_keys="Attendance.marked_by",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password,
        )

    def __repr__(self):
        return f"<User {self.email}>"


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    title = db.Column(
        db.String(200),
        nullable=False,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    category = db.Column(
        db.String(100),
        nullable=False,
    )

    venue = db.Column(
        db.String(200),
        nullable=False,
    )

    event_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    start_time = db.Column(
        db.Time,
        nullable=False,
    )

    end_time = db.Column(
        db.Time,
        nullable=False,
    )

    capacity = db.Column(
        db.Integer,
        nullable=False,
    )

    banner_url = db.Column(
        db.String(500),
        nullable=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="draft",
    )

    coordinator_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    coordinator = db.relationship(
        "User",
        back_populates="events",
        foreign_keys=[coordinator_id],
    )

    registrations = db.relationship(
        "Registration",
        back_populates="event",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Event {self.title}>"


class Registration(db.Model):
    __tablename__ = "registrations"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    event_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "events.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="registered",
    )

    registered_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    event = db.relationship(
        "Event",
        back_populates="registrations",
    )

    student = db.relationship(
        "User",
        back_populates="registrations",
        foreign_keys=[student_id],
    )

    attendance = db.relationship(
        "Attendance",
        back_populates="registration",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "event_id",
            "student_id",
            name="uq_event_student_registration",
        ),
    )

    def __repr__(self):
        return (
            f"<Registration event={self.event_id} "
            f"student={self.student_id}>"
        )


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    registration_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "registrations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    present = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    marked_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
    )

    marked_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    registration = db.relationship(
        "Registration",
        back_populates="attendance",
    )

    marker = db.relationship(
        "User",
        back_populates="marked_attendance",
        foreign_keys=[marked_by],
    )

    def __repr__(self):
        return (
            f"<Attendance registration={self.registration_id} "
            f"present={self.present}>"
        )