from app import create_app
from app.extensions import db
from app.models import Match, Player, Appearance

app = create_app()
with app.app_context():
    p = Player.query.filter_by(name="Milestone Test Player").first()
    if p:
        print(f"Deleting player {p.name} and appearances...")
        # Cascade should handle appearances if configured, otherwise manual
        # Appearance has cascade="all, delete-orphan"? 
        # In Match model: appearances = db.relationship(..., cascade="all, delete-orphan")
        # In Player model: appearances = db.relationship(..., back_populates='player')
        # So deleting player might not cascade delete appearances unless backref cascade set.
        # Let's delete appearances first manually to be safe.
        Appearance.query.filter_by(player_id=p.id).delete()
        
        # Also delete the test matches we created?
        # We created matches with date 2000-01-01 and "Test Opp X"
        Match.query.filter_by(league="Test League").delete()
        
        db.session.delete(p)
        db.session.commit()
        print("Cleanup complete.")
    else:
        print("Test player not found.")
