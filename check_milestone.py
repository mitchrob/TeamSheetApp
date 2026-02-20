from app import create_app
from app.extensions import db
from app.models import Player, Appearance
from sqlalchemy import func

app = create_app()
with app.app_context():
    stats = db.session.query(Player.name, func.count(Appearance.id))\
        .join(Appearance)\
        .group_by(Player.name)\
        .all()
    
    milestone_players = []
    for name, count in stats:
        if (count + 1) % 50 == 0:
            print(f"MILESTONE: {name} has {count} appearances (Next is {count+1})")
            milestone_players.append(name)
        elif count == 0: # Should not happen with join but theoretically
            print(f"DEBUT: {name} has {count}")

    if not milestone_players:
        # Create a dummy player with 49 appearances
        dummy_name = "Milestone Man"
        p = Player.query.filter_by(name=dummy_name).first()
        if not p:
            p = Player(name=dummy_name)
            db.session.add(p)
            db.session.commit() # commit to get ID
            
            # Add 49 dummy appearances
            # Need a match context, might be messy. 
            # Easier to just update an existing player if possible or create fresh.
            # Let's just create 49 appearances linked to a dummy match (or existing match)
            # Actually, reusing matches might violate unique constraint (player in match twice)
            # So we might need multiple matches.
            print("No milestone players found. Please add manually or use existing players.")
        else:
            # check stats again
            c = Appearance.query.filter_by(player_id=p.id).count()
            print(f"Dummy {dummy_name} has {c}")
