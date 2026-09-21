import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AdminUser, AuditEvent
from app.utils import normalize_username


def register_cli(app):
    app.cli.add_command(users)


@click.group()
def users():
    """Manage administrator accounts."""


@users.command("bootstrap")
@click.option("--username", prompt=True)
@click.password_option(confirmation_prompt=True)
@with_appcontext
def bootstrap_user(username, password):
    """Create the first database administrator."""
    if AdminUser.query.count():
        raise click.ClickException("A database administrator already exists.")
    if len(password) < 12:
        raise click.ClickException("Passwords must contain at least 12 characters.")
    normalized = normalize_username(username)
    if not normalized:
        raise click.ClickException("Username is required.")
    user = AdminUser(
        username=username.strip(),
        normalized_username=normalized,
        password_hash=generate_password_hash(password),
        must_change_password=False,
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(
        AuditEvent(
            actor_user_id=user.id,
            action="bootstrap",
            entity_type="admin_user",
            entity_id=str(user.id),
            description=f"Bootstrapped administrator {user.username}",
        )
    )
    db.session.commit()
    click.echo(f"Created administrator {user.username}.")


@users.command("reset-password")
@click.argument("username")
@click.password_option(confirmation_prompt=True)
@with_appcontext
def reset_password(username, password):
    """Emergency-reset an administrator password."""
    if len(password) < 12:
        raise click.ClickException("Passwords must contain at least 12 characters.")
    user = AdminUser.query.filter_by(normalized_username=normalize_username(username)).first()
    if not user:
        raise click.ClickException("Administrator not found.")
    user.password_hash = generate_password_hash(password)
    user.must_change_password = True
    db.session.add(
        AuditEvent(
            action="emergency_password_reset",
            entity_type="admin_user",
            entity_id=str(user.id),
            description=f"Emergency password reset for {user.username}",
        )
    )
    db.session.commit()
    click.echo(f"Reset password for {user.username}; a change is required at next login.")
