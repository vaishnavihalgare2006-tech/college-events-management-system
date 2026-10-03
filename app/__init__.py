from flask import Flask, render_template
from config import Config

from app.extensions import db, migrate, login_manager
from app import models
from app.blueprints.coordinator import coordinator_bp


@login_manager.user_loader
def load_user(user_id):
    return models.User.query.get(int(user_id))


def create_app(config_class=Config):

    app = Flask(__name__)

    app.config.from_object(config_class)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    login_manager.login_view = "auth.login"


    # ==========================================
    # BLUEPRINTS
    # ==========================================

    from app.blueprints.auth import auth_bp
    from app.blueprints.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(coordinator_bp)


    # ==========================================
    # LANDING PAGE
    # ==========================================

    @app.route("/")
    def home():

        # Only published events
        events = (
            models.Event.query
            .filter_by(status="published")
            .order_by(
                models.Event.event_date.asc(),
                models.Event.start_time.asc()
            )
            .limit(6)
            .all()
        )


        # Total published events
        total_events = (
            models.Event.query
            .filter_by(status="published")
            .count()
        )


        # Total registered students
        total_students = (
            models.Registration.query
            .filter_by(status="registered")
            .count()
        )


        # Total event categories
        total_categories = (
            db.session.query(
                models.Event.category
            )
            .filter(
                models.Event.status == "published",
                models.Event.category.isnot(None)
            )
            .distinct()
            .count()
        )


        return render_template(
            "home.html",

            events=events,

            total_events=total_events,

            total_students=total_students,

            total_categories=total_categories
        )


    return app