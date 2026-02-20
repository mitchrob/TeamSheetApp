from app import create_app
from app.extensions import db
from app.models import Match, Player, Appearance
from datetime import date

app = create_app()
with app.app_context():
    # create player
    p_name = "Milestone Test Player"
    p = Player.query.filter_by(name=p_name).first()
    if not p:
        p = Player(name=p_name)
        db.session.add(p)
        db.session.commit()
    
    # Check count
    count = Appearance.query.filter_by(player_id=p.id).count()
    needed = 49 - count
    
    if needed > 0:
        print(f"Adding {needed} appearances for {p_name}...")
        # Create a dummy match if needed, or reuse
        # To avoid unique constrains if meaningful, usually (match_id, player_id) is unique?
        # Model definition: 
        # class Appearance(db.Model):
        #     player_id = ...
        #     match_id = ...
        #     ... relationship ...
        # No unique constraint explicit in models.py shown, but usually implied. 
        # But let's create separate matches to be safe.
        
        for i in range(needed):
            m = Match(
                league="Test League",
                season="2000-01", 
                date=date(2000, 1, 1),
                opposition=f"Test Opp {i}",
                location="Home",
                result="Win",
                guildford_points=10,
                opposition_points=0
            )
            db.session.add(m)
            db.session.flush() # get ID
            
            app_rec = Appearance(player_id=p.id, match_id=m.id, position=1)
            db.session.add(app_rec)
        
        db.session.commit()
        print(f"Added {needed} appearances.")
    else:
        print(f"{p_name} already has {count} appearances.")
