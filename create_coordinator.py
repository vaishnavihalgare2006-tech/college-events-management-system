from app import create_app
from app.extensions import db
from app.models import User


app = create_app()


with app.app_context():

    email = "coordinator@cems.com"

    existing_user = User.query.filter_by(email=email).first()

    if existing_user:
        print("Coordinator account already exists.")
        print(f"Email: {email}")

    else:
        coordinator = User(
            name="CEMS Coordinator",
            email=email,
            role="coordinator",
            department="College Administration",
            is_active=True
        )

        coordinator.set_password("Coordinator@123")

        db.session.add(coordinator)
        db.session.commit()

        print("Coordinator account created successfully.")
        print()
        print("Login Details")
        print("---------------------------")
        print("Email    :", email)
        print("Password : Coordinator@123")
        print("Role     : coordinator")