from app import db
from datetime import datetime

class Setting(db.Model):
    __tablename__ = 'settings'
    
    id = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, id, value=None):
        self.id = id
        self.value = value
