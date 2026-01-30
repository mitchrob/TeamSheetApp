from app.extensions import db

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    appearances = db.relationship('Appearance', back_populates='player', lazy='dynamic')

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    league = db.Column(db.String(100))
    season = db.Column(db.String(20))
    date = db.Column(db.Date, nullable=False)
    opposition = db.Column(db.String(100))
    location = db.Column(db.String(50))
    result = db.Column(db.String(20))
    guildford_points = db.Column(db.Integer)
    opposition_points = db.Column(db.Integer)
    appearances = db.relationship('Appearance', back_populates='match', cascade="all, delete-orphan", lazy='select')

class Appearance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False) # 1-15 for starts, 16-20 for bench
    player = db.relationship('Player', back_populates='appearances')
    match = db.relationship('Match', back_populates='appearances')
