from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required

from app.extensions import db
from app.models import User


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/auth",
)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        department = request.form.get("department", "").strip()

        if not name or not email or not password:
            flash(
                "Name, email and password are required.",
                "danger",
            )
            return redirect(url_for("auth.register"))

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash(
                "An account with this email already exists.",
                "danger",
            )
            return redirect(url_for("auth.register"))

        user = User(
            name=name,
            email=email,
            role="student",
            department=department or None,
        )

        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash(
            "Registration successful. Please login.",
            "success",
        )

        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash(
                    "Your account is inactive.",
                    "danger",
                )
                return redirect(url_for("auth.login"))

            login_user(user)

            if user.role == "admin":
                return redirect(url_for("coordinator.dashboard"))

            if user.role == "coordinator":
                return redirect(url_for("coordinator.dashboard"))

            return redirect(url_for("student.home"))

        flash(
            "Invalid email or password.",
            "danger",
        )

        return redirect(url_for("auth.login"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()

    flash(
        "You have been logged out.",
        "success",
    )

    return redirect(url_for("auth.login"))