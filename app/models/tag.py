from app import db
import uuid
from datetime import datetime

class Tag(db.Model):
    __tablename__ = 'tags'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(7), default="#6c757d")  # Default color as hex code
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __init__(self, name, color=None):
        self.name = name
        if color:
            self.color = color
